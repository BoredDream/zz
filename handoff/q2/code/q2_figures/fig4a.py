# -*- coding: utf-8 -*-
"""图 4a　预测误差的日内分布与各月平均绝对误差（上下双面板）
================================================================================
核心任务（本图只回答两个问题，不承担解释性文字）
    (a) 预测误差在一天 24 小时内如何分布，是否存在系统性偏差？
    (b) 各月的平均绝对误差有何差异，哪个月误差最大？

信息结构（共享 x 轴，上 65% / 下 35%）
    · 上面板：24 组误差箱线图
        箱体 = 四分位距（浅灰蓝）；中线 = 中位数（深蓝灰，被强调）；
        须/帽 = 浅灰；不显示离群点（showfliers=False）
        y=0 保留一条稍深的基准线，**代替**原先图内的"正/负"方向文字说明
    · 下面板：各月 MAE 柱状图
        普通月份低饱和灰蓝；**只有 6 月染赤陶**（全图唯一被强调的月份）
        全期 MAE 用一条水平虚线表示，其标注**全图只出现一次**

刻意从图内删除的内容（消除重复信息与文字堆叠）
    · 标题里的 "全期 MAE 61.29、偏置 -9.45" —— 移入图注与正文
    · 图内文字 "正：实际高于预测（缺电风险侧）" / "负：实际低于预测（剩余电量侧）"
      —— y=0 基准线与图注已足够说明
    · 上面板中重复的 "全期 MAE 61.29" —— 只在下面板保留一次
    · 平均偏置 -9.45 —— **完全不出现在图内**
    · 6 月柱顶的 "最高 84.1" —— 只留数值 "84.1"，"最高"由图注承担

口径说明
    · 全期 MAE / RMSE / 偏置与逐月 MAE 均由 48,096 条明细逐时段现算，
      未平滑、未插值、未修改任何统计量（重构前后已逐项比对一致）
    · 误差定义：实际 − 预测（actual_net_kwh − forecast_net_kwh）
    · 小时归组：按 time_start 的整点部分；'24:00' 归入第 24 组，
      交付期该组无样本，故箱体位于 0–23 时（这是数据事实，非绘图遗漏）

数据源
    outputs/q2/interval_detail.csv（逐时段明细，48,096 条）
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

# x 轴刻度：24 组箱体全部标数字会拥挤；按 3 小时一档并在末端补 23
X_TICKS = [0, 3, 6, 9, 12, 15, 18, 21, 23]


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
            2, 1, figsize=(7.1, 4.8),
            gridspec_kw={"height_ratios": [1.8, 1.0], "hspace": 0.42})

        # ---------------- 上面板：误差的日内箱线图 ----------------
        ax1.boxplot(data, positions=hours, widths=0.62, showfliers=False,
                    patch_artist=True,
                    medianprops=dict(color=C_MAIN_D, lw=1.4),
                    whiskerprops=dict(color=C_GREY, lw=0.8),
                    capprops=dict(color=C_GREY, lw=0.8),
                    boxprops=dict(facecolor=C_GREY_L, alpha=0.75,
                                  edgecolor=C_GREY, lw=0.7))
        ax1.axhline(0, color=C_ACT, lw=1.1, zorder=5)   # y=0 基准线，替代正/负文字说明
        ax1.set_ylabel("预测误差 / (kWh/10分钟)")
        ax1.set_xlim(-0.8, 24.8)
        ax1.set_xticks(X_TICKS)
        ax1.set_xticklabels([str(h) for h in X_TICKS])
        ax1.set_xlabel("时刻 / 时")
        ax1.set_ylim(-480, 480)
        style(ax1)
        # 标题只留面板名；全期 MAE / 偏置一律不进标题
        ax1.set_title("(a) 预测误差的日内分布", pad=5, fontsize=9)

        # ---------------- 下面板：各月 MAE ----------------
        cols = [C_ACCENT if i == imax else C_GREY for i in range(len(months))]
        ax2.bar(np.arange(len(months)), mae_m, width=0.62, color=cols, alpha=0.90,
                zorder=3)
        ax2.axhline(mae_all, color=C_ACT, lw=1.1, ls=LS_ALT, zorder=5)
        # 顶部留出空白，避免标注与面板标题、与柱顶相互挤压
        ax2.set_ylim(0, mae_m.max() * 1.30)
        # 全期 MAE 标注：全图仅此一处；放在虚线右上方空白区，紧贴虚线不压柱
        ax2.annotate(f"全期 MAE {mae_all:.2f}",
                     xy=(len(months) - 0.4, mae_all), xytext=(0, 5),
                     textcoords="offset points", ha="right", va="bottom",
                     fontsize=7.8, color=C_TEXT, zorder=9)
        # 6 月柱顶只留数值，"最高"由图注承担
        ax2.annotate(f"{mae_m[imax]:.1f}", xy=(imax, mae_m[imax]), xytext=(0, 4),
                     textcoords="offset points", ha="center", va="bottom",
                     fontsize=7.8, color=C_ACCENT, zorder=9)
        ax2.set_xticks(np.arange(len(months)))
        ax2.set_xticklabels([f"{int(m[5:7])}月" for m in months])   # "2月" 而非 "02月"
        ax2.set_ylabel("MAE / (kWh/10分钟)")
        ax2.set_xlabel("月份")
        ax2.set_xlim(-0.7, len(months) - 0.3)
        style(ax2)
        ax2.set_title("(b) 各月平均绝对误差", pad=5, fontsize=9)

        fig.tight_layout()
        out = save(fig, "fig4a_forecast_error")

    return {"files": out, "meta": {
        "n_intervals": len(rows),
        "mae_kwh_per_interval": mae_all,
        "rmse_kwh_per_interval": float(np.sqrt((all_e ** 2).mean())),
        "bias_kwh_per_interval": float(all_e.mean()),
        "worst_month": months[imax], "worst_month_mae": float(mae_m[imax]),
        "best_month": months[int(np.argmin(mae_m))],
        "monthly_mae": {m: float(v) for m, v in zip(months, mae_m)},
        "hours_with_boxes": hours,
        "box_stats_by_hour": {
            h: {"n": int(len(err_hour[h])),
                "q1": float(np.percentile(err_hour[h], 25)),
                "median": float(np.percentile(err_hour[h], 50)),
                "q3": float(np.percentile(err_hour[h], 75))}
            for h in hours},
    }}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig4a()
    print(f"[图4a] 预测误差的日内分布与各月平均绝对误差  字体 {FONT}")
    for k, v in res["meta"].items():
        if k not in ("monthly_mae", "box_stats_by_hour"):
            print(f"   {k} = {v}")
    print(f"   最高月复核 = {res['meta']['monthly_mae'][res['meta']['worst_month']]:.10f}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
