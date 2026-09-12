"""标定第四问电价预测子模型的误差，供 docs/q4_model.md 引用。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import q4_solver as M  # noqa: E402

D0 = 30  # 留出预热期
print("阶段   MAPE     MAE(元/kWh)   RMSE")
for m in range(4):
    errs, aes, sq = [], [], []
    for d in range(D0, M.ND):
        ph = M.price_hat(d, m)
        e = (ph - M.PMAT[d]) / M.PMAT[d]
        errs.append(np.abs(e).mean())
        aes.append(np.abs(ph - M.PMAT[d]).mean())
        sq.append(((ph - M.PMAT[d]) ** 2).mean())
    print("  %d   %5.2f%%   %.4f        %.4f"
          % (m, 100 * np.mean(errs), np.mean(aes), np.sqrt(np.mean(sq))))

# 朴素基准：用前一日实际电价当作今日预测
naive = np.mean([np.abs(M.PMAT[d-1] - M.PMAT[d]).mean() for d in range(D0, M.ND)])
base = np.mean([M.PMAT[d].mean() for d in range(D0, M.ND)])
print("\n朴素基准（前一日实际, 全天）: MAE %.4f 元/kWh，占日均价 %.1f%%" % (naive, 100 * naive / base))

# 日内自相关，支撑 AR(1) 衰减设定
for lag in (1, 3, 6, 12, 18):
    r = np.corrcoef(M.PMAT[:, :-lag].ravel(), M.PMAT[:, lag:].ravel())[0, 1]
    print("  电价 %2d 步(×10min)滞后自相关 = %.4f" % (lag, r))
