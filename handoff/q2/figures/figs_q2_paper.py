# -*- coding: utf-8 -*-
"""第二问图集 · 学术插图风格版（低饱和蓝灰）

视觉规范（本脚本唯一权威定义）：
  · 白底、简洁二维、无渐变/发光/3D/阴影
  · 去顶部与右侧边框；仅水平浅灰弱网格（alpha 0.30, lw 0.5）
  · 配色全部低饱和蓝灰系：主色 深蓝灰，强调色 去饱和赤陶
  · 同义同色：同一含义在 9 张图中颜色一致；同图内不同系列以线型+marker 区分
  · 线型约定：实线/●=主数据；虚线/■=对照或实测；点划线/▲=次要
  · 文字 深灰 #333333；字号：刻度 8.5 / 轴标题 9.5 / 图例 8.5
  · 输出 SVG + PDF + PNG(600dpi)

逻辑修正（本轮审计发现）：
  · 图1 图注原写"全距覆盖 68.40%"，但图内只画 10–90 分位带
    -> 覆盖率口径统一为分位带 54.51%，与图内一致
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import matplotlib
from matplotlib import font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator, FuncFormatter

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "_figdata"
Q2 = HERE.parents[2] / "outputs" / "q2"

# ============================ 低饱和蓝灰配色（唯一权威）============================
C_MAIN = "#4C6E91"        # 主色：计划量 / 模型预测 / 主数据
C_MAIN_D = "#3A5470"      # 主色深版：中位数线
C_ACCENT = "#A9705A"      # 强调色（去饱和赤陶）：紧急购电、最大偏差、核心结论
C_ACCENT_L = "#DCC3B6"    # 强调色浅版（填充）
C_ACT = "#5B6470"         # 实测 / 真实观测
C_GREY = "#9AA4AE"        # 对照 / 次要
C_GREY_L = "#C9D0D6"      # 对照浅版（填充）
C_SOC = "#7E9B84"         # 储电量（低饱和绿，含灰调）
C_SOC_L = "#C6D3C8"       # 储电量浅版（填充）
C_GRID = "#DFE3E7"        # 网格
C_TEXT = "#333333"
C_SPINE = "#B4BBC2"

LS_MAIN, LS_ALT, LS_ALT2 = "-", "--", "-."
MK_MAIN, MK_ALT, MK_ALT2 = "o", "s", "^"

FONT_CANDIDATES = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                   "Arial Unicode MS", "DejaVu Sans"]
SAVE_FORMATS = ["svg", "pdf", "png"]
PNG_DPI = 600
DT = 1.0 / 6.0
E_MAX = 5000.0 * DT
_SOC_MIN, _SOC_MAX = 1200.0, 10800.0


def pick_font() -> str:
    have = {f.name for f in fm.fontManager.ttflist}
    for n in FONT_CANDIDATES:
        if n in have:
            return n
    return "DejaVu Sans"


FONT = pick_font()

RC = {
    "font.sans-serif": [FONT, "DejaVu Sans"],
    "axes.unicode_minus": False,
    "font.size": 8.5,
    "axes.labelsize": 9.5,
    "axes.titlesize": 9.5,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.fontsize": 8.5,
    "axes.edgecolor": C_SPINE,
    "axes.linewidth": 0.7,
    "text.color": C_TEXT,
    "axes.labelcolor": C_TEXT,
    "xtick.color": C_TEXT,
    "ytick.color": C_TEXT,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "svg.fonttype": "none",
    "axes.grid": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
}


# ============================ 工具 ============================
def save(fig, stem: str) -> dict:
    out = {}
    for ext in SAVE_FORMATS:
        p = HERE / f"{stem}.{ext}"
        kw = {"bbox_inches": "tight", "facecolor": "white"}
        if ext == "png":
            kw["dpi"] = PNG_DPI
        fig.savefig(p, format=ext, **kw)
        out[ext] = str(p)
    plt.close(fig)
    return out


def style(ax, grid_axis="y", grid=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_linewidth(0.7)
        ax.spines[s].set_color(C_SPINE)
    if grid:
        ax.grid(axis=grid_axis, color=C_GRID, lw=0.5, alpha=0.30)
        ax.set_axisbelow(True)
    return ax


def rd(p: Path) -> list[dict]:
    with p.open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def detail() -> list[dict]:
    rows = rd(Q2 / "interval_detail.csv")
    if len(rows) != 48_096:
        raise ValueError(f"interval_detail.csv 行数异常：{len(rows)}")
    return rows


def slot_of(t: str) -> float:
    return 24.0 if t == "24:00" else int(t[:2]) + int(t[3:5]) / 60.0


def box(ax, text, xy, xytext, color=None, ha="left", rad=None):
    """统一的结论标注：白底细边、无阴影、无渐变。"""
    ap = dict(arrowstyle="-", lw=0.6, color=C_GREY, shrinkA=0, shrinkB=2)
    if rad is not None:
        ap["connectionstyle"] = f"arc3,rad={rad}"
    return ax.annotate(text, xy=xy, xytext=xytext, textcoords="offset points",
                       fontsize=8, color=color or C_TEXT, ha=ha, zorder=9,
                       arrowprops=ap,
                       bbox=dict(boxstyle="round,pad=0.22", fc="white",
                                 ec=C_GREY_L, lw=0.6, alpha=0.95))


# ==============================================================================
#  图 1  净负荷预测与情景包络（2×2）
# ==============================================================================
def fig1() -> dict:
    rows = rd(DATA / "netload_scenarios_4days.csv")
    targets = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
    by = defaultdict(lambda: {"scen": defaultdict(dict)})
    for r in rows:
        d, t = r["date"], int(r["interval_index"])
        by[d]["scen"][int(r["scenario_id"])][t] = float(r["scenario_net_kwh"])
        by[d].setdefault("actual", {})[t] = float(r["actual_net_kwh"])
        by[d].setdefault("center", {})[t] = float(r["center_forecast_kwh"])

    meta, worst = {}, None
    cov90 = covn = 0
    with matplotlib.rc_context(RC):
        fig, axes = plt.subplots(2, 2, figsize=(7.1, 4.5), dpi=120, sharex=True)
        axes = axes.ravel()
        for ax, d in zip(axes, targets):
            tt = np.arange(144)
            x = tt * 10 / 60.0
            act = np.array([by[d]["actual"][t] for t in tt])
            cen = np.array([by[d]["center"][t] for t in tt])
            ids = sorted(by[d]["scen"])
            sc = np.array([[by[d]["scen"][s][t] for t in tt] for s in ids])
            lo = np.percentile(sc, 10, axis=0)
            hi = np.percentile(sc, 90, axis=0)
            cov90 += int(((act >= lo) & (act <= hi)).sum())
            covn += len(act)

            ax.fill_between(x, lo, hi, color=C_MAIN, alpha=0.14, linewidth=0, zorder=1)
            ax.plot(x, cen, color=C_MAIN, lw=1.6, ls=LS_MAIN, zorder=4,
                    marker=MK_MAIN, markevery=18, ms=3.0, mfc="white", mew=0.9)
            ax.plot(x, act, color=C_ACT, lw=1.4, ls=LS_ALT, zorder=5,
                    marker=MK_ALT, markevery=18, ms=2.8, mfc="white", mew=0.9)
            ax.axhline(0, color=C_GREY_L, lw=0.6, zorder=0)

            resid = np.abs(act - cen)
            i = int(np.argmax(resid))
            if worst is None or resid[i] > worst[1]:
                worst = (d, float(resid[i]), float(x[i]), float(act[i]))
            ax.set_xlim(0, 24)
            ax.set_ylim(-1250, 1350)
            ax.set_xticks(range(0, 25, 6))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
            style(ax)
            mae = float(resid.mean())
            ax.set_title(f"{d}　MAE {mae:.1f}", pad=4, fontsize=9)
            meta[d] = {"mae": mae, "rmse": float(np.sqrt((resid ** 2).mean())),
                       "n_scen": len(ids)}
        for ax in axes[2:]:
            ax.set_xlabel("时刻 / 时")
        for ax in (axes[0], axes[2]):
            ax.set_ylabel("净负荷 / (kWh/10分钟)")

        d, w, wx, wv = worst
        axw = axes[targets.index(d)]
        axw.plot([wx], [wv], marker="o", ms=4.6, mfc=C_ACCENT, mec="white",
                 mew=1.1, zorder=7)
        box(axw, f"本图内最大偏差 {w:.0f} kWh/10分钟", (wx, wv), (-108, -36), C_ACCENT)

        fig.legend(handles=[
            Line2D([], [], color=C_MAIN, lw=1.6, ls=LS_MAIN, marker=MK_MAIN,
                   markevery=[0], ms=3.0, mfc="white", mew=0.9,
                   label="本文模型中心预测"),
            Line2D([], [], color=C_ACT, lw=1.4, ls=LS_ALT, marker=MK_ALT,
                   markevery=[0], ms=2.8, mfc="white", mew=0.9, label="真实观测值"),
            Patch(facecolor=C_MAIN, alpha=0.14, edgecolor="none",
                  label="历史残差情景包络（10–90 分位）"),
            Line2D([], [], color=C_ACCENT, lw=0, marker="o", ms=4.4, mec="white",
                   mew=1.0, label="最大偏差时点"),
        ], loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.0),
            handlelength=2.4, columnspacing=1.5)
        fig.tight_layout(rect=(0, 0, 1, 0.935))
        out = save(fig, "fig1_netload_forecast")
    meta["envelope_coverage_10_90_pct"] = 100 * cov90 / covn
    return {"files": out, "meta": meta}


# ==============================================================================
#  图 1b  典型日功率曲线与分时电价
# ==============================================================================
def fig1b() -> dict:
    rows = rd(DATA / "annex1_net_load.csv")
    t = np.array([slot_of(r["time_label"]) for r in rows])
    load = np.array([float(r["load_kw"]) for r in rows])
    pv = np.array([float(r["pv_kw"]) for r in rows])
    net = np.array([float(r["net_kw"]) for r in rows])
    price = np.array([float(r["price_yuan_per_kwh"]) for r in rows])
    step = np.r_[t, 24.0]
    sur = net < 0

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(7.1, 4.6), sharex=True,
            gridspec_kw={"height_ratios": [2.0, 1.0], "hspace": 0.14})
        if sur.any():
            s0, s1 = t[sur][0], t[sur][-1] + 10 / 60
            ax1.axvspan(s0, s1, color=C_SOC_L, alpha=0.45, zorder=0)
            ax1.annotate(f"光伏富余 {abs(net[sur].sum()) * DT:,.0f} kWh",
                         xy=((s0 + s1) / 2, -1800), ha="center", fontsize=8,
                         color="#4E6B52", zorder=9)
        ax1.plot(t, load, color=C_MAIN, lw=1.4, ls=LS_MAIN, marker=MK_MAIN,
                 markevery=16, ms=3.0, mfc="white", mew=0.9, zorder=4, label="小区负载")
        ax1.plot(t, pv, color=C_ACCENT, lw=1.6, ls=LS_ALT, marker=MK_ALT,
                 markevery=16, ms=3.0, mfc="white", mew=0.9, zorder=5, label="光伏出力")
        ax1.plot(t, net, color=C_SOC, lw=1.8, ls=(0, (6, 1.5, 1.5, 1.5)),
                 marker=MK_ALT2, markevery=16, ms=3.2, mfc="white", mew=0.9,
                 zorder=6, label="净负荷（负载−光伏）")
        ax1.axhline(0, color=C_GREY_L, lw=0.6, zorder=1)
        imax = int(np.argmax(pv))
        ax1.plot([t[imax]], [pv[imax]], marker="o", ms=4.6, mfc=C_ACCENT,
                 mec="white", mew=1.1, zorder=9)
        box(ax1, f"光伏峰值 {pv[imax]:,.0f} kW", (t[imax], pv[imax]), (10, 6), C_ACCENT)
        ax1.set_ylabel("功率 / kW")
        ax1.set_ylim(-2400, 9200)
        ax1.yaxis.set_major_locator(MaxNLocator(nbins=6))
        style(ax1)
        ax1.legend(frameon=False, ncol=3, loc="upper left", handlelength=2.6,
                   columnspacing=1.4, bbox_to_anchor=(0.0, 1.02), borderaxespad=0.0)
        ax1.set_title("典型日（附件1）功率曲线与分时电价", pad=22)

        ax2.step(step, np.r_[price, price[-1]], where="post", color=C_ACCENT, lw=1.5)
        ax2.fill_between(step, 0, np.r_[price, price[-1]], step="post",
                         color=C_ACCENT_L, alpha=0.35, linewidth=0)
        ax2.axhspan(0, 0.45, color=C_MAIN, alpha=0.06, zorder=0)
        ax2.axhspan(1.25, 1.62, color=C_ACCENT, alpha=0.08, zorder=0)
        ax2.annotate(f"谷价区 <0.45\n最低 {price.min():.4f}", xy=(1.0, 0.18),
                     fontsize=7.8, color=C_MAIN_D, zorder=9)
        ax2.annotate(f"尖峰价区 >1.25\n最高 {price.max():.4f}", xy=(14.2, 1.26),
                     fontsize=7.8, color=C_ACCENT, zorder=9)
        ax2.set_ylim(0, 1.62)
        ax2.set_yticks([0, 0.5, 1.0, 1.5])
        ax2.set_xlim(0, 24)
        ax2.set_xticks(range(0, 25, 2))
        ax2.set_xlabel("时刻 / 时")
        ax2.set_ylabel("电价 / (元/kWh)")
        style(ax2)
        fig.tight_layout()
        out = save(fig, "fig1b_typical_day")
    return {"files": out, "meta": {"surplus_kwh": float(abs(net[sur].sum()) * DT)}}


# ==============================================================================
#  图 2a  单日计划购电对分时电价的响应（单主题图）
#  --------------------------------------------------------------------------
#  设计目标：本图只回答一个问题——「模型是否实现了低价多购、高价少购？」
#  信息结构（上下共享 x 轴，上 35% / 下 65%）：
#    上面板：仅分时电价（阶梯线 + 极浅填充），标出尖峰价区间；无右轴、无其他变量
#    下面板：仅计划购电量（窄柱），深蓝灰单一主色；无面积填充
#  刻意不画的（避免与图1 重复职责、降低视觉噪声）：
#    · 模型预测净负荷、实际净负荷 —— 预测准确性由图1 承担
#    · 大框标注 / 长弯箭头 —— 尖峰价时段的计划购电合计放到图注与正文
#  数据完全来自 outputs/q2/interval_detail.csv 的 2025-06-21 原始记录，
#  未平滑、未插值、未改单位、未改时间范围。
# ==============================================================================
def fig2a() -> dict:
    tgt = "2025-06-21"
    rows = sorted([r for r in detail() if r["date"] == tgt],
                  key=lambda r: slot_of(r["time_start"]))
    if len(rows) != 144:
        raise ValueError(f"{tgt} 时段数异常：{len(rows)}，应为 144")
    t = np.array([slot_of(r["time_start"]) for r in rows])
    plan = np.array([float(r["committed_plan_kwh"]) for r in rows])
    price = np.array([float(r["price_yuan_per_kwh"]) for r in rows])
    em = np.array([float(r["emergency_kwh"]) for r in rows])

    step_x = np.r_[t, 24.0]
    step_y = np.r_[price, price[-1]]
    peak = price >= 1.25
    peak_plan = float(plan[peak].sum()) if peak.any() else 0.0
    has_em = em.sum() > 1e-7

    with matplotlib.rc_context(RC):
        fig, (axp, axb) = plt.subplots(
            2, 1, figsize=(7.1, 3.9), sharex=True,
            gridspec_kw={"height_ratios": [0.54, 1.0], "hspace": 0.10})

        # ---------------- 上面板：分时电价（唯一变量） ----------------
        if peak.any():
            axp.axvspan(t[peak][0], t[peak][-1] + 10 / 60,
                        color=C_ACCENT, alpha=0.10, zorder=0, lw=0)
            axp.annotate("尖峰价时段", xy=((t[peak][0] + t[peak][-1] + 10 / 60) / 2,
                                         price.max() * 1.06),
                         ha="center", va="bottom", fontsize=7.8, color=C_ACCENT,
                         zorder=6)
        axp.fill_between(step_x, 0, step_y, step="post", color=C_ACCENT,
                         alpha=0.08, linewidth=0, zorder=1)
        axp.step(step_x, step_y, where="post", color=C_ACCENT, lw=1.4, zorder=3,
                 label="分时电价")
        axp.set_ylabel("电价 / (元/kWh)", labelpad=3)
        axp.set_ylim(0, price.max() * 1.26)
        axp.set_yticks([0, 0.5, 1.0, 1.5])
        style(axp)
        axp.legend(frameon=False, loc="upper left", handlelength=1.8,
                   borderaxespad=0.2, fontsize=8)
        axp.set_title(f"{tgt} 单日计划购电与分时电价", pad=5)

        # ---------------- 下面板：计划购电量（唯一主色） ----------------
        axb.bar(t, plan, width=(10 / 60) * 0.84, color=C_MAIN, linewidth=0,
                zorder=3, label="计划购电量")
        if has_em:
            axb.bar(t, em, bottom=plan, width=(10 / 60) * 0.84, color=C_ACCENT,
                    linewidth=0, zorder=4, label="紧急购电量")
        axb.set_xlim(0, 24)
        axb.set_xticks(range(0, 25, 4))
        axb.set_ylim(0, plan.max() * 1.12)
        axb.set_xlabel("时刻 / 时")
        axb.set_ylabel("购电量 / (kWh/10分钟)", labelpad=3)
        style(axb)
        axb.legend(frameon=False, loc="upper left", handlelength=1.6,
                   borderaxespad=0.2, fontsize=8)

        fig.subplots_adjust(left=0.085, right=0.985, top=0.905, bottom=0.135)
        out = save(fig, "fig2a_single_day_dispatch")
    return {"files": out, "meta": {
        "date": tgt, "plan_total_kwh": float(plan.sum()),
        "plan_max_kwh": float(plan.max()),
        "emergency_total_kwh": float(em.sum()), "has_emergency": has_em,
        "peak_intervals": int(peak.sum()), "peak_plan_kwh": peak_plan,
        "zero_plan_intervals": int((plan <= 1e-9).sum()),
        "price_min": float(price.min()), "price_max": float(price.max()),
    }}


# ==============================================================================
#  图 2b  月度购电量构成与紧急购电占比
# ==============================================================================
def fig2b() -> dict:
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
    return {"files": out, "meta": {"em_max": float(em[imax]), "share_mean": mean}}


# ==============================================================================
#  图 3a  四日储电量轨迹
# ==============================================================================
def fig3a() -> dict:
    targets = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
    by = defaultdict(list)
    for r in detail():
        if r["date"] in targets:
            by[r["date"]].append(r)
    st = [(C_MAIN, LS_MAIN, MK_MAIN), (C_GREY, LS_ALT, MK_ALT),
          (C_SOC, LS_ALT2, MK_ALT2), (C_ACT, (0, (3, 1, 1, 1)), "D")]

    with matplotlib.rc_context(RC):
        fig = plt.figure(figsize=(7.1, 3.6))
        ax = fig.add_axes((0.075, 0.135, 0.905, 0.70))   # 手工布局，避免 tight_layout 与图例冲突
        hs, ls_ = [], []
        for d, (c, l, m) in zip(targets, st):
            sub = sorted(by[d], key=lambda r: slot_of(r["time_start"]))
            t = np.array([slot_of(r["time_start"]) for r in sub])
            soc = np.array([float(r["soc_start_kwh"]) for r in sub])
            ax.plot(t, soc, color=c, lw=1.5, ls=l, marker=m, markevery=8, ms=3.4,
                    mfc="white", mew=0.9, zorder=5)
            hs.append(Line2D([], [], color=c, lw=1.5, ls=l, marker=m,
                             markevery=[0], ms=3.4, mfc="white", mew=0.9))
            ls_.append(f"{d}　{soc[0]:.0f}→{soc[-1]:.0f} kWh")
        ax.axhspan(_SOC_MIN, _SOC_MAX, color=C_SOC_L, alpha=0.16, zorder=0)
        for y, txt in ((_SOC_MAX, f"运行上限 {_SOC_MAX:.0f} kWh"),
                       (_SOC_MIN, f"运行下限 {_SOC_MIN:.0f} kWh")):
            ax.axhline(y, color=C_ACCENT, lw=1.1, ls=(0, (5, 2)), zorder=3)
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
        ax.legend(hs, ls_, frameon=False, ncol=4, loc="lower center",
                  bbox_to_anchor=(0.5, 1.005), handlelength=2.6, columnspacing=1.4)
        out = save(fig, "fig3a_soc_trajectory")
    return {"files": out, "meta": {"dates": targets}}


# ==============================================================================
#  图 3b  储电量分布与充放电量分布
# ==============================================================================
def fig3b() -> dict:
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
        ax1.hist(soc, bins=48, range=(_SOC_MIN, _SOC_MAX), color=C_SOC, alpha=0.85,
                 edgecolor="white", linewidth=0.4, zorder=3)
        for y, txt, dx, ha in ((_SOC_MIN, f"下限 {_SOC_MIN:.0f}\n{low_pct:.2f}% 时段",
                                150, "left"),
                               (_SOC_MAX, f"上限 {_SOC_MAX:.0f}\n{high_pct:.2f}% 时段",
                                -150, "right")):
            ax1.axvline(y, color=C_ACCENT, lw=1.1, ls=(0, (5, 2)), zorder=5)
            ax1.annotate(txt, xy=(y + dx, ax1.get_ylim()[1] * 0.70), ha=ha,
                         fontsize=7.8, color=C_ACCENT, zorder=9)
        ax1.set_xlabel("储电量 / kWh")
        ax1.set_ylabel("时段数")
        ax1.set_xlim(_SOC_MIN, _SOC_MAX)
        ax1.xaxis.set_major_locator(MaxNLocator(nbins=5))
        style(ax1)
        ax1.set_title("(a) 储电量分布（48,096 个时段）", pad=5, fontsize=9)

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
    return {"files": out, "meta": {"low_pct": low_pct, "high_pct": high_pct,
                                   "hit_charge_pct": hit_c, "hit_discharge_pct": hit_d}}


# ==============================================================================
#  图 4a  预测误差日内分布与逐月 MAE
# ==============================================================================
def fig4a() -> dict:
    rows = detail()
    eh, em_ = defaultdict(list), defaultdict(list)
    for r in rows:
        e = float(r["actual_net_kwh"]) - float(r["forecast_net_kwh"])
        eh[24 if r["time_start"] == "24:00" else int(r["time_start"][:2])].append(e)
        em_[r["date"][:7]].append(e)
    hours = sorted(eh)
    data = [np.array(eh[h]) for h in hours]
    months = sorted(em_)
    mae_m = np.array([float(np.abs(np.array(em_[m])).mean()) for m in months])
    all_e = np.array([e for v in eh.values() for e in v])
    imax = int(np.argmax(mae_m))

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(7.1, 4.7),
            gridspec_kw={"height_ratios": [1.75, 1.0], "hspace": 0.46})
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
                      f"{np.abs(all_e).mean():.2f}、偏置 {all_e.mean():+.2f} kWh/10分钟",
                      pad=5, fontsize=9)

        cols = [C_ACCENT if i == imax else C_GREY for i in range(len(months))]
        ax2.bar(np.arange(len(months)), mae_m, width=0.62, color=cols, alpha=0.90,
                zorder=3)
        ax2.axhline(float(np.abs(all_e).mean()), color=C_ACT, lw=1.1, ls=LS_ALT,
                    zorder=5)
        ax2.annotate(f"全期 MAE {np.abs(all_e).mean():.2f}",
                     xy=(len(months) - 0.5, float(np.abs(all_e).mean())),
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
    return {"files": out, "meta": {"mae": float(np.abs(all_e).mean()),
                                   "rmse": float(np.sqrt((all_e ** 2).mean())),
                                   "bias": float(all_e.mean()),
                                   "worst_month": months[imax],
                                   "worst_mae": float(mae_m[imax])}}


# ==============================================================================
#  图 4b  紧急购电的电价档与时刻分布
# ==============================================================================
def fig4b() -> dict:
    band = rd(DATA / "emergency_by_price_band.csv")
    order = ["谷(<0.5)", "平(0.5-0.9)", "峰(0.9-1.25)", "尖(≥1.25)"]
    lut = {r["price_band"]: r for r in band}
    bs = [b for b in order if b in lut]
    kwh = np.array([float(lut[b]["emergency_kwh"]) for b in bs])
    share = np.array([float(lut[b]["share_pct"]) for b in bs])
    cnt = np.array([int(float(lut[b]["intervals"])) for b in bs])
    cols = [C_MAIN, C_GREY, C_GREY_L, C_ACCENT]

    sc = rd(DATA / "emergency_scatter.csv")
    bh = defaultdict(int)
    for r in sc:
        bh[int(r["hour"])] += 1
    hours = sorted(bh)
    counts = np.array([bh[h] for h in hours])
    hmax = int(np.argmax(counts))
    hcols = [C_ACCENT if i == hmax else C_GREY for i in range(len(hours))]

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.1, 3.3),
                                       gridspec_kw={"width_ratios": [1.12, 1.0],
                                                    "wspace": 0.42})
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
    return {"files": out, "meta": {"peak_share": float(share[-1]),
                                   "intervals": int(counts.sum())}}


# ==============================================================================
#  图 5  策略费用对比与终端价值敏感性
# ==============================================================================
def fig5() -> dict:
    base = rd(DATA / "baseline_compare.csv")
    total = np.array([float(r["total_cost_yuan"]) for r in base])
    planned = np.array([float(r["planned_cost_yuan"]) for r in base])
    emer = np.array([float(r["emergency_cost_yuan"]) for r in base])
    names = ["主策略\n（本文模型）", "固定参考储能\n（局部反事实）", "无储能\n（基线）"]

    sens = rd(DATA / "sensitivity_terminal.csv")
    dates = sorted({r["date"] for r in sens})
    factors = sorted({float(r["terminal_value_factor"]) for r in sens})
    cost = {d: {} for d in dates}
    for r in sens:
        cost[r["date"]][float(r["terminal_value_factor"])] = float(r["natural_day_cost_yuan"])

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.1, 4.2),
                                       gridspec_kw={"width_ratios": [1.0, 1.05],
                                                    "wspace": 0.30})
        x = np.arange(len(base))
        ax1.bar(x, planned, width=0.52, color=C_MAIN, alpha=0.88, zorder=3)
        ax1.bar(x, emer, width=0.52, bottom=planned, color=C_ACCENT, alpha=0.95, zorder=4)
        ax1.set_xticks(x)
        ax1.set_xticklabels(names, fontsize=7.8)
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

        mk = [MK_ALT, MK_MAIN, MK_ALT2]
        ls = [LS_ALT, LS_MAIN, LS_ALT2]
        cl = [C_GREY, C_MAIN, C_ACT]
        xs = np.arange(len(dates))
        for k, f in enumerate(factors):
            vals = [cost[d][f] for d in dates]
            main = (f == 1)
            ax2.plot(xs, vals, color=C_ACCENT if main else cl[k],
                     lw=2.0 if main else 1.4, ls=LS_MAIN if main else ls[k],
                     marker=mk[k], ms=5.2 if main else 4.2,
                     mfc=C_ACCENT if main else "white",
                     mec=C_ACCENT if main else cl[k], mew=1.2,
                     zorder=6 if main else 5)
            if main:
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
    return {"files": out, "meta": {"saving": save_amt}}


# ============================ 入口 ============================
def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    print(f"字体 {FONT}   |   配色 低饱和蓝灰   |   PNG {PNG_DPI} dpi")
    print("-" * 76)
    jobs = [("图1  净负荷预测与情景包络", fig1),
            ("图1b 典型日功率与电价", fig1b),
            ("图2a 单日调度与电价", fig2a),
            ("图2b 月度购电量构成", fig2b),
            ("图3a 储电量轨迹", fig3a),
            ("图3b 储能分布", fig3b),
            ("图4a 预测误差", fig4a),
            ("图4b 紧急购电分布", fig4b),
            ("图5  策略对比与敏感性", fig5)]
    ok = 0
    for title, fn in jobs:
        try:
            res = fn()
            n = "  ".join(f"{k}:{Path(v).stat().st_size // 1024}KB"
                          for k, v in res["files"].items())
            print(f"  [OK]   {title:24s} {n}")
            ok += 1
        except Exception as exc:                         # noqa: BLE001
            print(f"  [FAIL] {title:24s} {type(exc).__name__}: {exc}")
    print("-" * 76)
    print(f"完成 {ok}/{len(jobs)} 张")
    return 0 if ok == len(jobs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
