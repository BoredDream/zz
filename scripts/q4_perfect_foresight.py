"""第四问：完美预见电价对照回测，用来拆分第三问 → 第四问的 +5.20%。

要解决的问题
------------
`docs/q4_model.md` 第 9 节与 `reports/project_task_reference.md` C9 都写明：
第三问（13,162,682.8855 元）与第四问 4-3（13,847,794.9401 元）相差 **+5.20%**，
但**不能整体归因于「价格波动」**——两次回测的**可利用信息不同**：

  * 第三问把附件1 的分时电价当作**已知**量送入 LP（附件1 恰是附件4 的逐时段均值，
    逐时段最大差 5.15e-05，属表格取整，故两组可干净对比）；
  * 第四问必须在 0:00 用 `price_hat` **预测**附件4 的波动电价。

所以 +5.20% = (a) 价格波动的风险成本 + (b) 预测误差的信息缺失成本。本脚本补上
那个缺失的对照点：

    完美预见第四问（PF）：把 `price_hat(d, m)` 整个换成**当日实际电价** `PMAT[d]`，
    其余一字不动（同样的负荷/光伏预测与场景、同样的 λ=0.478、同样的实时层与滚动时域）。

三个点的差值给出干净分解：

    (a) 价格波动风险成本 = C(Q4-PF) − C(Q3)          ← 两边都「已知价格」，只差价格过程本身
    (b) 预测误差信息缺失 = C(Q4-3) − C(Q4-PF)        ← 价格过程相同，只差「知不知道」
    (a) + (b) = C(Q4-3) − C(Q3) = +5.20%

做法
----
**不修改 `src/`**：只替换 `q4_solver` 模块命名空间里的 `price_hat` 一个名字。
注意 `scenarios4()` 也调用 `price_hat(dd, m)` 取历史日的价格预测来构造乘性残差
`ratio = PMAT[dd] / price_hat(dd, m)`；替换后 `ratio ≡ 1`，价格情景退化为
「全部等于当日实际电价」。这正是「完美预见」的应有含义：价格维度无不确定性，
负荷/光伏维度仍按原样抽样。

冷启动：d=0 时原 `price_hat` 用附件1 的 `P` 作显式先验（附件4 无历史），
本脚本保持不变——该约定只影响 1 月预热期，交付期统计不含它。

用法
----
    python scripts/q4_perfect_foresight.py [K]          # K 默认 30，跑一次约 505 s
    python scripts/q4_perfect_foresight.py enrich [K]   # 只补「期末存量转移」字段，约 2 s

整跑结束时会自动调用一次 `enrich()`；`enrich` 单独可用，便于给已落盘的结果补字段
而不必重跑回测。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import q4_solver as M  # noqa: E402

OUT = ROOT / "outputs" / "q4"
Q3_OUT = ROOT / "outputs" / "q3_multistage"
DELIVERY_START = "2025-02-01"
K_DEFAULT = 30

_ORIG_PRICE_HAT = M.price_hat


def use_actual_price() -> None:
    """把电价预测换成当日实际电价（模板行口径，与 price_hat 的返回口径一致）。"""
    def price_hat(d, m):
        # price_hat 返回 **144 长、模板行口径** 的向量（第 t 项覆盖 [(t+1)*10,(t+2)*10)），
        # 故「实际电价」就是 PMAT[d] 本身；d=0 沿用附件1 冷启动先验。
        return M.PMAT[d].copy() if d > 0 else M.P.copy()
    M.price_hat = price_hat


def inventory_contamination(k: int = K_DEFAULT) -> dict:
    """把「(a)/(b) 里含多少期末存量转移」算清楚。

    λ 是终端储能的**影子价值**（1 kWh 留在期末值 λ 元），故两个对照点的期末存量差
    ΔS 在目标函数里正好值 `λ·ΔS` 元。这部分是**存量转移**而非效率差异，
    会混进 (a)/(b)，必须单独报出来，否则等于把「多留了电」当成「省了钱」。

    只读已落盘的 npz 与 JSON，不重跑回测。
    """
    q3_npz = Q3_OUT / f"detail_stages0123_K{k}.npz"
    q4_npz = OUT / f"detail_q4-3_K{k}.npz"
    pf_json = OUT / f"perfect_foresight_q4_K{k}.json"
    if not (q3_npz.exists() and q4_npz.exists() and pf_json.exists()):
        return {}

    lam = float(json.loads(pf_json.read_text(encoding="utf-8"))["meta"]["lambda_kept"])
    s_q4 = float(np.load(q4_npz, allow_pickle=True)["S"][-1, -1])
    s_q3 = float(np.load(q3_npz, allow_pickle=True)["S"][-1, -1])
    s_pf = float(json.loads(pf_json.read_text(encoding="utf-8"))["soc_end_delivery_kwh"])
    d = json.loads(pf_json.read_text(encoding="utf-8"))["decomposition"]
    a_gap = d["a_price_volatility_risk_cost_yuan"]
    b_gap = d["b_forecast_error_information_loss_yuan"]
    return {
        "lambda_used_for_valuation_yuan_per_kwh": lam,
        "terminal_soc_kwh": {"q3": s_q3, "q4_3": s_q4, "perfect_foresight": s_pf},
        "a_stock_transfer_yuan": lam * (s_pf - s_q3),
        "a_stock_transfer_pct_of_gap": 100.0 * abs(lam * (s_pf - s_q3)) / abs(a_gap) if a_gap else None,
        "b_stock_transfer_yuan": lam * (s_pf - s_q4),
        "b_stock_transfer_pct_of_gap": 100.0 * abs(lam * (s_pf - s_q4)) / abs(b_gap) if b_gap else None,
        "a_pure_efficiency_yuan": a_gap - lam * (s_pf - s_q3),
        "b_pure_efficiency_yuan": b_gap - lam * (s_pf - s_q4),
    }


def enrich(k: int = K_DEFAULT) -> int:
    """给已落盘的 PF JSON 补上「存量转移」字段，不重跑回测。"""
    pf_json = OUT / f"perfect_foresight_q4_K{k}.json"
    if not pf_json.exists():
        print(f"缺少 {pf_json}，请先跑一次回测")
        return 1
    r = json.loads(pf_json.read_text(encoding="utf-8"))
    r["inventory_contamination"] = inventory_contamination(k)
    pf_json.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    ic = r["inventory_contamination"]
    print(json.dumps(ic, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "enrich":
        return enrich(int(sys.argv[2]) if len(sys.argv) > 2 else K_DEFAULT)
    K = int(sys.argv[1]) if len(sys.argv) > 1 else K_DEFAULT
    print("=" * 96)
    print("第四问完美预见电价对照（只替换 q4_solver.price_hat，不修改 src/）")
    print("=" * 96)

    use_actual_price()
    t0 = time.perf_counter()
    rec, _ = M.backtest4(0, M.ND, K=K, stages=(0, 1, 2, 3), S0=6000.0, verbose=True)
    elapsed = time.perf_counter() - t0

    days = sorted(rec)
    start = M.DSTR.index(DELIVERY_START)
    keys = ("total_cost_yuan", "plan_cost_yuan", "adjust_cost_yuan", "emergency_cost_yuan",
            "emergency_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh",
            "adjust_up_kwh", "adjust_down_kwh")
    totals = {k: 0.0 for k in keys}
    soc_end = []
    for i in range(start, len(days)):
        r = rec[days[i]]
        n = r["natural"]
        sp, sa, se = M.natural_settle_parts4(days[i], r["natural_x"], r["natural_q"], n["z"])
        up = float(np.maximum(r["natural_q"] - r["natural_x"], 0).sum())
        dn = float(np.maximum(r["natural_x"] - r["natural_q"], 0).sum())
        for k, v in (("total_cost_yuan", float(sp.sum() + sa.sum() + se.sum())),
                     ("plan_cost_yuan", float(sp.sum())), ("adjust_cost_yuan", float(sa.sum())),
                     ("emergency_cost_yuan", float(se.sum())), ("emergency_kwh", float(n["z"].sum())),
                     ("charge_kwh", float(n["c"].sum())), ("discharge_kwh", float(n["g"].sum())),
                     ("curtail_kwh", float(n["w"].sum())), ("adjust_up_kwh", up), ("adjust_down_kwh", dn)):
            totals[k] += v
        soc_end.append(float(r["S24"]))

    # ---- 三个对照点 ----
    c_pf = totals["total_cost_yuan"]
    q4_path = OUT / f"summary_q4-3_K{K}.json"
    q3_path = Q3_OUT / f"summary_stages0123_K{K}.json"
    c_q4 = float(json.loads(q4_path.read_text(encoding="utf-8"))["totals"]["total_cost_yuan"]) \
        if q4_path.exists() else None
    c_q3 = float(json.loads(q3_path.read_text(encoding="utf-8"))["totals"]["total_cost_yuan"]) \
        if q3_path.exists() else None

    decomp = {}
    if c_q3 is not None and c_q4 is not None:
        decomp = {
            "c_q3_deterministic_price_known_yuan": c_q3,
            "c_q4_PF_volatile_price_known_yuan": c_pf,
            "c_q4_3_volatile_price_forecast_yuan": c_q4,
            "a_price_volatility_risk_cost_yuan": c_pf - c_q3,
            "a_pct_of_q3": (c_pf / c_q3 - 1.0) * 100.0,
            "b_forecast_error_information_loss_yuan": c_q4 - c_pf,
            "b_pct_of_q3": ((c_q4 - c_pf) / c_q3) * 100.0,
            "total_gap_yuan": c_q4 - c_q3,
            "total_gap_pct_of_q3": (c_q4 / c_q3 - 1.0) * 100.0,
            "identity_residual_yuan": abs((c_pf - c_q3) + (c_q4 - c_pf) - (c_q4 - c_q3)),
        }

    result = {
        "meta": {
            "purpose": "完美预见电价对照：拆分第三问→第四问的 +5.20%",
            "method": "只替换 q4_solver.price_hat 为当日实际电价；负荷/光伏场景、λ、实时层、"
                      "滚动时域均不变",
            "lambda_kept": M.LAM,
            "lambda_note": "λ 保持 0.478（与 4-3 一致），以免横向比较混入终端价值变化",
            "price_convention": "模板行口径 144 长；d=0 沿用附件1 冷启动先验",
            "stages": [0, 1, 2, 3], "K": K, "S0": 6000.0,
            "delivery_start": DELIVERY_START, "delivery_end": M.DSTR[days[-1]],
            "delivery_days": len(days) - start,
            "elapsed_seconds": elapsed,
        },
        "totals": totals,
        "decomposition": decomp,
        "soc_end_mean_daily_kwh": float(np.mean(soc_end)),
        "soc_end_delivery_kwh": soc_end[-1],
        "src_unmodified": True,
    }
    dest = OUT / f"perfect_foresight_q4_K{K}.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # 先落盘，再补「存量转移」对照（它要读上面这份 JSON 与两个 npz）
    enrich(K)

    print(json.dumps({"total_cost_yuan": round(c_pf, 4),
                      "elapsed_seconds": round(elapsed, 1)}, ensure_ascii=False))
    if decomp:
        print("\n分解（单位：元）：")
        print(f"  第三问  确定性电价·已知   {decomp['c_q3_deterministic_price_known_yuan']:>18,.4f}")
        print(f"  第四问  波动电价·完美预见 {decomp['c_q4_PF_volatile_price_known_yuan']:>18,.4f}"
              f"   (a) 波动风险 {decomp['a_price_volatility_risk_cost_yuan']:>+14,.4f}"
              f"  {decomp['a_pct_of_q3']:+.3f}%")
        print(f"  第四问  波动电价·预测     {decomp['c_q4_3_volatile_price_forecast_yuan']:>18,.4f}"
              f"   (b) 信息缺失 {decomp['b_forecast_error_information_loss_yuan']:>+14,.4f}"
              f"  {decomp['b_pct_of_q3']:+.3f}%")
        print(f"  合计                                                  "
              f"   {decomp['total_gap_yuan']:>+14,.4f}  {decomp['total_gap_pct_of_q3']:+.3f}%")
        print(f"  恒等式残差 {decomp['identity_residual_yuan']:.3e} 元")
    print(f"\n-> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
