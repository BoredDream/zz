"""第四问：独立复算（不复用 src/q4_solver.py 或 src/q4_q2_solver.py 的任何代码）。

为什么需要它
------------
`reports/project_task_reference.md`「最终状态定义」第 3 条要求「每个结果均能由明细
独立复算」。第四问此前只有一个校验，且**不是**独立复算：

  * `scripts/validate_q4.py` —— **import 了 `src/q4_solver` 与 `src/q4_q2_solver`**，
    复用了模型自己的常量（`M.ETA`/`M.CMAX`/`M.T`）、自己加载的价格矩阵（`M.PMAT`）
    和**自己的结算函数**（`M.natural_settle_parts4`、`M.midnight_actual`）。
    它证明的是「编码与已验收产物自洽」，不是数字算对了。

本脚本换一条路：只读**原始附件**（附件2、附件4 的 xlsx）与**已落盘的明细数组**（npz），
按 README「固定口径」与题面公式从零重算，再与已验收产物逐位比对。

三条彼此独立的复算路径
----------------------
甲 结算复算
    直接从附件4 构造自然日电价 `p(d) = [PMAT[d−1,143], PMAT[d,0:143]]`，
    独立实现题面公式 `p·min(x,q) + 1.5p(q−x)⁺ + 0.5p(x−q)⁺ + 5p·z`，
    逐日重算三项费用与总费用，与 payload / summary 比对。
乙 实时层与储能轨迹复算（**只有 4-3 能做**，理由见下）
    按 README 第 6 条与模型文档描述的贪心规则**重新实现**实时层，从当日初始 SOC
    出发独立重放整条能量轨迹（c/g/z/w/S），与明细数组比对。
丙 物理与能量平衡不变量（两个变体都做）
    SOC 递推、充放电上限、SOC 上下限、非负、同时充放电、
    **能量平衡恒等式** `L − G − q + c − g − z + w ≡ 0`（逐时段，纯明细 + 附件2）。

本脚本**没有**证明什么
----------------------
  * **4-2 的实时层规则未被独立重放。** 变体 4-2 用的是 `q2_solver.causal_dispatch`，
    它以 SAA 最优解的**参考充放电轨迹**（`reference_charge`/`reference_discharge`）
    为输入；这两个数组**没有落盘**（`scripts/export_q4.py` 只存了 c/g/z/w/S），
    因此无法从已有产物重放该规则。对 4-2 只做了路径甲与路径丙（含能量平衡恒等式）。
  * 预测子模型（附件4 的两因子电价预测 `price_hat`、净负荷情景生成 `scenario_set`）
    ——两条路径都直接使用已落盘的决策轨迹，不重新预测；
  * SAA 情景生成与阶段 LP 编码本身——本脚本**不重解任何 LP**。最优化层面的证据只有
    `scripts/q4_solver_uniqueness_check.py`（最优值不依赖算法）与「记录解可行且满足
    全部物理约束」。**「记录解是该 LP 的最优解」这件事没有被独立复核。**
  * 终端储能价值 `λ` 这个**假设**（4-3 取 0.478、4-2 取 0.33417，均取自附件1 的
    价格水平，而结算价是附件4）——它的影响由 `scripts/q4_lambda_sensitivity.py` 单独度量；
  * 冷启动约定（1月1日首段负荷/光伏缺失、附件4 无历史时以附件1 作价格先验）；
  * 1 月预热期（交付期统计从 2025-02-01 起，本脚本也只比对交付期）；
  * `result4-{2,3}.xlsx` 工作簿本身：`scripts/validate_q4.py` 做的是「工作簿 ↔ payload」
    逐格对账，本脚本做的是「payload ↔ 原始附件」。两者复合可把工作簿传递地锚到原始
    附件，但工作簿未被本脚本直接重算。
  * 路径乙按 README/模型文档描述的贪心规则**重新实现**实时层。它通过，说明代码与该
    描述一致；若描述本身就写错了，两者会一起错。

用法
----
    python scripts/verify_q4.py [2|3] [K]     默认 3，K 默认 30。
    不带参数则对 2 与 3 各跑一次。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "problem" / "data"
OUT = ROOT / "outputs" / "q4"

# ---- 物理与结算常量：全部取自题面 / README「固定口径」，不取自模型代码 ----
T = 144                     # 每自然日 144 个 10 分钟时段
DT = 1.0 / 6.0              # 时段长（h）
ETA = 0.9                   # 单程效率
SMIN, SMAX = 1200.0, 10800.0
CMAX = 5000.0 * DT          # 单时段充/放电上限（交流母线侧 kWh）
EMG_MULT = 5.0              # 紧急购电电价倍数
UP_MULT, DN_MULT = 1.5, 0.5  # 上调（缺额）/下调（超发）违约金倍数
DELIVERY_START = "2025-02-01"
DELIVERY_END = "2025-12-31"
S0_DEFAULT = 6000.0
ND = 365
N_JAN = 31                  # 1 月预热天数 → 交付期起点在明细中的下标

TOL_YUAN = 1e-6
TOL_KWH = 1e-6

failures: list[str] = []
worst_seen: dict[str, float] = {}


def check(name: str, worst: float, tol: float = TOL_YUAN) -> None:
    ok = worst <= tol
    worst_seen[name] = max(worst_seen.get(name, 0.0), worst)
    if not ok:
        print(f"  [FAIL] {name:<52} 最大偏差 {worst:.3e}")
        failures.append(f"{name}: {worst:.3e}")
    else:
        print(f"  [OK ] {name:<52} 最大偏差 {worst:.3e}")


# ----------------------------------------------------------------------
# 0. 直接读原始附件
# ----------------------------------------------------------------------
def load_pmat() -> np.ndarray:
    """附件4 实际电价矩阵（365×144）。附件4 无日期列，按 2025 全年逐日排列。"""
    m = pd.read_excel(DATA / "附件4.xlsx", header=0).iloc[:, 1:].to_numpy(float)
    if m.shape != (ND, T):
        raise ValueError(f"附件4 应为 {ND}×{T}，实得 {m.shape}")
    return m


def natural_price4(m: np.ndarray, d: int) -> np.ndarray:
    """附件4 模板行 → 自然日 00:00--24:00 的 144 个价格。

    README「固定口径」第 3 条：附件原始列 `0:10, ..., 0:00+1` 映射到绝对时刻，
    第 t 列覆盖 [(t+1)*10, (t+2)*10) 分钟。故自然日首段 00:00--00:10 用**上一日**末列。
    """
    if d == 0:
        raise ValueError("交付期统计不含 d=0，自然日电价未定义")
    return np.r_[m[d - 1, T - 1], m[d, : T - 1]]


def load_actual_load_pv() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """附件2 的小区负载与光伏实际功率（kW → kWh/时段）。"""
    dl = pd.read_excel(DATA / "附件2.xlsx", sheet_name="小区负载", header=0)
    dates = pd.to_datetime(dl.iloc[:, 0]).dt.strftime("%Y-%m-%d").tolist()
    lkw = dl.iloc[:, 1:].to_numpy(float)
    gkw = pd.read_excel(DATA / "附件2.xlsx", sheet_name="光伏发电实际功率",
                        header=0).iloc[:, 1:].to_numpy(float)
    if lkw.shape != (ND, T) or gkw.shape != (ND, T):
        raise ValueError(f"附件2 应为 {ND}×{T}，实得 {lkw.shape} / {gkw.shape}")
    return lkw * DT, gkw * DT, dates


LOAD_PV: tuple[np.ndarray, np.ndarray, list[str]]


# ----------------------------------------------------------------------
# 1. 独立实现题面结算公式
# ----------------------------------------------------------------------
def settle_split(x: np.ndarray, q: np.ndarray, z: np.ndarray, p: np.ndarray):
    """题面口径 `C = p·min(x,q) + 1.5p(q−x)⁺ + 0.5p(x−q)⁺ + 5p·z` 的三项拆分。"""
    up = np.maximum(q - x, 0.0)
    dn = np.maximum(x - q, 0.0)
    return p * np.minimum(x, q), UP_MULT * p * up + DN_MULT * p * dn, EMG_MULT * p * z


# ----------------------------------------------------------------------
# 2. 独立重实现实时层（贪心调度）—— 对应变体 4-3
# ----------------------------------------------------------------------
def greedy_step(net: float, S: float) -> tuple[float, float, float, float, float]:
    """单时段贪心：净负荷为正则先放电、不足再紧急购电；为负则先充电、充不下的弃电。

    规则取自 README「固定口径」第 6 条与模型的实时层描述：
      g = min(net, CMAX, (S−SMIN)·η)
      c = min(−net, CMAX, (SMAX−S)/η)
    返回 (c, g, z, w, S_new)。
    """
    c = g = z = w = 0.0
    if net > 0:
        g = max(min(net, CMAX, (S - SMIN) * ETA), 0.0)
        S -= g / ETA
        z = net - g
    else:
        s = -net
        c = max(min(s, CMAX, (SMAX - S) / ETA), 0.0)
        S += ETA * c
        w = s - c
    return c, g, z, w, S


def replay_day(d: int, S0: float, nq: np.ndarray,
               l_kwh: np.ndarray, g_kwh: np.ndarray) -> dict[str, np.ndarray]:
    """从当日初始 SOC 出发，独立重放自然日 00:00--24:00 的能量轨迹。

    自然时段 t 的净负荷：
      t=0       → 上一日模板末段 `L[d−1,143] − G[d−1,143]`（0:00 尚未实现，
                  用已完成的绝对时刻 00:00--00:10 所属区间，即前一日最后一列）
      t=1..143  → 本日模板 `L[d,t−1] − G[d,t−1]`
    """
    c = np.zeros(T); g = np.zeros(T); z = np.zeros(T); w = np.zeros(T)
    S_hist = np.zeros(T + 1)
    S_hist[0] = S0
    S = S0
    for t in range(T):
        if t == 0:
            net = float(l_kwh[d - 1, T - 1] - g_kwh[d - 1, T - 1] - nq[0])
        else:
            net = float(l_kwh[d, t - 1] - g_kwh[d, t - 1] - nq[t])
        c[t], g[t], z[t], w[t], S = greedy_step(net, S)
        S_hist[t + 1] = S
    return {"c": c, "g": g, "z": z, "w": w, "S": S_hist}


# ----------------------------------------------------------------------
# 3. 单变体复算
# ----------------------------------------------------------------------
def verify_variant(variant: str, m: np.ndarray, K: int) -> dict:
    detail = np.load(OUT / f"detail_q4-{variant}_K{K}.npz")
    payload = json.loads((OUT / f"payload_q4-{variant}_K{K}.json").read_text(encoding="utf-8"))
    summary = json.loads((OUT / f"summary_q4-{variant}_K{K}.json").read_text(encoding="utf-8"))
    dates = [str(x) for x in detail["dates"]]
    x, q = detail["x"], detail["q"]
    nx, nq = detail["natural_x"], detail["natural_q"]
    z, c, g, w, S = detail["z"], detail["c"], detail["g"], detail["w"], detail["S"]
    S0v = detail["S0"]

    i0 = dates.index(DELIVERY_START)
    if dates[-1] != DELIVERY_END:
        raise ValueError(f"{variant}: 交付期末日应为 {DELIVERY_END}，实得 {dates[-1]}")
    n_days = len(dates)
    sl = slice(i0, n_days)

    # ---- 结构：明细数组与原始附件的一致性 ----
    check(f"[{variant}] 明细电价 = 附件4 实际电价/kWh", float(np.abs(detail["price"] - m).max()), 1e-12)
    check(f"[{variant}] 自然日电价右移一位自洽",
          float(np.abs(natural_price4(m, i0)[1:] - m[i0, : T - 1]).max()), 1e-12)
    # 自然日计划 = 上一日末列 + 当日模板前 143 段
    check(f"[{variant}] natural_x 右移自洽/kWh",
          max(float(np.abs(nx[i0:, 1:] - x[i0:, : T - 1]).max()),
              float(np.abs(nx[i0:, 0] - x[i0 - 1: n_days - 1, T - 1]).max())), TOL_KWH)
    check(f"[{variant}] natural_q 右移自洽/kWh",
          max(float(np.abs(nq[i0:, 1:] - q[i0:, : T - 1]).max()),
              float(np.abs(nq[i0:, 0] - q[i0 - 1: n_days - 1, T - 1]).max())), TOL_KWH)
    if variant == "2":
        # 4-2 只在 0:00 决策，q ≡ x（题面「不滚动调整」的建模选择）
        check(f"[{variant}] q ≡ x（只在0:00决策）/kWh", float(np.abs(q - x).max()), TOL_KWH)

    # ---- 甲：结算复算（自然日） ----
    pday = {d["date"]: d for d in payload["days"]}
    if len(pday) != n_days - i0:
        raise ValueError(f"{variant}: payload 应为 {n_days - i0} 天，实得 {len(pday)}")
    plan_t = adj_t = emg_t = tot_t = 0.0
    day_gap: dict[str, float] = {}
    for i in range(i0, n_days):
        p = natural_price4(m, i)
        sp, sa, se = settle_split(nx[i], nq[i], z[i], p)
        tot = float(sp.sum() + sa.sum() + se.sum())
        plan_t += float(sp.sum()); adj_t += float(sa.sum()); emg_t += float(se.sum())
        tot_t += tot
        rec = pday[dates[i]]
        # 三项之和 == 总费用（题面口径恒等式，独立于模型）
        resid = abs(tot - (float(sp.sum()) + float(sa.sum()) + float(se.sum())))
        day_gap[dates[i]] = abs(tot - rec["total_cost_yuan"]) + resid

    worst_day = max(day_gap, key=lambda k: day_gap[k])
    check(f"[{variant}] 逐日总费用 vs payload", max(day_gap.values()))
    check(f"[{variant}] 交付期计划购电费 vs summary", abs(plan_t - summary["totals"]["plan_cost_yuan"]))
    check(f"[{variant}] 交付期调整相关费用 vs summary", abs(adj_t - summary["totals"]["adjust_cost_yuan"]))
    check(f"[{variant}] 交付期紧急购电费 vs summary", abs(emg_t - summary["totals"]["emergency_cost_yuan"]))
    check(f"[{variant}] 交付期总费用 vs summary", abs(tot_t - summary["totals"]["total_cost_yuan"]))

    qty = {
        "emergency_kwh": float(z[sl].sum()),
        "charge_kwh": float(c[sl].sum()),
        "discharge_kwh": float(g[sl].sum()),
        "curtail_kwh": float(w[sl].sum()),
        "adjust_up_kwh": float(np.maximum(nq[sl] - nx[sl], 0).sum()),
        "adjust_down_kwh": float(np.maximum(nx[sl] - nq[sl], 0).sum()),
    }
    for k, v in qty.items():
        check(f"[{variant}] 交付期 {k} vs summary", abs(v - summary["totals"][k]), TOL_KWH)

    # ---- 丙：物理与能量平衡不变量（纯明细 + 附件2） ----
    l_kwh, g_kwh, _ = LOAD_PV
    soc_res = float(np.abs(S[:, 1:] - (S[:, :-1] + ETA * c - g / ETA)).max())
    check(f"[{variant}] SOC 递推残差/kWh", soc_res, 1e-9)
    check(f"[{variant}] 充电量超上限/kWh", float(np.maximum(c - CMAX, 0).max()), TOL_KWH)
    check(f"[{variant}] 放电量超上限/kWh", float(np.maximum(g - CMAX, 0).max()), TOL_KWH)
    check(f"[{variant}] SOC 低于下限/kWh", float(np.maximum(SMIN - S, 0).max()), TOL_KWH)
    check(f"[{variant}] SOC 高于上限/kWh", float(np.maximum(S - SMAX, 0).max()), TOL_KWH)
    check(f"[{variant}] 负数电量/kWh",
          float(max(-min(c.min(), g.min(), z.min(), w.min(), x.min(), q.min(), nx.min(), nq.min()), 0.0)),
          TOL_KWH)
    check(f"[{variant}] 同时充放电/kWh", float(np.minimum(c, g).max()), TOL_KWH)
    check(f"[{variant}] 首日初始 SOC 偏离 6000/kWh", abs(S0v[0] - S0_DEFAULT), 1e-9)
    check(f"[{variant}] 跨日 SOC 不连续/kWh", float(np.abs(S0v[1:] - S[:, -1][:-1]).max()), 1e-9)
    check(f"[{variant}] SOC 轨迹首列 ≠ S0/kWh", float(np.abs(S[:, 0] - S0v).max()), 1e-9)

    # 能量平衡： L − G − q + c − g − z + w ≡ 0（逐时段，t=0 用前一日模板末列）
    Ln = np.empty_like(nq); Gn = np.empty_like(nq)
    Ln[1:, 0] = l_kwh[:-1, T - 1]; Gn[1:, 0] = g_kwh[:-1, T - 1]
    Ln[1:, 1:] = l_kwh[1:, : T - 1]; Gn[1:, 1:] = g_kwh[1:, : T - 1]
    Ln[0, 0] = l_kwh[0, 0]; Gn[0, 0] = g_kwh[0, 0]   # d=0 冷启动，不参与交付期统计
    Ln[0, 1:] = l_kwh[0, : T - 1]; Gn[0, 1:] = g_kwh[0, : T - 1]
    balance = Ln - Gn - nq + c - g - z + w
    check(f"[{variant}] 能量平衡恒等式/kWh", float(np.abs(balance[sl]).max()), TOL_KWH)

    # ---- 乙：实时层与储能轨迹独立重放（只对 4-3） ----
    if variant == "3":
        dc = np.zeros_like(c); dg = np.zeros_like(g); dz = np.zeros_like(z)
        dw = np.zeros_like(w); dS = np.zeros_like(S)
        for i in range(1, n_days):
            rep = replay_day(i, float(S0v[i]), nq[i], l_kwh, g_kwh)
            dc[i] = np.abs(rep["c"] - c[i]).max(); dg[i] = np.abs(rep["g"] - g[i]).max()
            dz[i] = np.abs(rep["z"] - z[i]).max(); dw[i] = np.abs(rep["w"] - w[i]).max()
            dS[i] = np.abs(rep["S"] - S[i]).max()
        check(f"[{variant}] 重放充电量 vs 明细/kWh", float(dc.max()), TOL_KWH)
        check(f"[{variant}] 重放放电量 vs 明细/kWh", float(dg.max()), TOL_KWH)
        check(f"[{variant}] 重放紧急购电 vs 明细/kWh", float(dz.max()), TOL_KWH)
        check(f"[{variant}] 重放弃电 vs 明细/kWh", float(dw.max()), TOL_KWH)
        check(f"[{variant}] 重放 SOC 轨迹 vs 明细/kWh", float(dS.max()), TOL_KWH)
    else:
        print(f"  [--  ] [{variant}] 实时层重放：跳过（SAA 参考充放电轨迹未落盘，见模块 docstring）")

    return {"variant": variant, "total_cost_yuan": tot_t, "plan_cost_yuan": plan_t,
            "adjust_cost_yuan": adj_t, "emergency_cost_yuan": emg_t,
            "worst_day": worst_day, "worst_day_gap": day_gap[worst_day],
            "realtime_replay_done": variant == "3"}


# ----------------------------------------------------------------------
def main() -> int:
    global LOAD_PV, K
    args = [a for a in sys.argv[1:]]
    variants = [args[0]] if args and args[0] in ("2", "3") else ["2", "3"]
    K = int(args[1]) if len(args) > 1 else 30

    print("=" * 96)
    print("第四问独立复算：只读原始附件2/4 + 已落盘明细，不 import src/q4_solver.py / q4_q2_solver.py")
    print("=" * 96)

    print("\n0. 原始数据口径")
    m = load_pmat()
    LOAD_PV = load_actual_load_pv()
    l_kwh, g_kwh, adates = LOAD_PV
    print(f"  附件4 实际电价 {m.shape}  范围 {m.min():.4f}—{m.max():.4f}  均值 {m.mean():.4f} 元/kWh")
    print(f"  附件2 负载/光伏 {l_kwh.shape}  日期 {adates[0]} .. {adates[-1]}")
    print(f"  交付期 {DELIVERY_START} .. {DELIVERY_END}（明细下标 {N_JAN} 起，共 {ND - N_JAN} 天）")

    rows = {}
    for v in variants:
        print(f"\n{'-' * 96}\n变体 4-{v}\n{'-' * 96}")
        rows[v] = verify_variant(v, m, K)

    print("\n" + "=" * 96)
    if failures:
        print(f"FAILED — {len(failures)} 项超差：")
        for f in failures:
            print("   -", f)
    else:
        print("ALL OK — 所有独立复算项均在容差内")
    print("=" * 96)

    result = {"mode": "independent_verify", "K": K, "variants": rows,
              "worst": worst_seen, "failures": failures,
              "realtime_replay_covered": ["3"]}
    dest = OUT / f"independent_verify_q4_K{K}.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {dest}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
