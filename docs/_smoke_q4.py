"""问题4 模型的冒烟测试：两个变体各跑几天，核对物理不变量与费用拆分。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import q4_solver as M  # noqa: E402
import q3_multistage as Q3  # noqa: E402

print("附件4 电价矩阵:", M.PMAT.shape, "均价 %.4f" % M.PMAT.mean())
for m in (0, 1, 2, 3):
    ph = M.price_hat(120, m)
    err = np.abs(ph - M.PMAT[120]) / M.PMAT[120]
    print(f"  price_hat(m={m}) MAPE(该日) = {err.mean()*100:5.2f}%  电平 {ph.mean():.4f}")
    print(f"    water_value = {M.water_value(ph):.4f} 元/kWh")

for which, stages in (("2", (0,)), ("3", (0, 1, 2, 3))):
    rec, _ = M.backtest4(55, 59, K=8, stages=stages, verbose=False)
    worst = {k: 0.0 for k in ("soc", "bal", "c_max", "g_max", "s_lo", "s_hi", "cost")}
    for d, r in rec.items():
        prev = r["S0"]
        for t in range(M.T):
            now = r["S"][t]
            worst["soc"] = max(worst["soc"], abs(now - (prev + M.ETA*r["c"][t] - r["g"][t]/M.ETA)))
            worst["bal"] = max(worst["bal"], abs(r["q"][t] + r["z"][t] + r["g"][t] - r["c"][t]
                                                 - r["w"][t] - (M.L[d][t] - M.G[d][t])))
            worst["c_max"] = max(worst["c_max"], r["c"][t] - M.CMAX)
            worst["g_max"] = max(worst["g_max"], r["g"][t] - M.CMAX)
            worst["s_lo"] = max(worst["s_lo"], M.SMIN - now)
            worst["s_hi"] = max(worst["s_hi"], now - M.SMAX)
            prev = now
        tot, _, _ = M.day_cost4(d, r["x"], r["q"], r)
        p1, p2, p3 = M.settle_parts4(d, r["x"], r["q"], r["z"])
        worst["cost"] = max(worst["cost"], abs(tot - (p1.sum()+p2.sum()+p3.sum())))
    print(f"\n=== 变体 4-{which}  stages={stages} ===")
    for k, v in worst.items():
        print(f"  {k:>6} = {v:.3e}")
    assert worst["soc"] < 1e-6 and worst["bal"] < 1e-6 and worst["cost"] < 1e-6
    d = sorted(rec)[0]
    r = rec[d]
    print(f"  {M.DSTR[d]}  |q-x| 合计 {np.abs(r['q']-r['x']).sum():9.1f} kWh"
          f"  (变体4-2 应恒为 0)")
    if which == "2":
        assert np.abs(r["q"] - r["x"]).max() < 1e-9, "变体4-2 的 q 应恒等于 x"
    print("  段标签:", [b["time_range"] for b in M.storage_blocks(r["c"], r["g"])])
    print("  紧急段:", M.emergency_segments(r["z"])[:2])
    print(f"  总费用 {M.day_cost4(d, r['x'], r['q'], r)[0]:,.0f} 元")
print("\nOK 全部不变量通过")
