# -*- coding: utf-8 -*-
"""图 4a　预测误差的日内分布与逐月平均绝对误差（上下双面板）
================================================================================
核心任务
    预测误差的日内分布有无系统性偏置？哪个月误差最大？（模型的误差体检）

信息结构
    · 上面板：按时刻分组的箱线图（24 个箱）
        箱体 = 四分位距（灰蓝，对照语义）；中线 = 中位数（深蓝灰，被强调）
        须 = 非离群极值；深灰水平线 = 无偏基准线（误差 0）
        并标注"正 = 实际高于预测（缺电风险侧）/ 负 = 实际低于预测（剩余电量侧）"
    · 下面板：逐月平均绝对误差柱，最差月染赤陶，虚线为全期均值

口径说明
    逐月 MAE 由 48,096 条明细逐时段现算，与素材包 §F3 的引用值一致
    （6 月 84.14 kWh/10 分钟为最高月）。

数据源
    outputs/q2/interval_detail.csv（误差 = actual_net_kwh − forecast_net_kwh）
================================================================================
"""
from __future__ import annotations

try:
    from ._common import (C_ACCENT, C_ACT, C_GREY, C_GREY_L, C_MAIN_D, C_TEXT,
                          FONT, LS_ALT, RC, detail, save, style)
except ImportError:
    from _common import (C_ACCENT, C_ACT, C_GREY, C_GREY_L, C_MAIN_D, C_TEXT,
                         FONT, LS_ALT, RC, detail, save, style)

from collections import defaultdict

import numpy as np
import matplotlib
import matplotlib.pyplot as plt


def fig4a() -> dict:
    """绘制图4a，返回 {"files": …, "meta": …}。"""
    rows = detail()
    err_hour: dict = defaultdict(list)
    err_month: dict = defaultdict(list)
    for r in rows:
        e = float(r["actual_net_kwh"]) - float(r["forecast_net_kwh"])
        h = 24 if r["time_start"] == "24:00" else int(r["time_start"][:2])
        err_hour[h].append(e)
        err_month[r["date"][:7]].append(e)

    hours = sorted(err_hour)
    data = [np.array(err_hour[h]) for h in hours]
    months = sorted(err_month)
    mae_m = np.array([float(np.abs(np.array(err_month[m])).mean()) for m in months])
    all_e = np.array([e for v in err_hour.values() for e in v])
    imax = int(np.argmax(mae_m))
    mae_all = float(np.abs(all_e).mean())

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(7.1, 4.7),
            gridspec_kw={"height_ratios": [1.75, 1.0], "hspace": 0.46})

        # ---------------- 上面板：误差的日内箱线图 ----------------
        ax1.boxplot(data, positions=hours, widths=0.62, showfliers=False,
                    patch_artist=True,
                    medianprops=dict(color=C_MAIN_D, lw=1.4),
                    whiskerprops=dict(color=C_GREY, lw=0.8),
                    capprops=dict(color=C_GREY, lw=0.8),
                    boxprops=dict(facecolor=C_GREY_L, alpha=0.75,
                                  edgecolor=C_GREY, lw=0.7))
        ax1.axhline(0, color=C_ACT, lw=1.2, zorder=5)
        ax1.annotate("正：实际高于预测（缺电风险侧）", xy=(0.4, 330), fontsize=7.8,
                     color=C_ACCENT, zorder=9)
        ax1.annotate("负：实际低于预测（剩余电量侧）", xy=(0.4, -430), fontsize=7.8,
                     color=C_MAIN_D, zorder=9)
        ax1.set_ylabel("预测误差 / (kWh/10分钟)")
        ax1.set_xticks(hours)
        ax1.set_xticklabels([str(h) for h in hours], fontsize=7.5)
        ax1.set_xlabel("时刻 / 时")
        ax1.set_ylim(-480, 480)
        style(ax1)
        ax1.set_title(f"(a) 预测误差（实际−预测）的日内分布　全期 MAE "
                      f"{mae_all:.2f}、偏置 {all_e.mean():+.2f} kWh/10分钟",
                      pad=5, fontsize=9)

        # ---------------- 下面板：逐月 MAE ----------------
        cols = [C_ACCENT if i == imax else C_GREY for i in range(len(months))]
        ax2.bar(np.arange(len(months)), mae_m, width=0.62, color=cols, alpha=0.90,
                zorder=3)
        ax2.axhline(mae_all, color=C_ACT, lw=1.1, ls=LS_ALT, zorder=5)
        ax2.annotate(f"全期 MAE {mae_all:.2f}", xy=(len(months) - 0.5, mae_all),
                     xytext=(0, 5), textcoords="offset points", ha="right",
                     fontsize=7.8, color=C_TEXT, zorder=9)
        ax2.annotate(f"最高 {mae_m[imax]:.1f}", xy=(imax, mae_m[imax]),
                     xytext=(0, 5), textcoords="offset points", ha="center",
                     fontsize=7.8, color=C_ACCENT, zorder=9)
        ax2.set_xticks(np.arange(len(months)))
        ax2.set_xticklabels([m[5:] + "月" for m in months])
        ax2.set_ylabel("MAE / (kWh/10分钟)")
        ax2.set_xlabel("月份")
        ax2.set_ylim(0, mae_m.max() * 1.24)
        style(ax2)
        ax2.set_title("(b) 逐月平均绝对误差", pad=5, fontsize=9)
        fig.tight_layout()
        out = save(fig, "fig4a_forecast_error")

    return {"files": out, "meta": {
        "n_intervals": len(rows),
        "mae_kwh_per_interval": mae_all,
        "rmse_kwh_per_interval": float(np.sqrt((all_e ** 2).mean())),
        "bias_kwh_per_interval": float(all_e.mean()),
        "worst_month": months[imax], "worst_month_mae": float(mae_m[imax]),
        "monthly_mae": {m: float(v) for m, v in zip(months, mae_m)},
    }}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig4a()
    print(f"[图4a] 预测误差日内分布与逐月 MAE  字体 {FONT}")
    for k, v in res["meta"].items():
        if k != "monthly_mae":
            print(f"   {k} = {v}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
