# -*- coding: utf-8 -*-
"""图 2b　月度购电量构成与紧急购电占比（上下双面板）
================================================================================
核心任务
    全期 334 天的购电量按月如何分布？紧急购电是否可控、集中在哪里？

信息结构
    · 上面板：堆叠柱 —— 计划购电量（深蓝灰）+ 紧急购电量（赤陶强调）
    · 下面板：仅紧急购电占比（%），最高月染赤陶，虚线为全期均值

为什么下面板用占比而不是绝对值
    紧急购电量相对计划量极小（全期占比 1.2733%），绝对值在图上看不见；
    用占比才能看出月间差异（最高 3.0991% / 最低 0.4129%）。

数据源
    _figdata/monthly_summary.csv（由 code/gen_plot_data.py 从
    outputs/q2/daily_metrics.csv 按月加总，自然日口径）
================================================================================
"""
from __future__ import annotations

try:
    from ._common import (C_ACCENT, C_ACT, C_GREY, C_GREY_L, C_MAIN, DATA,
                          FONT, LS_ALT, RC, rd, save, style)
except ImportError:
    from _common import (C_ACCENT, C_ACT, C_GREY, C_GREY_L, C_MAIN, DATA,
                         FONT, LS_ALT, RC, rd, save, style)

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter


def fig2b() -> dict:
    """绘制图2b，返回 {"files": …, "meta": …}。"""
    rows = rd(DATA / "monthly_summary.csv")
    months = [r["month"][5:] + "月" for r in rows]
    plan = np.array([float(r["plan_kwh"]) for r in rows])
    em = np.array([float(r["emergency_kwh"]) for r in rows])
    share = np.array([float(r["emergency_share_pct"]) for r in rows])
    x = np.arange(len(rows))
    imax = int(np.argmax(em))
    mean = float(share.mean())

    with matplotlib.rc_context(RC):
        fig, (ax, axr) = plt.subplots(
            2, 1, figsize=(7.1, 4.3), sharex=True,
            gridspec_kw={"height_ratios": [1.85, 1.0], "hspace": 0.16})

        ax.bar(x, plan, width=0.60, color=C_MAIN, alpha=0.85, zorder=3)
        ax.bar(x, em, width=0.60, bottom=plan, color=C_ACCENT, alpha=0.95, zorder=4)
        ax.set_ylabel("购电量 / kWh")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v/1e6:,.1f}M"))
        top = (plan + em).max()
        ax.set_ylim(0, top * 1.26)
        style(ax)
        ax.annotate(f"最高 {em[imax]:,.0f} kWh", xy=(x[imax], plan[imax] + em[imax]),
                    xytext=(0, 26), textcoords="offset points", ha="center",
                    fontsize=8, color=C_ACCENT,
                    arrowprops=dict(arrowstyle="-", lw=0.6, color=C_GREY, shrinkB=1),
                    bbox=dict(boxstyle="round,pad=0.22", fc="white", ec=C_GREY_L,
                              lw=0.6, alpha=0.95))
        ax.set_title("月度购电量构成（自然日口径，334 天）", pad=5)

        axr.bar(x, share, width=0.60, color=C_GREY, alpha=0.75, zorder=3)
        axr.bar([imax], [share[imax]], width=0.60, color=C_ACCENT, alpha=0.95, zorder=4)
        axr.axhline(mean, color=C_ACT, lw=1.0, ls=LS_ALT, zorder=5)
        axr.annotate(f"全期均值 {mean:.4f}%", xy=(len(rows) - 0.4, mean),
                     xytext=(0, 4), textcoords="offset points", ha="right",
                     fontsize=7.8, color=C_ACT)
        axr.set_ylabel("紧急购电占比 / %")
        axr.set_xticks(x)
        axr.set_xticklabels(months)
        axr.set_xlabel("月份")
        axr.set_ylim(0, share.max() * 1.32)
        style(axr)

        fig.legend(handles=[
            Patch(facecolor=C_MAIN, alpha=0.85, label="计划购电量"),
            Patch(facecolor=C_ACCENT, alpha=0.95, label="紧急购电量"),
            Patch(facecolor=C_GREY, alpha=0.75, label="月度紧急购电占比"),
            Line2D([], [], color=C_ACT, lw=1.0, ls=LS_ALT,
                   label=f"全期均值 {mean:.4f}%")],
            loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.0),
            handlelength=1.5, columnspacing=1.4)
        fig.tight_layout(rect=(0, 0, 1, 0.925))
        out = save(fig, "fig2b_monthly_stack")

    return {"files": out, "meta": {
        "em_max_kwh": float(em[imax]), "em_max_month": months[imax],
        "em_max_share_pct": float(share[imax]),
        "em_min_month": months[int(np.argmin(em))],
        "share_mean_pct": mean,
    }}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig2b()
    print(f"[图2b] 月度购电量构成与紧急购电占比  字体 {FONT}")
    for k, v in res["meta"].items():
        print(f"   {k} = {v}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
