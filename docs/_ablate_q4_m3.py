"""消融：18:00 的日内电价更新到底帮了还是害了（按费用，不按 MAE）。

在同一批日子里跑两次变体 4-3，唯一差别是 m=3 阶段用哪版电价预测：
  A 基线   price_hat(d, 3)     含 18:00 更新
  B 消融   price_hat(d, 0)     18:00 不更新，沿用 0:00 那版预测
结算一律用实际电价 PMAT[d]，故两次的费用可直接比。

用法： python docs/_ablate_q4_m3.py [d0] [d1]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import q4_solver as M  # noqa: E402

_real_price_hat = M.price_hat


def run(d0: int, d1: int, freeze_m3: bool, K: int = 30):
    if freeze_m3:
        M.price_hat = lambda d, m: _real_price_hat(d, 0) if m == 3 else _real_price_hat(d, m)
    else:
        M.price_hat = _real_price_hat
    M._PHAT_CACHE.clear()
    rec, _ = M.backtest4(d0, d1, K=K, stages=(0, 1, 2, 3), S0=6000.0)
    return sum(M.day_cost4(d, r["x"], r["q"], r)[0] for d, r in rec.items()), rec


if __name__ == "__main__":
    d0 = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    d1 = int(sys.argv[2]) if len(sys.argv) > 2 else 240
    print(f"样本 {M.DSTR[d0]} .. {M.DSTR[d1-1]}（{d1-d0} 天，K=30，变体4-3）")
    a_cost, a_rec = run(d0, d1, freeze_m3=False)
    b_cost, b_rec = run(d0, d1, freeze_m3=True)
    print(f"  A 含 18:00 更新 : {a_cost:>14,.2f} 元")
    print(f"  B 冻结 0:00 版  : {b_cost:>14,.2f} 元")
    print(f"  差 (A-B)        : {a_cost-b_cost:>+14,.2f} 元  "
          f"({100*(a_cost-b_cost)/b_cost:+.2f}%)  {'更新有害' if a_cost > b_cost else '更新有益'}")
    adj_a = sum(np.abs(a_rec[d]["q"] - a_rec[d]["x"]).sum() for d in a_rec)
    adj_b = sum(np.abs(b_rec[d]["q"] - b_rec[d]["x"]).sum() for d in b_rec)
    emg_a = sum(a_rec[d]["z"].sum() for d in a_rec)
    emg_b = sum(b_rec[d]["z"].sum() for d in b_rec)
    print(f"  |q-x| 合计      : A {adj_a:,.1f} / B {adj_b:,.1f} kWh")
    print(f"  紧急购电        : A {emg_a:,.1f} / B {emg_b:,.1f} kWh")
