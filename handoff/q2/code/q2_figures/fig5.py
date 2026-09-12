# -*- coding: utf-8 -*-
"""图 5　费用构成与终端储电价值敏感性（左右双面板）
================================================================================
核心任务
    储能与日内补救各值多少钱？结果对终端储电价值取值是否敏感？

信息结构
    · 左面板：三种口径的费用构成堆叠柱 —— 计划购电费（深蓝灰）+ 紧急购电费（赤陶）
        主策略（本文模型）/ 固定参考储能（局部反事实）/ 无储能（基线）
      并用赤陶标注 + 虚线参考线给出"主策略相对无储能基线的节省额"
    · 右面板：终端储电价值 0 / 1 / 2 倍 v 下四个指定日期的当日费用
        改为折线 + marker（斜率比柱高更易看出"2 倍时费用上升"）；
        主模型档（1 倍 v）用赤陶实心 marker 强调

口径护栏
    "固定参考储能（局部反事实）"每日沿用主策略的储电量起点、不响应实际偏差，
    仅用于度量日内补救的局部价值，**不是独立连续全年策略**，
    不得与主策略并列为"两种完整策略"。

数据源
    _figdata/baseline_compare.csv 与 _figdata/sensitivity_terminal.csv
    （由 code/gen_plot_data.py 从 outputs/q2/summary.json 与 solver_payload.json 整理）
================================================================================
"""
from __future__ import annotations

try:
    from ._common import (C_ACCENT, C_ACT, C_GREY, C_GREY_L, C_MAIN, C_TEXT,
                          DATA, FONT, LS_ALT, LS_ALT2, LS_MAIN, MK_ALT, MK_ALT2,
                          MK_MAIN, RC, rd, save, style)
except ImportError:
    from _common import (C_ACCENT, C_ACT, C_GREY, C_GREY_L, C_MAIN, C_TEXT,
                         DATA, FONT, LS_ALT, LS_ALT2, LS_MAIN, MK_ALT, MK_ALT2,
                         MK_MAIN, RC, rd, save, style)

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

STRATEGY_NAMES = ["主策略\n（本文模型）", "固定参考储能\n（局部反事实）", "无储能\n（基线）"]


def fig5() -> dict:
    """绘制图5，返回 {"files": …, "meta": …}。"""
    base = rd(DATA / "baseline_compare.csv")
    total = np.array([float(r["total_cost_yuan"]) for r in base])
    planned = np.array([float(r["planned_cost_yuan"]) for r in base])
    emer = np.array([float(r["emergency_cost_yuan"]) for r in base])

    sens = rd(DATA / "sensitivity_terminal.csv")
    dates = sorted({r["date"] for r in sens})
    factors = sorted({float(r["terminal_value_factor"]) for r in sens})
    cost: dict = {d: {} for d in dates}
    for r in sens:
        cost[r["date"]][float(r["terminal_value_factor"])] = float(r["natural_day_cost_yuan"])

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.1, 4.2),
                                       gridspec_kw={"width_ratios": [1.0, 1.05],
                                                    "wspace": 0.30})
        # ---------------- 左：三种口径的费用构成 ----------------
        x = np.arange(len(base))
        ax1.bar(x, planned, width=0.52, color=C_MAIN, alpha=0.88, zorder=3)
        ax1.bar(x, emer, width=0.52, bottom=planned, color=C_ACCENT, alpha=0.95, zorder=4)
        ax1.set_xticks(x)
        ax1.set_xticklabels(STRATEGY_NAMES, fontsize=7.8)
        ax1.set_ylabel("总购电费 / 元")
        ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v/1e4:,.0f}万"))
        ax1.set_ylim(0, total.max() * 1.42)
        style(ax1)
        for i, v in enumerate(total):
            ax1.annotate(f"{v/1e4:,.1f}", xy=(i, v), xytext=(0, 5),
                         textcoords="offset points", ha="center", fontsize=8,
                         color=C_TEXT)
        save_amt = float(total[2] - total[0])
        ax1.annotate(f"主策略相对无储能基线\n节省 {save_amt/1e4:,.1f} 万元"
                     f"（{save_amt/total[2]*100:.1f}%）",
                     xy=(2.0, total[2] * 1.005), xytext=(1.30, total.max() * 1.30),
                     ha="center", va="center", fontsize=8, color=C_ACCENT,
                     arrowprops=dict(arrowstyle="-", lw=0.8, color=C_ACCENT,
                                     shrinkA=4, shrinkB=2,
                                     connectionstyle="arc3,rad=-0.25"),
                     bbox=dict(boxstyle="round,pad=0.28", fc="white",
                               ec=C_GREY_L, lw=0.8, alpha=0.96), zorder=9)
        ax1.plot([0, 2], [total[0], total[2]], color=C_ACCENT, lw=1.0,
                 ls=(0, (4, 2)), zorder=6)
        ax1.legend(handles=[Patch(facecolor=C_MAIN, alpha=0.88, label="计划购电费"),
                            Patch(facecolor=C_ACCENT, alpha=0.95, label="紧急购电费")],
                   frameon=False, loc="lower left", handlelength=1.5, fontsize=8)
        ax1.set_title("(a) 三种口径的费用构成（334 天累计）", pad=5, fontsize=9)

        # ---------------- 右：终端储电价值敏感性 ----------------
        mk = [MK_ALT, MK_MAIN, MK_ALT2]
        ls = [LS_ALT, LS_MAIN, LS_ALT2]
        cl = [C_GREY, C_MAIN, C_ACT]
        xs = np.arange(len(dates))
        for k, f in enumerate(factors):
            vals = [cost[d][f] for d in dates]
            is_main = (f == 1)
            ax2.plot(xs, vals, color=C_ACCENT if is_main else cl[k],
                     lw=2.0 if is_main else 1.4, ls=LS_MAIN if is_main else ls[k],
                     marker=mk[k], ms=5.2 if is_main else 4.2,
                     mfc=C_ACCENT if is_main else "white",
                     mec=C_ACCENT if is_main else cl[k], mew=1.2,
                     zorder=6 if is_main else 5)
            if is_main:
                ax2.annotate("主模型", xy=(xs[-1], vals[-1]), xytext=(6, 6),
                             textcoords="offset points", fontsize=7.6, color=C_ACCENT)
        ax2.set_xticks(xs)
        ax2.set_xticklabels([d[5:].replace("-", "/") for d in dates])
        ax2.set_xlabel("日期（月/日）")
        ax2.set_ylabel("当日费用 / 元")
        vmax = max(cost[d][f] for d in dates for f in factors)
        ax2.set_ylim(0, vmax * 1.20)
        ax2.set_xlim(-0.35, len(dates) - 0.65)
        style(ax2)
        ax2.set_title("(b) 终端储电价值的敏感性", pad=5, fontsize=9)

        fig.legend(handles=[
            Patch(facecolor=C_MAIN, alpha=0.88, label="计划购电费"),
            Patch(facecolor=C_ACCENT, alpha=0.95, label="紧急购电费"),
            Line2D([], [], color=C_ACCENT, lw=2.0, marker=MK_MAIN, ms=5.2,
                   mfc=C_ACCENT, mec=C_ACCENT, label="终端价值 1 倍 v（主模型）"),
            Line2D([], [], color=C_GREY, lw=1.4, ls=LS_ALT, marker=MK_ALT, ms=4.2,
                   mfc="white", mec=C_GREY, label="终端价值 0 倍 v"),
            Line2D([], [], color=C_ACT, lw=1.4, ls=LS_ALT2, marker=MK_ALT2, ms=4.2,
                   mfc="white", mec=C_ACT, label="终端价值 2 倍 v")],
            loc="upper center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 1.005),
            fontsize=7.8, columnspacing=1.2, handlelength=2.0)
        fig.tight_layout(rect=(0, 0, 1, 0.90))
        out = save(fig, "fig5_strategy_compare")

    return {"files": out, "meta": {
        "total_cost_yuan": {n.replace("\n", ""): float(v)
                            for n, v in zip(STRATEGY_NAMES, total)},
        "saving_yuan": save_amt,
        "saving_pct_of_baseline": float(save_amt / total[2] * 100),
        "sensitivity_dates": dates, "sensitivity_factors": factors,
    }}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig5()
    print(f"[图5] 费用构成与终端储电价值敏感性  字体 {FONT}")
    for k, v in res["meta"].items():
        print(f"   {k} = {v}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
