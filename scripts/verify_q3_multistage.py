"""第三问：独立复算（不复用 src/q3_multistage.py 的任何代码）。

为什么需要它
------------
`reports/project_task_reference.md`「最终状态定义」第 3 条要求「每个结果均能由明细
独立复算」。此前第三问只有两个校验，都**不是**独立复算：

  * `scripts/validate_q3_multistage.py` —— **import 了 `src/q3_multistage`**，用的是模型
    自己的常量（`M.ETA`/`M.T`）、自己加载的数据（`M.L`/`M.G`）和自己的时点约定
    （`M.midnight_actual`）。它证明的是「编码与已验收产物自洽」。
  * `scripts/q3_solver_uniqueness_check.py` —— 复用同一份 LP 构造，只换求解算法。
    它证明最优值不依赖求解器配置，不证明数字本身算对了。

本脚本换一条路：只读**原始附件**（附件1/2 的 xlsx）与**已落盘的明细数组**（npz），
按 README「固定口径」与题面公式从零重算，再与已验收产物逐位比对。
不 import 模型，不使用模型的任何函数或常量。

三条彼此独立的复算路径
----------------------
甲 结算复算
    用自然日价格向量独立实现题面费用公式 `p·min(x,q) + 1.5p(q−x)⁺ + 0.5p(x−q)⁺ + 5p·z`，
    逐日重算三项费用与总费用，与 payload / summary 比对。
乙 实时层与储能轨迹复算
    按 README 第 6 条与模型 docstring 描述的贪心调度规则**重新实现**实时层，
    从当日初始 SOC 出发独立重放整条能量轨迹（c/g/z/w/S），与明细数组比对。
丙 八组合复算
    对八个预报发布组合各重跑甲，独立重算对照表，并独立重算条件边际与 Shapley 分摊。

本脚本**没有**证明什么
----------------------
尚未被独立复算覆盖的部分（引用结论时必须保留这些限定）：

  * 预测子模型（附件3 的 PCHIP 插值与衰减均值组合、负荷预测）——三条路径都直接使用
    已落盘的决策轨迹，不重新预测；
  * SAA 情景生成与阶段 LP 编码本身——本脚本不重解任何 LP。最优化层面的证据只有
    `scripts/q3_solver_uniqueness_check.py`（最优值不依赖算法）与「记录解可行且满足
    全部物理约束」。**「记录解是该 LP 的最优解」这件事没有被独立复核。**
  * 终端储能价值 `λ = 0.478` 这个**假设**；
  * 锁定区间规则（禁用某发布时刻时由上一次启用的时刻负责到下一次启用为止）；
  * 时间标签口径（README「固定口径」第 3 条：附件原始列 `0:10...0:00+1` 映射到绝对
    时刻，不做同行循环移位）。本脚本按该口径复算并**验证其自洽**，但口径本身是
    建模约定，不是算术结论。
  * `result3.xlsx` 工作簿本身：`scripts/validate_q3_multistage.py` 做的是「工作簿 ↔
    payload」逐格对账，本脚本做的是「payload ↔ 原始附件」。两者复合可把工作簿传递地
    锚到原始附件，但工作簿未被本脚本直接重算。
  * 路径乙按 README/模型文档描述的贪心规则**重新实现**实时层。它通过，说明代码与
    该描述一致；若描述本身就写错了，两者会一起错。

用法
----
    python scripts/verify_q3_multistage.py [tag] [K]
    tag 默认 0123（主答案），K 默认 30。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "problem" / "data"
OUT = ROOT / "outputs" / "q3_multistage"

# ---- 物理与结算常量：全部取自题面 / README「固定口径」，不取自模型代码 ----
T = 144                     # 每自然日 144 个 10 分钟时段
DT = 1.0 / 6.0              # 时段长（h）
ETA = 0.9                   # 单程效率
SMIN, SMAX = 1200.0, 10800.0
CMAX = 5000.0 * DT          # 单时段充/放电上限（交流母线侧 kWh），题面 5000 kW × 10min
EMG_MULT = 5.0              # 紧急购电电价倍数
UP_MULT, DN_MULT = 1.5, 0.5  # 上调（缺额）/下调（超发）违约金倍数
DELIVERY_START = "2025-02-01"
DELIVERY_END = "2025-12-31"
S0_DEFAULT = 6000.0
STAGE_HOUR = {"0": "0", "1": "6", "2": "12", "3": "18"}   # 阶段序号 → 发布时刻

TOL_YUAN = 1e-6             # 费用比对容差（元）
TOL_KWH = 1e-6              # 电量比对容差（kWh）

failures: list[str] = []
worst_seen: dict[str, float] = {}
QUIET = False               # 八组合的 7 个非主组合只记录不逐行打印


def check(name: str, worst: float, tol: float = TOL_YUAN) -> None:
    ok = worst <= tol
    worst_seen[name] = max(worst_seen.get(name, 0.0), worst)
    if not ok:
        print(f"  [FAIL] {name:<46} 最大偏差 {worst:.3e}")
        failures.append(f"{name}: {worst:.3e}")
    elif not QUIET:
        print(f"  [OK ] {name:<46} 最大偏差 {worst:.3e}")


# ----------------------------------------------------------------------
# 0. 直接读原始附件
# ----------------------------------------------------------------------
def load_price() -> np.ndarray:
    """附件1 的分时电价（144 列）。

    README「固定口径」第 3 条：附件原始列 `0:10, ..., 0:00+1` 映射到绝对时刻，
    即第 t 列覆盖 [(t+1)*10, (t+2)*10) 分钟。因此一个自然日 00:00--24:00 的
    144 个价格是附件列的一次**右移一位**：00:00--00:10 用上一日的末列。
    """
    df = pd.read_excel(DATA / "附件1.xlsx", header=0)
    df.columns = ["t", "p", "L", "G"]
    p = df.p.to_numpy(float)
    if p.shape != (T,):
        raise ValueError(f"附件1 电价应为 {T} 列，实得 {p.shape}")
    return p


def natural_price(p: np.ndarray) -> np.ndarray:
    """附件列 → 自然日 00:00--24:00 的 144 个价格（右移一位，不做同行循环移位）。"""
    return np.r_[p[-1], p[: T - 1]]


def load_actual_load_pv() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """附件2 的小区负载与光伏实际功率（kW → kWh/时段）。"""
    dl = pd.read_excel(DATA / "附件2.xlsx", sheet_name="小区负载", header=0)
    dates = pd.to_datetime(dl.iloc[:, 0]).dt.strftime("%Y-%m-%d").tolist()
    lkw = dl.iloc[:, 1:].to_numpy(float)
    gkw = pd.read_excel(DATA / "附件2.xlsx", sheet_name="光伏发电实际功率",
                        header=0).iloc[:, 1:].to_numpy(float)
    if lkw.shape[1] != T or gkw.shape[1] != T:
        raise ValueError(f"附件2 应为 {T} 列，实得 {lkw.shape} / {gkw.shape}")
    return lkw * DT, gkw * DT, dates


# ----------------------------------------------------------------------
# 1. 独立实现题面结算公式
# ----------------------------------------------------------------------
def settle_split(x: np.ndarray, q: np.ndarray, z: np.ndarray, p: np.ndarray):
    """题面口径 `C = p·min(x,q) + 1.5p(q−x)⁺ + 0.5p(x−q)⁺ + 5p·z` 的三项拆分。"""
    up = np.maximum(q - x, 0.0)
    dn = np.maximum(x - q, 0.0)
    return p * np.minimum(x, q), UP_MULT * p * up + DN_MULT * p * dn, EMG_MULT * p * z


# ----------------------------------------------------------------------
# 2. 独立重实现实时层（贪心调度）
# ----------------------------------------------------------------------
def greedy_step(net: float, S: float) -> tuple[float, float, float, float, float]:
    """单时段贪心：净负荷为正则先放电、不足再紧急购电；为负则先充电、充不下的弃电。

    规则取自 README「固定口径」第 6 条与模型的实时层描述：
      g = min(net, CMAX, (S−SMIN)·η)   —— 放电 g 消耗 g/η 的储电量
      c = min(−net, CMAX, (SMAX−S)/η)  —— 充电 c 只存入 η·c
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


def replay_day(d: int, S0: float, nq: np.ndarray, l_kwh: np.ndarray,
               g_kwh: np.ndarray) -> dict[str, np.ndarray]:
    """从当日初始 SOC 出发，独立重放自然日 00:00--24:00 的能量轨迹。

    自然时段 t 的净负荷：
      t=0       → 上一日模板末段 `L[d−1,143] − G[d−1,143]`（0:00 尚未实现，用已完成的
                  绝对时刻 00:00--00:10 所属区间，即前一日最后一列）
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
# 3. 单组合复算
# ----------------------------------------------------------------------
def read_summary(tag: str) -> dict:
    path = OUT / f"summary_stages{tag}_K{K}.json"
    if not path.exists():
        raise FileNotFoundError(f"缺少 summary：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_combo(tag: str, p_nat: np.ndarray, deep: bool) -> dict:
    """对单个组合跑甲（结算）与可选乙（实时层）。返回交付期合计。"""
    global QUIET
    QUIET = not deep
    detail = np.load(OUT / f"detail_stages{tag}_K{K}.npz")
    payload = json.loads((OUT / f"payload_stages{tag}_K{K}.json").read_text(encoding="utf-8"))
    summary = read_summary(tag)
    dates = [str(d) for d in detail["dates"]]
    x, q, z = detail["natural_x"], detail["natural_q"], detail["z"]
    c, g, w, S = detail["c"], detail["g"], detail["w"], detail["S"]
    S0v = detail["S0"]

    i0 = dates.index(DELIVERY_START)
    if dates[-1] != DELIVERY_END:
        raise ValueError(f"{tag}: 交付期末日应为 {DELIVERY_END}，实得 {dates[-1]}")
    n_days = len(dates)

    # ---- 甲：结算复算（自然日） ----
    # payload/summary 只覆盖交付期，复算也只在交付期上比对。
    pday = {d["date"]: d for d in payload["days"]}
    if len(pday) != n_days - i0:
        raise ValueError(f"{tag}: payload 应为 {n_days - i0} 天，实得 {len(pday)}")
    plan_t = adj_t = emg_t = tot_t = 0.0
    day_gap: dict[str, float] = {}
    for i in range(i0, n_days):
        sp, sa, se = settle_split(x[i], q[i], z[i], p_nat)
        tot = float(sp.sum() + sa.sum() + se.sum())
        plan_t += float(sp.sum()); adj_t += float(sa.sum()); emg_t += float(se.sum())
        tot_t += tot
        rec = pday[dates[i]]
        # 三项之和 == 总费用（题面口径恒等式，独立于模型）
        resid = abs(tot - (float(sp.sum()) + float(sa.sum()) + float(se.sum())))
        day_gap[dates[i]] = abs(tot - rec["total_cost_yuan"]) + resid

    worst_day = max(day_gap, key=lambda k: day_gap[k])
    check(f"[{tag}] 逐日总费用 vs payload", max(day_gap.values()))
    check(f"[{tag}] 交付期计划购电费 vs summary", abs(plan_t - summary["totals"]["plan_cost_yuan"]))
    check(f"[{tag}] 交付期调整相关费用 vs summary", abs(adj_t - summary["totals"]["adjust_cost_yuan"]))
    check(f"[{tag}] 交付期紧急购电费 vs summary", abs(emg_t - summary["totals"]["emergency_cost_yuan"]))
    check(f"[{tag}] 交付期总费用 vs summary", abs(tot_t - summary["totals"]["total_cost_yuan"]))

    # ---- 交付期电量口径 ----
    sl = slice(i0, n_days)
    qty = {
        "emergency_kwh": float(z[sl].sum()),
        "charge_kwh": float(c[sl].sum()),
        "discharge_kwh": float(g[sl].sum()),
        "curtail_kwh": float(w[sl].sum()),
        "adjust_up_kwh": float(np.maximum(q[sl] - x[sl], 0).sum()),
        "adjust_down_kwh": float(np.maximum(x[sl] - q[sl], 0).sum()),
    }
    for k, v in qty.items():
        check(f"[{tag}] 交付期 {k} vs summary", abs(v - summary["totals"][k]), TOL_KWH)

    # ---- 物理不变量（纯明细，不依赖任何模型代码） ----
    soc_res = float(np.abs(S[:, 1:] - (S[:, :-1] + ETA * c - g / ETA)).max())
    check(f"[{tag}] SOC 递推残差/kWh", soc_res, 1e-9)
    check(f"[{tag}] 充电量超上限/kWh", float(np.maximum(c - CMAX, 0).max()), TOL_KWH)
    check(f"[{tag}] 放电量超上限/kWh", float(np.maximum(g - CMAX, 0).max()), TOL_KWH)
    check(f"[{tag}] SOC 低于下限/kWh", float(np.maximum(SMIN - S, 0).max()), TOL_KWH)
    check(f"[{tag}] SOC 高于上限/kWh", float(np.maximum(S - SMAX, 0).max()), TOL_KWH)
    check(f"[{tag}] 负数电量/kWh",
          float(max(-min(c.min(), g.min(), z.min(), w.min(), x.min(), q.min()), 0.0)), TOL_KWH)
    check(f"[{tag}] 同时充放电/kWh", float(np.minimum(c, g).max()), TOL_KWH)
    check(f"[{tag}] 跨日 SOC 不连续/kWh", float(np.abs(S0v[1:] - S[:-1, T]).max()), 1e-9)
    check(f"[{tag}] 首日初始 SOC 偏离 6000/kWh", abs(S0v[0] - S0_DEFAULT), 1e-9)

    # ---- 乙：实时层与储能轨迹独立重放 ----
    if deep:
        l_kwh, g_kwh, _ = LOAD_PV
        dc = np.zeros_like(c); dg = np.zeros_like(g)
        dz = np.zeros_like(z); dw = np.zeros_like(w); dS = np.zeros_like(S)
        for i in range(1, n_days):     # d=0 的午夜段无前一日实测，冷启动另有约定
            rep = replay_day(i, float(S0v[i]), q[i], l_kwh, g_kwh)
            dc[i] = np.abs(rep["c"] - c[i]).max(); dg[i] = np.abs(rep["g"] - g[i]).max()
            dz[i] = np.abs(rep["z"] - z[i]).max(); dw[i] = np.abs(rep["w"] - w[i]).max()
            dS[i] = np.abs(rep["S"] - S[i]).max()
        check(f"[{tag}] 重放充电量 vs 明细/kWh", float(dc.max()), TOL_KWH)
        check(f"[{tag}] 重放放电量 vs 明细/kWh", float(dg.max()), TOL_KWH)
        check(f"[{tag}] 重放紧急购电 vs 明细/kWh", float(dz.max()), TOL_KWH)
        check(f"[{tag}] 重放弃电 vs 明细/kWh", float(dw.max()), TOL_KWH)
        check(f"[{tag}] 重放 SOC 轨迹 vs 明细/kWh", float(dS.max()), TOL_KWH)

    return {"tag": tag, "total_cost_yuan": tot_t, "plan_cost_yuan": plan_t,
            "adjust_cost_yuan": adj_t, "emergency_cost_yuan": emg_t,
            "worst_day": worst_day, "worst_day_gap": day_gap[worst_day]}


# ----------------------------------------------------------------------
# 4. 八组合：独立重算条件边际与 Shapley
# ----------------------------------------------------------------------
def shapley(costs: dict[frozenset, float], players=(1, 2, 3)) -> dict[int, float]:
    """对加入顺序取平均的 Shapley 分摊，v(S) = 相对 0-only 的节省。"""
    import itertools
    base = costs[frozenset()]
    v = {S: base - c for S, c in costs.items()}
    full = frozenset(players)
    out = {}
    for j in players:
        acc = 0.0
        for perm in itertools.permutations(players):
            pre = frozenset(perm[: perm.index(j)])
            acc += v[pre | {j}] - v[pre]
        out[j] = acc / len(list(itertools.permutations(players)))
    assert abs(sum(out.values()) - v[full]) < 1e-6, "Shapley 效率公理不成立"
    return out


def verify_all_combos(p_nat: np.ndarray) -> dict:
    global QUIET
    import itertools
    combos = []
    for n in range(4):
        for c in itertools.combinations((1, 2, 3), n):
            combos.append("".join(str(x) for x in (0,) + c))
    costs: dict[frozenset, float] = {}
    rows = {}
    for tag in combos:
        r = verify_combo(tag, p_nat, deep=False)
        rows[tag] = r
        stages = frozenset(int(ch) for ch in tag[1:])
        costs[stages] = r["total_cost_yuan"]
        print(f"  [OK ] {tag:<8} 交付期总费用 {r['total_cost_yuan']:,.4f} 元")

    def label(tag: str) -> str:
        """产物 tag（0123）→ 对照表 policy 标签（0+6+12+18）。

        阶段序号 0/1/2/3 对应发布时刻 0:00/6:00/12:00/18:00，标签里写的是**时刻**。
        """
        head, rest = tag[0], tag[1:]
        return f"{head}-only" if not rest else "+".join([head] + [STAGE_HOUR[ch] for ch in rest])

    QUIET = False               # 汇总比对要逐行打印
    comp_path = OUT / "q3_stage_comparison.json"
    comp = json.loads(comp_path.read_text(encoding="utf-8")) if comp_path.exists() else None
    if comp is None:
        raise FileNotFoundError(f"缺少八组合对照表：{comp_path}")
    by_policy = {r["policy"]: r for r in comp["rows"]}
    missing = [label(t) for t in rows if label(t) not in by_policy]
    if missing:
        raise KeyError(f"对照表缺少这些策略标签：{missing}")
    for tag, r in rows.items():
        ref = by_policy[label(tag)]
        check(f"[8组合] {label(tag)} 总费用 vs 对照表",
              abs(r["total_cost_yuan"] - ref["total_cost_yuan"]))
    # 独立重算 Shapley：v(S) = 0-only 费用 − S 的费用，效率公理与对照表逐项比对
    sh = shapley(costs)
    for j, v in sh.items():
        key = f"{STAGE_HOUR[str(j)]}:00"
        ref = comp["shapley_savings_vs_0_only_for_full_policy_yuan"][key]
        check(f"[8组合] Shapley({key}) vs 对照表", abs(v - ref), 1e-4)
    check("[8组合] 全启用相对 0-only 的总节省 vs 对照表",
          abs((costs[frozenset()] - costs[frozenset((1, 2, 3))])
              - comp["full_policy_saving_vs_0_only_yuan"]), 1e-4)
    return {"rows": rows, "shapley": sh,
            "saving_full_vs_0only": costs[frozenset()] - costs[frozenset((1, 2, 3))]}


# ----------------------------------------------------------------------
def main() -> int:
    global K, LOAD_PV
    tag = sys.argv[1] if len(sys.argv) > 1 else "0123"
    K = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    print("=" * 92)
    print("第三问独立复算：只读原始附件 + 已落盘明细，不 import src/q3_multistage.py")
    print("=" * 92)

    print("\n0. 原始数据口径")
    price = load_price()
    p_nat = natural_price(price)
    LOAD_PV = load_actual_load_pv()
    print(f"  附件1 电价 {price.shape}  范围 {price.min():.4f}—{price.max():.4f}  "
          f"均值 {price.mean():.4f} 元/kWh")
    print(f"  自然日价格向量 = 附件列右移一位；首段 {p_nat[0]:.4f}（= 附件末列 "
          f"{price[-1]:.4f}），第 2 段 {p_nat[1]:.4f}（= 附件首列 {price[0]:.4f}）")
    assert np.allclose(p_nat[1:], price[: T - 1]), "自然日价格向量构造不自洽"
    l_kwh, g_kwh, adates = LOAD_PV
    print(f"  附件2 负载/光伏 {l_kwh.shape}  日期 {adates[0]} .. {adates[-1]}")

    print("\n1. 主组合 甲+乙 独立复算")
    main_row = verify_combo(tag, p_nat, deep=True)

    print("\n2. 八组合 甲 独立复算 + 独立重算 Shapley")
    combo = verify_all_combos(p_nat)

    print("\n" + "=" * 92)
    if failures:
        print(f"FAILED — {len(failures)} 项超差：")
        for f in failures:
            print("   -", f)
    else:
        print("ALL OK — 所有独立复算项均在容差内")
    print("=" * 92)

    result = {
        "mode": "independent_verify", "K": K, "main_tag": tag,
        "main": main_row, "combos": {k: v for k, v in combo["rows"].items()},
        "shapley": {str(k): v for k, v in combo["shapley"].items()},
        "saving_full_vs_0only": combo["saving_full_vs_0only"],
        "worst": worst_seen, "failures": failures,
    }
    dest = OUT / f"independent_verify_{tag}_K{K}.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {dest}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
