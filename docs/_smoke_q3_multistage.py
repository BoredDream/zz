"""改口径后的冒烟测试：逐时段核对 SOC 递推、功率平衡、上下限与费用拆分。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import q3_multistage as M  # noqa: E402

rec, _ = M.backtest(55, 59, K=8, verbose=False)
worst = {"soc": 0.0, "bal": 0.0, "c_max": 0.0, "g_max": 0.0, "s_lo": 0.0, "s_hi": 0.0, "cost": 0.0}
for d, r in rec.items():
    S_prev = r["S0"]
    for t in range(M.T):
        S_now = r["S"][t]
        soc_res = S_now - (S_prev + M.ETA * r["c"][t] - r["g"][t] / M.ETA)
        bal = r["q"][t] + r["z"][t] + r["g"][t] - r["c"][t] - r["w"][t] - (M.L[d][t] - M.G[d][t])
        worst["soc"] = max(worst["soc"], abs(soc_res))
        worst["bal"] = max(worst["bal"], abs(bal))
        worst["c_max"] = max(worst["c_max"], r["c"][t] - M.CMAX)
        worst["g_max"] = max(worst["g_max"], r["g"][t] - M.CMAX)
        worst["s_lo"] = max(worst["s_lo"], M.SMIN - S_now)
        worst["s_hi"] = max(worst["s_hi"], S_now - M.SMAX)
        S_prev = S_now
        assert r["c"][t] >= -1e-9 and r["g"][t] >= -1e-9 and r["z"][t] >= -1e-9 and r["w"][t] >= -1e-9
    tot, pa, _ = M.day_cost(r["x"], r["q"], r)
    s1, s2, s3 = M.settle_parts(r["x"], r["q"], r["z"])
    worst["cost"] = max(worst["cost"], abs(tot - (s1.sum() + s2.sum() + s3.sum())))

print("最大残差：")
for k, v in worst.items():
    print(f"  {k:>6} = {v:.3e}")
print(f"\nCMAX = {M.CMAX:.4f} kWh/时段 (母线侧)")
for d, r in list(rec.items())[:2]:
    print(f"\n{M.DSTR[d]}  S0(0:10)={r['S0']:.1f}  S[142](24:00)={r['S'][142]:.1f}  S[143](次日0:10)={r['S'][143]:.1f}")
    print(f"  充电 {r['c'].sum():9.1f}  放电(母线) {r['g'].sum():9.1f}  放电(电池侧等价) {r['g'].sum()/M.ETA:9.1f}")
    print(f"  紧急 {r['z'].sum():9.1f}  弃电 {r['w'].sum():9.1f}  max c={r['c'].max():.2f} max g={r['g'].max():.2f}")
    print(f"  计划 {r['x'].sum():9.1f}  调整后 {r['q'].sum():9.1f}  |q-x| {np.abs(r['q']-r['x']).sum():9.1f}")
    print(f"  费用 {M.day_cost(r['x'], r['q'], r)[0]:,.0f} 元")
    print("  时刻标签:", [M.interval_label(t) for t in (0, 1, 142, 143)])
    print("  紧急段:", M.emergency_segments(r["z"])[:3])
assert worst["soc"] < 1e-6 and worst["bal"] < 1e-6 and worst["cost"] < 1e-6
print("\nOK 全部不变量通过")
