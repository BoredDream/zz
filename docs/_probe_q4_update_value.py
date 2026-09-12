"""量化日内更新在【同一窗口】上的边际价值。

各阶段剩余时段不同，直接比 MAPE 不可比。这里固定窗口 [TSTAGE[m], 144)：
  A = price_hat(d, m)         实际使用的预测（含日内更新）
  B = price_hat(d, 0)         0:00 那版预测，截同一窗口（= 不更新的对照）
  C = PMAT[d-1]               朴素持续（前一日同时段实际）
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import q4_solver as M  # noqa: E402

D0 = 30
print("阶段  窗口        A:含更新      B:0:00版      C:前一日    A vs B")
for m in range(4):
    tm = M.TSTAGE[m]
    ma = mb = mc = 0.0
    win = 0
    for d in range(D0, M.ND):
        a = M.price_hat(d, m)[tm:]
        b = M.price_hat(d, 0)[tm:]
        c = M.PMAT[d - 1][tm:]
        y = M.PMAT[d][tm:]
        ma += np.abs(a - y).mean(); mb += np.abs(b - y).mean(); mc += np.abs(c - y).mean()
        win += 1
    ma, mb, mc = ma / win, mb / win, mc / win
    tag = "↑改善" if ma < mb else "↓变差"
    print("  %d   %3d-%3d   %.4f      %.4f      %.4f     %+.1f%% %s"
          % (m, tm, 144, ma, mb, mc, 100 * (ma - mb) / mb, tag))

# 分时段：更新到底在哪些钟点有用
print("\n按时段看 MAE（含更新 A - 不更新 B），负=更新更好")
for m in range(1, 4):
    tm = M.TSTAGE[m]
    diff = np.zeros(M.T)
    cnt = np.zeros(M.T)
    for d in range(D0, M.ND):
        diff += np.abs(M.price_hat(d, m) - M.PMAT[d]) - np.abs(M.price_hat(d, 0) - M.PMAT[d])
        cnt += 1
    diff /= cnt
    seg = diff[tm:]
    print("  m=%d  更新后: 改善 %d 段 / 变差 %d 段，窗口均值 %+.4f 元/kWh"
          % (m, int((seg < 0).sum()), int((seg > 0).sum()), seg.mean()))
