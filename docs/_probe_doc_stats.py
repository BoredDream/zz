"""核验建模文档中声称的统计量：附件3预报误差RMSE（按提前期）、负载周周期/自相关/月水平/日内形状。"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from q3_solver import ISSUE_LABELS, load_q3_inputs, Q3Config  # noqa: E402

data_dir = Path(__file__).resolve().parent.parent / "problem" / "data"
inputs = load_q3_inputs(data_dir, Q3Config())
fc = inputs["pv_forecast_kw"]          # (365,4,24) kW，附件3整点预报
pv = inputs["pv_actual_kw"]            # (365,144) kW，自然日口径（NaN：1/1 00:00）
load = inputs["load_actual_kw"]
days = inputs["dates"]

print("=" * 92)
print("1. 附件3 光伏预报误差 RMSE (kW)：发布时刻 × 提前期")
print("=" * 92)
ISSUE_HOURS = [0, 6, 12, 18]
LEADS = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 13]
print(f"{'发布':>6} |" + "".join(f"{f'{k}h':>8}" for k in LEADS))
for si, label in enumerate(ISSUE_LABELS):
    row = []
    for lead in LEADS:
        tgt = ISSUE_HOURS[si] + lead
        shift, hour = divmod(tgt, 24)
        errs = [fc[d, si, lead - 1] - pv[d + shift, hour * 6] for d in range(365 - shift)]
        row.append(float(np.sqrt(np.nanmean(np.square(errs)))))
    print(f"{label:>6} |" + "".join(f"{v:8.0f}" for v in row))

print()
print("=" * 92)
print("2. 负载统计特征")
print("=" * 92)
dow = np.array([(date(2025, 1, 1) + timedelta(days=i)).weekday() for i in range(365)])
names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
daily_mean = np.nanmean(load, axis=1)
print("各星期平均负载 (kW): " + ", ".join(f"{names[w]}={np.nanmean(daily_mean[dow == w]):.0f}" for w in range(7)))
wknd = (dow == 4) | (dow == 5)
print(f"周五+周六均值 = {np.nanmean(daily_mean[wknd]):.0f} kW ; 其余5天 = {np.nanmean(daily_mean[~wknd]):.0f} kW"
      f"  （相差 {100 * (1 - np.nanmean(daily_mean[wknd]) / np.nanmean(daily_mean[~wknd])):.0f}%）")

daily_energy = np.nansum(load, axis=1) / 6.0
print(f"日电量 lag-1 自相关 = {np.corrcoef(daily_energy[1:], daily_energy[:-1])[0, 1]:.3f}")
print(f"日电量 lag-7 自相关 = {np.corrcoef(daily_energy[7:], daily_energy[:-7])[0, 1]:.3f}")

month = np.array([(date(2025, 1, 1) + timedelta(days=i)).month for i in range(365)])
print("各月平均负载 (kW): " + ", ".join(f"{m}月={np.nanmean(daily_mean[month == m]):.0f}" for m in range(1, 13)))

shape = load / np.nanmean(load, axis=1, keepdims=True)
print(f"归一化日内曲线跨日标准差（144时段平均） = {np.nanstd(shape, axis=0).mean():.4f}")

print()
print("=" * 92)
print("3. 光伏 / 净负荷极值")
print("=" * 92)
print(f"光伏实际峰值 = {np.nanmax(pv):.0f} kW ; 负载峰值 = {np.nanmax(load):.0f} kW")
print(f"光伏预报峰值 = {fc.max():.0f} kW")
net = load - pv
print(f"净负荷最小 = {np.nanmin(net):.0f} kW ; 最大 = {np.nanmax(net):.0f} kW")

print()
print("=" * 92)
print("4. 同一目标时刻 13:00 的预报精度随发布时刻的改进")
print("=" * 92)
for si, label in enumerate(ISSUE_LABELS):
    lead = 13 - ISSUE_HOURS[si]
    if 1 <= lead <= 24:
        errs = [fc[d, si, lead - 1] - pv[d, 13 * 6] for d in range(365)]
        print(f"  {label} 发布、提前{lead:2d}h、目标13:00：RMSE = {np.sqrt(np.mean(np.square(errs))):7.1f} kW")
    else:
        print(f"  {label} 发布：13:00 已过去或超出24h视野")
