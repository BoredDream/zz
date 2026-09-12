# -*- coding: utf-8 -*-
"""图 1b　典型日负荷、光伏、净负荷与分时电价（上下双面板）
================================================================================
核心任务
    典型日中，小区负荷、光伏出力、净负荷与分时电价在日内如何变化？
    让评委一眼看懂：白天光伏上升 → 净负荷下降 → 净负荷转负即"光伏富余" → 电价存在明显峰谷差。

信息结构（共享 x 轴，上 65% / 下 35%）
    · 上面板：三条干净折线，无 marker
        小区负荷  实线    lw1.6  #4C6E91
        光伏出力  虚线    lw1.5  灰 #9AA4AE
        净负荷    点划线  lw1.8  青灰绿 #7E9B84（核心派生量，略突出）
      y=0 浅灰基准线；**只填充净负荷低于 0 的实际区域**（fill_between where=net<0）
    · 下面板：仅一条赤陶阶梯线（step），**无曲线下方填充**；
      谷价区 / 尖峰价区用 alpha 0.06 的极浅水平色带区分

图内文字只保留 3 处：光伏富余区 / 谷价区 / 尖峰价区（无数值、无边框、无箭头）。
光伏峰值、富余总量、最低价、最高价、峰谷价比全部移入图注与正文。

先做过的数据审计（结论：数值无误，发现并修正了一处时间标签生成缺陷）
    · annex1_net_load.csv 由 code/gen_plot_data.py 生成。
      附件1.xlsx 的时间列为【混合类型】，切换点恰在 10:00：
        idx 0–59   datetime.time（00:10 … 10:00）
        idx 60–143 纯字符串（'10:10' … '0:00+1'）
      旧版生成函数用 `"24:00" if not hasattr(v, "hour") else ...` 判断，
      使整个下午的 84 行（10:10–24:00）标签全部被写成 '24:00'。
      后果：slot_of() 对 84 行返回同一个 x=24，折线在 x=24 处往返——
      这正是旧图"光伏自 10:00 起长期维持约 6400 kW"与"24:00 处垂直下降到 0"的确切成因，
      两者均为绘图伪影。修复前唯一标签仅 61 个，修复后 144 个。
    · 数值未被改动：144 行数值与附件1.xlsx 原始单元格逐行逐列比对，0 项不一致。
    · 本模块内置时间轴自检（标签须 144 个互异且严格递增），防止该缺陷回归。

绘图约定（数据为 10 分钟区间量，行标签为该区间的结束时刻 00:10…24:00）
    · x 轴直接取标签时刻，因此 x 覆盖 (0, 24]，不用 np.r_ 外推端点，
      避免人为制造"末端垂线"或"平台"。
    · 三条功率曲线用 plot 而非 step：load/pv 是平滑变化的连续量，
      阶梯化会在整点造成虚假的平台印象。
================================================================================
"""
from __future__ import annotations

try:
    from ._common import (C_ACCENT, C_GREY, C_GREY_L, C_MAIN, C_MAIN_D, C_SOC,
                          DATA, DT, FONT, RC, rd, save, slot_of, style)
except ImportError:
    from _common import (C_ACCENT, C_GREY, C_GREY_L, C_MAIN, C_MAIN_D, C_SOC,
                         DATA, DT, FONT, RC, rd, save, slot_of, style)

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


def fig1b() -> dict:
    """绘制图1b，返回 {"files": …, "meta": …}。"""
    rows = rd(DATA / "annex1_net_load.csv")
    labels = [r["time_label"] for r in rows]

    # ---- 时间轴自检（防回归：旧版此处曾因标签生成缺陷产生 84 个重复标签）----
    if len(set(labels)) != len(labels):
        raise ValueError(f"时间标签存在重复：{len(set(labels))} 个唯一值 / {len(labels)} 行")
    t = np.array([slot_of(s) for s in labels])
    if not np.all(np.diff(t) > 0):
        raise ValueError("时间轴非严格递增，请检查 gen_plot_data.py 的 label() 实现")

    load = np.array([float(r["load_kw"]) for r in rows])
    pv = np.array([float(r["pv_kw"]) for r in rows])
    net = np.array([float(r["net_kw"]) for r in rows])
    price = np.array([float(r["price_yuan_per_kwh"]) for r in rows])
    sur = net < 0

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(7.1, 4.4), sharex=True,
            gridspec_kw={"height_ratios": [1.8, 0.8], "hspace": 0.12})

        # ---------------- 上面板：负荷 / 光伏 / 净负荷 ----------------
        if sur.any():   # 只填净负荷低于 0 的实际区域，表达真正的光伏富余量
            ax1.fill_between(t, net, 0.0, where=sur, interpolate=True,
                             color=C_SOC, alpha=0.15, linewidth=0, zorder=2)
        ax1.axhline(0.0, color=C_GREY_L, lw=0.7, alpha=0.9, zorder=1)
        ax1.plot(t, load, color=C_MAIN, lw=1.6, ls="-", zorder=4, label="小区负荷")
        ax1.plot(t, pv, color=C_GREY, lw=1.5, ls=(0, (5, 2)), zorder=3, label="光伏出力")
        ax1.plot(t, net, color=C_SOC, lw=1.8, ls=(0, (6, 1.5, 1.5, 1.5)),
                 zorder=5, label="净负荷")
        if sur.any():   # 全图仅 1 处结论标注：无数值、无边框、无箭头
            ax1.annotate("光伏富余区", xy=(float(t[sur].mean()), -900), ha="center",
                         va="top", fontsize=8, color="#4E6B52", zorder=9)
        ax1.set_ylabel("功率 / kW")
        ax1.set_ylim(-2400, 8400)
        ax1.yaxis.set_major_locator(MaxNLocator(nbins=6))
        style(ax1)
        ax1.legend(frameon=False, ncol=3, loc="upper center",
                   bbox_to_anchor=(0.5, 1.02), handlelength=2.4, columnspacing=1.6,
                   borderaxespad=0.0, fontsize=8)

        # ---------------- 下面板：分时电价（仅阶梯线，无填充） ----------------
        ax2.step(t, price, where="post", color=C_ACCENT, lw=1.5, zorder=4)
        pmin, pmax = float(price.min()), float(price.max())
        ax2.axhspan(pmin - 0.05, 0.56, color=C_MAIN, alpha=0.06, zorder=0, lw=0)
        ax2.axhspan(1.25, pmax + 0.05, color=C_ACCENT, alpha=0.06, zorder=0, lw=0)
        ax2.annotate("谷价区", xy=(1.2, 0.22), fontsize=7.5, color=C_MAIN_D, zorder=9)
        ax2.annotate("尖峰价区", xy=(14.6, 1.31), fontsize=7.5, color=C_ACCENT, zorder=9)
        ax2.set_ylim(0, pmax * 1.16)
        ax2.set_yticks([0, 0.5, 1.0, 1.5])
        ax2.set_xlim(0, 24)
        ax2.set_xticks(range(0, 25, 4))
        ax2.set_xlabel("时刻 / h")
        ax2.set_ylabel("电价 / (元/kWh)")
        style(ax2)

        fig.subplots_adjust(left=0.088, right=0.985, top=0.915, bottom=0.125)
        out = save(fig, "fig1b_typical_day")

    i20 = labels.index("20:00")
    return {"files": out, "meta": {
        "pv_peak_kw": float(pv.max()),
        "pv_peak_label": labels[int(np.argmax(pv))],
        "pv_zero_intervals": int((pv == 0).sum()),
        "surplus_intervals": int(sur.sum()),
        "surplus_kwh": float(abs(net[sur].sum()) * DT),
        "surplus_label_range": [labels[int(np.nonzero(sur)[0][0])],
                                labels[int(np.nonzero(sur)[0][-1])]] if sur.any() else None,
        "net_min_kw": float(net.min()),
        "price_min": pmin, "price_max": pmax,
        "price_peak_valley_ratio": float(pmax / pmin),
        "pv_at_20h": float(pv[i20]),
        "n_labels": len(set(labels)), "last_label": labels[-1],
    }}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig1b()
    print(f"[图1b] 典型日负荷/光伏/净负荷与分时电价  字体 {FONT}")
    for k, v in res["meta"].items():
        print(f"   {k} = {v}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
