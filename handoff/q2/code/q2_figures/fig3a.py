# -*- coding: utf-8 -*-
"""图 3a　四个指定日期的储电量轨迹（单面板四日对比）
================================================================================
核心任务
    证明储能**始终运行在题面要求的 1200–10800 kWh 区间内**（素材包 §F1 约束校验的图形化证据），
    并横向对比四个指定日期的储电量轨迹形态。

信息结构（单面板，非 2×2）
    · 四条曲线 = 四个指定日期的储电量，以 **颜色 + 线型 + marker** 三重区分
    · 赤陶虚线 = 运行上下限 1200 / 10800 kWh，并在图上直接标注
    · 浅绿底纹 = 允许运行区间

为什么换成单面板
    原版为 2×2 四单日面板并叠加电价右轴，共 8 条信息线，
    缩到论文宽度后不可读；单面板直接对比"是否越界"更有说服力。
    电价不在此图叠加，避免双轴误导（电价响应与套利见图1b、图2a）。

数据源
    outputs/q2/interval_detail.csv（逐时段明细，48,096 条）
================================================================================
"""
from __future__ import annotations

try:
    from ._common import (C_ACCENT, C_ACT, C_GREY, C_MAIN, C_SOC, C_SOC_L,
                          FONT, LS_ALT, LS_ALT2, LS_MAIN, MK_ALT, MK_ALT2,
                          MK_MAIN, RC, SOC_MAX, SOC_MIN, detail, save, slot_of, style)
except ImportError:
    from _common import (C_ACCENT, C_ACT, C_GREY, C_MAIN, C_SOC, C_SOC_L,
                         FONT, LS_ALT, LS_ALT2, LS_MAIN, MK_ALT, MK_ALT2,
                         MK_MAIN, RC, SOC_MAX, SOC_MIN, detail, save, slot_of, style)

from collections import defaultdict

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

TARGET_DATES = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]


def fig3a() -> dict:
    """绘制图3a，返回 {"files": …, "meta": …}。"""
    by: dict = defaultdict(list)
    for r in detail():
        if r["date"] in TARGET_DATES:
            by[r["date"]].append(r)

    styles = [(C_MAIN, LS_MAIN, MK_MAIN),
              (C_GREY, LS_ALT, MK_ALT),
              (C_SOC, LS_ALT2, MK_ALT2),
              (C_ACT, (0, (3, 1, 1, 1)), "D")]

    meta = {}
    with matplotlib.rc_context(RC):
        fig = plt.figure(figsize=(7.1, 3.6))
        # 手工布局：tight_layout 遇到轴外图例会把绘图区挤到右侧并留大片空白
        ax = fig.add_axes((0.075, 0.135, 0.905, 0.70))
        handles, labels = [], []
        for d, (c, l, m) in zip(TARGET_DATES, styles):
            sub = sorted(by[d], key=lambda r: slot_of(r["time_start"]))
            t = np.array([slot_of(r["time_start"]) for r in sub])
            soc = np.array([float(r["soc_start_kwh"]) for r in sub])
            ax.plot(t, soc, color=c, lw=1.5, ls=l, marker=m, markevery=8, ms=3.4,
                    mfc="white", mew=0.9, zorder=5)
            handles.append(Line2D([], [], color=c, lw=1.5, ls=l, marker=m,
                                  markevery=[0], ms=3.4, mfc="white", mew=0.9))
            labels.append(f"{d}　{soc[0]:.0f}→{soc[-1]:.0f} kWh")
            meta[d] = {"soc_start_kwh": float(soc[0]), "soc_end_kwh": float(soc[-1]),
                       "soc_min_kwh": float(soc.min()), "soc_max_kwh": float(soc.max())}

        ax.axhspan(SOC_MIN, SOC_MAX, color=C_SOC_L, alpha=0.16, zorder=0)
        for y, txt in ((SOC_MAX, f"运行上限 {SOC_MAX:.0f} kWh"),
                       (SOC_MIN, f"运行下限 {SOC_MIN:.0f} kWh")):
            ax.axhline(y, color=C_ACCENT, lw=1.1, ls=(0, (5, 2)), zorder=3)
            # 标注放左侧，避免与右侧曲线重叠
            ax.annotate(txt, xy=(0.15, y), xytext=(0, 5), textcoords="offset points",
                        ha="left", fontsize=7.8, color=C_ACCENT, zorder=9)
        ax.set_xlim(0, 24)
        ax.set_ylim(0, 12200)
        ax.set_xticks(range(0, 25, 2))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        ax.set_xlabel("时刻 / 时")
        ax.set_ylabel("储电量 / kWh")
        style(ax)
        ax.set_title("四个指定日期的储电量轨迹（全部时段位于运行区间内）", pad=30)
        ax.legend(handles, labels, frameon=False, ncol=4, loc="lower center",
                  bbox_to_anchor=(0.5, 1.005), handlelength=2.6, columnspacing=1.4)
        out = save(fig, "fig3a_soc_trajectory")

    span = [v for key, d in meta.items() if key in TARGET_DATES
            for v in (d["soc_min_kwh"], d["soc_max_kwh"])]
    meta["in_band"] = bool(min(span) >= SOC_MIN - 1e-6 and max(span) <= SOC_MAX + 1e-6)
    return {"files": out, "meta": meta}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig3a()
    print(f"[图3a] 四个指定日期的储电量轨迹  字体 {FONT}")
    for k, v in res["meta"].items():
        print(f"   {k} = {v}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
