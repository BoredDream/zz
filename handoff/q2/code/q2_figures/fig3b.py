# -*- coding: utf-8 -*-
"""图 3b　储电量分布与单时段充放电量分布（左右双面板）
================================================================================
核心任务
    全期储电量与充放电量的分布形态如何？是否长期贴运行边界、是否经常打满功率上限？
    这是全图集里唯一能暴露模型结构性特征的一张图。

信息结构
    · 左面板：48,096 个时段的起始储电量直方图（48 个箱）
      赤陶虚线标出运行上下限 1200 / 10800 kWh，并直接给出贴边界时段占比
    · 右面板：单时段充电量（低饱和绿）与放电量（赤陶）直方图
      赤陶虚线标出功率上限 833.3333 kWh（= 5000 kW × 1/6 h），并给出打满比例

实测结论（论文可引用）
    · 贴上限（≥10750 kWh）占 14.75%、贴下限（≤1250 kWh）占 4.21%
    · 打满功率上限的时段：充电 4.06%、放电 0.19%
    → 储电量频繁触及上限、而放电侧几乎从不满功率运行，
      支持"储能容量相对光伏富余偏小"这一改进方向。

数据源
    outputs/q2/interval_detail.csv（逐时段明细，48,096 条）
================================================================================
"""
from __future__ import annotations

try:
    from ._common import (C_ACCENT, C_SOC, E_MAX, FONT, RC, SOC_MAX, SOC_MIN,
                          detail, save, style)
except ImportError:
    from _common import (C_ACCENT, C_SOC, E_MAX, FONT, RC, SOC_MAX, SOC_MIN,
                         detail, save, style)

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


def fig3b() -> dict:
    """绘制图3b，返回 {"files": …, "meta": …}。"""
    rows = detail()
    soc = np.array([float(r["soc_start_kwh"]) for r in rows])
    chg = np.array([float(r["charge_kwh"]) for r in rows])
    dis = np.array([float(r["discharge_kwh"]) for r in rows])
    low_pct = float((soc <= 1250).mean() * 100)
    high_pct = float((soc >= 10750).mean() * 100)
    hit_c = float((chg >= E_MAX - 1e-6).mean() * 100)
    hit_d = float((dis >= E_MAX - 1e-6).mean() * 100)

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.1, 3.2),
                                       gridspec_kw={"width_ratios": [1.0, 1.05],
                                                    "wspace": 0.34})
        # ---------------- 左：储电量分布 ----------------
        ax1.hist(soc, bins=48, range=(SOC_MIN, SOC_MAX), color=C_SOC, alpha=0.85,
                 edgecolor="white", linewidth=0.4, zorder=3)
        for y, txt, dx, ha in ((SOC_MIN, f"下限 {SOC_MIN:.0f}\n{low_pct:.2f}% 时段",
                                150, "left"),
                               (SOC_MAX, f"上限 {SOC_MAX:.0f}\n{high_pct:.2f}% 时段",
                                -150, "right")):
            ax1.axvline(y, color=C_ACCENT, lw=1.1, ls=(0, (5, 2)), zorder=5)
            ax1.annotate(txt, xy=(y + dx, ax1.get_ylim()[1] * 0.70), ha=ha,
                         fontsize=7.8, color=C_ACCENT, zorder=9)
        ax1.set_xlabel("储电量 / kWh")
        ax1.set_ylabel("时段数")
        ax1.set_xlim(SOC_MIN, SOC_MAX)
        ax1.xaxis.set_major_locator(MaxNLocator(nbins=5))
        style(ax1)
        ax1.set_title("(a) 储电量分布（48,096 个时段）", pad=5, fontsize=9)

        # ---------------- 右：充放电量分布 ----------------
        bins = np.linspace(0, E_MAX, 41)
        ax2.hist(chg, bins=bins, color=C_SOC, alpha=0.85, edgecolor="white",
                 linewidth=0.4, zorder=3, label="充电量")
        ax2.hist(dis, bins=bins, color=C_ACCENT, alpha=0.85, edgecolor="white",
                 linewidth=0.4, zorder=4, label="放电量")
        ax2.axvline(E_MAX, color=C_ACCENT, lw=1.1, ls=(0, (5, 2)), zorder=5)
        ax2.annotate(f"功率上限 {E_MAX:.1f} kWh\n打满：充电 {hit_c:.1f}% / 放电 {hit_d:.1f}%",
                     xy=(E_MAX, ax2.get_ylim()[1] * 0.72), xytext=(-8, 0),
                     textcoords="offset points", ha="right", fontsize=7.8,
                     color=C_ACCENT, zorder=9)
        ax2.set_xlabel("单时段充 / 放电量 / kWh")
        ax2.set_ylabel("时段数")
        ax2.set_xlim(0, E_MAX * 1.02)
        ax2.xaxis.set_major_locator(MaxNLocator(nbins=5))
        style(ax2)
        ax2.legend(frameon=False, loc="upper center", ncol=2, handlelength=1.5,
                   columnspacing=1.2)
        ax2.set_title("(b) 充放电量分布", pad=5, fontsize=9)
        fig.tight_layout()
        out = save(fig, "fig3b_soc_hist")

    return {"files": out, "meta": {
        "n_intervals": len(rows),
        "soc_low_pct": low_pct, "soc_high_pct": high_pct,
        "hit_charge_pct": hit_c, "hit_discharge_pct": hit_d,
        "interval_limit_kwh": float(E_MAX),
    }}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig3b()
    print(f"[图3b] 储电量分布与充放电量分布  字体 {FONT}")
    for k, v in res["meta"].items():
        print(f"   {k} = {v}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
