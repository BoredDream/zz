# -*- coding: utf-8 -*-
"""图 4b　紧急购电量的电价档与时段分布（左右双面板）
================================================================================
核心任务
    紧急购电发生在什么电价档、什么时刻？
    解释一个乍看矛盾的现象：66% 的紧急购电量落在尖峰价档，而模型本是为了省钱。

信息结构
    · 左面板：按电价四档的水平条形 —— 谷（<0.5）/ 平（0.5–0.9）/
      峰（0.9–1.25）/ 尖（≥1.25）元/kWh，色阶为「蓝 → 灰 → 浅灰 → 赤陶」，
      每档右对齐给出购电量、占比与出现时段数
    · 右面板：出现紧急购电的时段在 24 小时上的分布，峰值小时染赤陶

因果护栏（务必与结论同写）
    紧急购电量仅占总购电量的 1.27%，但其费用占总费用的约 11.22%。
    绝对量集中于高价档，反映的是"预测误差恰好落在高价时段"这一事实，
    **不表示策略在高价时段主动多购电**，不得写成策略偏好高价。

数据源
    _figdata/emergency_by_price_band.csv 与 _figdata/emergency_scatter.csv
    （由 code/gen_plot_data.py 从 outputs/q2/interval_detail.csv 整理）
================================================================================
"""
from __future__ import annotations

try:
    from ._common import (C_ACCENT, C_GREY, C_GREY_L, C_MAIN, C_TEXT, DATA,
                          FONT, RC, rd, save, style)
except ImportError:
    from _common import (C_ACCENT, C_GREY, C_GREY_L, C_MAIN, C_TEXT, DATA,
                         FONT, RC, rd, save, style)

from collections import defaultdict

import numpy as np
import matplotlib
import matplotlib.pyplot as plt

# 电价档顺序与阈值（与图1b、图2a 的尖峰阈值 1.25 保持一致）
BAND_ORDER = ["谷(<0.5)", "平(0.5-0.9)", "峰(0.9-1.25)", "尖(≥1.25)"]


def fig4b() -> dict:
    """绘制图4b，返回 {"files": …, "meta": …}。"""
    band = rd(DATA / "emergency_by_price_band.csv")
    lut = {r["price_band"]: r for r in band}
    bs = [b for b in BAND_ORDER if b in lut]
    kwh = np.array([float(lut[b]["emergency_kwh"]) for b in bs])
    share = np.array([float(lut[b]["share_pct"]) for b in bs])
    cnt = np.array([int(float(lut[b]["intervals"])) for b in bs])
    cols = [C_MAIN, C_GREY, C_GREY_L, C_ACCENT]

    scatter = rd(DATA / "emergency_scatter.csv")
    by_hour: dict = defaultdict(int)
    for r in scatter:
        by_hour[int(r["hour"])] += 1
    hours = sorted(by_hour)
    counts = np.array([by_hour[h] for h in hours])
    hmax = int(np.argmax(counts))
    hcols = [C_ACCENT if i == hmax else C_GREY for i in range(len(hours))]

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.1, 3.3),
                                       gridspec_kw={"width_ratios": [1.12, 1.0],
                                                    "wspace": 0.42})
        # ---------------- 左：按电价档 ----------------
        ypos = np.arange(len(bs))
        ax1.barh(ypos, kwh, height=0.62, color=cols[:len(bs)], alpha=0.92, zorder=3)
        ax1.set_yticks(ypos)
        ax1.set_yticklabels(bs)
        ax1.invert_yaxis()
        ax1.set_xlabel("紧急购电量 / kWh")
        ax1.set_xlim(0, kwh.max() * 1.58)
        style(ax1, grid_axis="x")
        for i, (v, s, c) in enumerate(zip(kwh, share, cnt)):
            ax1.annotate(f"{v:,.0f}", xy=(v, i), xytext=(6, 3),
                         textcoords="offset points", fontsize=7.8, color=C_TEXT, zorder=9)
            ax1.annotate(f"{s:.1f}%｜{c} 时段", xy=(v, i), xytext=(6, -8),
                         textcoords="offset points", fontsize=7.4, color=C_GREY, zorder=9)
        ax1.annotate(f"{share[-1]:.0f}% 集中在尖峰价档",
                     xy=(kwh[-1] * 0.5, len(bs) - 1), ha="center", va="center",
                     fontsize=8, color="white", zorder=9)
        ax1.set_title("(a) 紧急购电量按电价档分布", pad=5, fontsize=9)

        # ---------------- 右：按时段 ----------------
        ax2.bar(np.arange(len(hours)), counts, width=0.64, color=hcols, alpha=0.90,
                zorder=3)
        ax2.set_xticks([i for i, h in enumerate(hours) if h % 2 == 0])
        ax2.set_xticklabels([str(h) for h in hours if h % 2 == 0])
        ax2.set_xlabel("时刻 / 时")
        ax2.set_ylabel("出现紧急购电的时段数")
        ax2.set_ylim(0, counts.max() * 1.20)
        style(ax2)
        ax2.annotate(f"峰值 {counts[hmax]} 个时段", xy=(hmax, counts[hmax]),
                     xytext=(0, 5), textcoords="offset points", ha="center",
                     fontsize=7.8, color=C_ACCENT, zorder=9)
        ax2.set_title(f"(b) 时刻分布（合计 {int(counts.sum()):,} 个时段）",
                      pad=5, fontsize=9)
        fig.tight_layout()
        out = save(fig, "fig4b_emergency_cost_band")

    return {"files": out, "meta": {
        "band_kwh": {b: float(v) for b, v in zip(bs, kwh)},
        "band_share_pct": {b: float(v) for b, v in zip(bs, share)},
        "peak_band": bs[-1], "peak_band_share_pct": float(share[-1]),
        "intervals_total": int(counts.sum()),
        "peak_hour": int(hours[hmax]), "peak_hour_count": int(counts[hmax]),
    }}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig4b()
    print(f"[图4b] 紧急购电量的电价档与时段分布  字体 {FONT}")
    for k, v in res["meta"].items():
        print(f"   {k} = {v}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
