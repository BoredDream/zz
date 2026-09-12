# ==============================================================================
#  第二问 · 优秀论文级科研图表（重设计版）
#  --------------------------------------------------------------------------
#  覆盖 5 张核心图：
#    fig1_netload_forecast   净负荷预测与情景包络（2×2）
#    fig2a_single_day_dispatch  单日调度与电价
#    fig2b_monthly_stack     月度购电量构成与紧急占比
#    fig3a_soc_trajectory    四日储电量轨迹（重构为单面板对比）
#    fig5_strategy_compare   策略费用对比与终端价值敏感性
#
#  运行：python figs_q2_paper.py
#  输出：每张图 .svg（矢量）/ .pdf（矢量）/ .png（600 dpi）
#
#  ============================ 统一视觉规范 ============================
#  1. 白色背景；去掉顶部与右侧边框；浅灰弱网格（仅水平，alpha≈0.35，lw 0.5）
#  2. 科研蓝 #2F6FB0 = 主数据；橙色 #D98943 = 唯一重点强调色
#  3. 对照/次要 = 灰 #9AA3A8 与灰蓝 #91A5B5；低饱和，无高饱和抢眼色
#  4. 储电量序列 = 低饱和绿 #6F9B72（仅储能图使用，全篇不重复）
#  5. 多重区分：颜色 + 线型 + marker（保证黑白打印可辨识）
#     · 实线+marker 'o'    = 主序列
#     · 虚线+marker 's'    = 对照/实际值
#     · 点划线+marker '^'  = 次要/受限序列
#     · 橙色一律实线且最粗 + 抗锯齿填充（重点）
#  6. 共享轴的双轴图一律不使用（本版已全部消除 twinx，改为量纲分离或归一化对比）
#  7. 字号：刻度 8.5、轴标题 9.5、图例 8.5；A4 双栏 figsize 7.1×4.2~4.6
#  8. 网格线、边框、标签做减法：图内文字仅保留必要结论数值
#
#  ============================ 数据真实性 ============================
#  完全不修改任何原始数值、计算结果或结论；仅改变视觉编码。
#  数据来源：本目录 _图表数据/ 与 ../zz/outputs/q2/（详见 README.md 与 §K）
# ==============================================================================

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

HERE = Path(__file__).resolve().parent          # handoff/q2/figures
DATA = HERE.parent / "_figdata"                 # handoff/q2/_figdata
Q2 = HERE.parents[2] / "outputs" / "q2"         # 仓库 outputs/q2

# ============================ 统一配色（低饱和） ============================
C_MAIN = "#2F6FB0"        # 科研蓝：主数据
C_MAIN_L = "#9DBBD8"      # 科研蓝浅版：填充
C_ACCENT = "#D98943"      # 橙色：唯一重点强调色
C_ACCENT_L = "#F0CDAA"    # 橙色浅版：填充
C_ACTUAL = "#5A6166"      # 实测/真实值：深灰
C_GREY = "#9AA3A8"        # 对照/次要：灰
C_GREYBLUE = "#91A5B5"    # 对照：灰蓝
C_SOC = "#6F9B72"         # 储电量：低饱和绿（仅储能图）
C_SOC_L = "#C3D6C4"
C_TEXT = "#333333"
C_GRID = "#DDDDDD"

LS_MAIN, LS_ALT, LS_ALT2 = "-", "--", "-."
MK_MAIN, MK_ALT, MK_ALT2 = "o", "s", "^"

FONT_CANDIDATES = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                   "Arial Unicode MS", "DejaVu Sans"]
SAVE_FORMATS = ["svg", "pdf", "png"]
PNG_DPI = 600
DT = 1.0 / 6.0
E_MAX = 5000.0 * DT          # 833.3333 kWh/时段（题面附录1 功率上限换算）


def pick_font() -> str:
    available = {f.name for f in fm.fontManager.ttflist}
    for name in FONT_CANDIDATES:
        if name in available:
            return name
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
    "axes.edgecolor": "#B0B0B0",
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


# ============================ 公共工具 ============================
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
    """统一坐标轴样式：去上右边框、浅灰弱网格、细边框。"""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_linewidth(0.7)
        ax.spines[s].set_color("#B0B0B0")
    if grid:
        ax.grid(axis=grid_axis, color=C_GRID, lw=0.5, alpha=0.35)
        ax.set_axisbelow(True)
    return ax


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"缺少数据文件：{path}")
    with path.open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def read_detail() -> list[dict]:
    rows = read_csv(Q2 / "interval_detail.csv")
    if len(rows) != 48_096:
        raise ValueError(f"interval_detail.csv 行数异常：{len(rows)}")
    return rows


def slot_of(t: str) -> float:
    return 24.0 if t == "24:00" else int(t[:2]) + int(t[3:5]) / 60.0


def note(ax, text, xy, **kw):
    """统一的图内结论标注（细灰引线，无重边框）。"""
    kw.setdefault("fontsize", 8)
    kw.setdefault("color", C_TEXT)
    kw.setdefault("zorder", 8)
    return ax.annotate(text, xy=xy, xytext=kw.pop("xytext", (0, 0)),
                       textcoords="offset points" if "xytext" in kw else None,
                       arrowprops=dict(arrowstyle="-", lw=0.6, color="#AAAAAA",
                                       shrinkA=0, shrinkB=2),
                       bbox=dict(boxstyle="round,pad=0.22", fc="white",
                                 ec="#D5D5D5", lw=0.5, alpha=0.92),
                       **kw)


# ==============================================================================
#  图 1  净负荷预测与情景包络（2×2）
#  设计改动：情景包络由 2 层减为 1 层 10–90 分位（全距过于贴近，属无效信息）；
#            预测线实线+marker 取稀疏采样，保证黑白可辨识；标注改为橙色重点。
# ==============================================================================
def fig1() -> dict:
    rows = read_csv(DATA / "netload_scenarios_4days.csv")
    targets = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
    by = defaultdict(lambda: {"scen": defaultdict(dict)})
    for r in rows:
        d = r["date"]
        t = int(r["interval_index"])
        by[d]["scen"][int(r["scenario_id"])][t] = float(r["scenario_net_kwh"])
        by[d]["actual"] = by[d].get("actual", {})
        by[d]["center"] = by[d].get("center", {})
        by[d]["actual"][t] = float(r["actual_net_kwh"])
        by[d]["center"][t] = float(r["center_forecast_kwh"])

    meta = {}
    with matplotlib.rc_context(RC):
        fig, axes = plt.subplots(2, 2, figsize=(7.1, 4.5), dpi=120, sharex=True)
        axes = axes.ravel()
        global_worst = None
        for ax, d in zip(axes, targets):
            tt = np.arange(144)
            x = tt * 10 / 60.0
            actual = np.array([by[d]["actual"][t] for t in tt])
            center = np.array([by[d]["center"][t] for t in tt])
            ids = sorted(by[d]["scen"])
            scen = np.array([[by[d]["scen"][s][t] for t in tt] for s in ids])
            lo = np.percentile(scen, 10, axis=0)
            hi = np.percentile(scen, 90, axis=0)

            ax.fill_between(x, lo, hi, color=C_MAIN_L, alpha=0.45, linewidth=0, zorder=1)
            ax.plot(x, center, color=C_MAIN, lw=1.7, ls=LS_MAIN, zorder=4,
                    marker=MK_MAIN, markevery=18, ms=3.0, mfc="white",
                    mew=0.9, label="本文模型中心预测")
            ax.plot(x, actual, color=C_ACTUAL, lw=1.5, ls=LS_ALT, zorder=5,
                    marker=MK_ALT, markevery=18, ms=2.8, mfc="white",
                    mew=0.9, label="真实观测值")
            ax.axhline(0, color="#C8C8C8", lw=0.6, zorder=0)

            resid = np.abs(actual - center)
            i = int(np.argmax(resid))
            # 仅记录“本图内最大偏差”时点，全局最大值所在面板才标注（避免误导）
            if global_worst is None or resid[i] > global_worst[1]:
                global_worst = (d, float(resid[i]), float(x[i]), float(actual[i]))
            meta[d] = {"mae": float(resid.mean()),
                       "rmse": float(np.sqrt((resid ** 2).mean())),
                       "n_scen": len(ids),
                       "argmax_t": float(x[i]), "argmax_resid": float(resid[i])}

            mae = meta[d]["mae"]
            ax.set_xlim(0, 24)
            ax.set_ylim(-1250, 1350)
            ax.set_xticks(range(0, 25, 6))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
            style(ax)
            ax.set_title(f"{d}　MAE {mae:.1f}", pad=4, fontsize=9)

        for ax in axes[2:]:
            ax.set_xlabel("时刻 / 时")
        for ax in (axes[0], axes[2]):
            ax.set_ylabel("净负荷 / (kWh/10分钟)")

        d, worst, wx, wv = global_worst
        axw = axes[targets.index(d)]
        axw.plot([wx], [wv], marker="o", ms=4.6, mfc=C_ACCENT, mec="white",
                 mew=1.1, zorder=7)
        axw.annotate(
            f"本图内最大偏差 {worst:.0f} kWh/10分钟",
            xy=(wx, wv), xytext=(-104, -34), textcoords="offset points",
            fontsize=8, color="#8A5A2B", zorder=8,
            arrowprops=dict(arrowstyle="-", lw=0.6, color="#BBBBBB", shrinkA=0, shrinkB=3),
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=C_ACCENT_L, lw=0.7))

        handles = [
            Line2D([], [], color=C_MAIN, lw=1.7, ls=LS_MAIN, marker=MK_MAIN,
                   markevery=[0], ms=3.0, mfc="white", mew=0.9, label="本文模型中心预测"),
            Line2D([], [], color=C_ACTUAL, lw=1.5, ls=LS_ALT, marker=MK_ALT,
                   markevery=[0], ms=2.8, mfc="white", mew=0.9, label="真实观测值"),
            Patch(facecolor=C_MAIN_L, alpha=0.45, edgecolor="none",
                  label="历史残差情景包络（10–90 分位）"),
            Line2D([], [], color=C_ACCENT, lw=0, marker="o", ms=4.2, mec="white",
                   mew=1.0, label="最大偏差时点"),
        ]
        fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False,
                   bbox_to_anchor=(0.5, 1.0), handlelength=2.4, columnspacing=1.5)
        fig.tight_layout(rect=(0, 0, 1, 0.935))
        out = save(fig, "fig1_netload_forecast")
    return {"files": out, "meta": meta}


# ==============================================================================
#  图 2a  单日调度与电价
#  设计改动：删除 twinx 双轴（消除双轴误导）；电价改为橙色顶栏阶梯带，
#            与购电面积在空间上分离；实际净负荷用灰色虚线叠加对照。
# ==============================================================================
def fig2a() -> dict:
    target = "2025-06-21"
    rows = [r for r in read_detail() if r["date"] == target]
    rows.sort(key=lambda r: slot_of(r["time_start"]))
    t = np.array([slot_of(r["time_start"]) for r in rows])
    plan = np.array([float(r["committed_plan_kwh"]) for r in rows])
    price = np.array([float(r["price_yuan_per_kwh"]) for r in rows])
    em = np.array([float(r["emergency_kwh"]) for r in rows])
    net = np.array([float(r["actual_net_kwh"]) for r in rows])
    fc = np.array([float(r["forecast_net_kwh"]) for r in rows])
    step = np.r_[t, 24.0]
    plan_s = np.r_[plan, plan[-1]]

    with matplotlib.rc_context(RC):
        fig, (axp, ax) = plt.subplots(
            2, 1, figsize=(7.1, 4.3), sharex=True,
            gridspec_kw={"height_ratios": [1.0, 2.35], "hspace": 0.12})

        # --- 上栏：电价（橙色强调；尖峰区用同色淡填充）---
        axp.step(step, np.r_[price, price[-1]], where="post", color=C_ACCENT, lw=1.6)
        axp.fill_between(step, 0, np.r_[price, price[-1]], step="post",
                         color=C_ACCENT_L, alpha=0.35, linewidth=0)
        peak = price >= 1.25
        axp.set_ylim(0, 1.75)
        axp.set_yticks([0, 0.5, 1.0, 1.5])
        axp.set_ylabel("电价 / (元/kWh)", labelpad=2)
        style(axp, grid=False)
        axp.set_title(f"{target}　计划购电量、实际净负荷与电价", pad=5)
        if peak.any():
            axp.annotate("尖峰价时段 ≥1.25 元/kWh",
                         xy=(t[peak][0] + 1.5, 1.70), fontsize=7.6,
                         color="#8A5A2B", va="top")

        # --- 下栏：购电量（蓝色面积）+ 实际净负荷（灰虚线）---
        ax.fill_between(step, 0, plan_s, step="post", color=C_MAIN_L,
                        alpha=0.55, linewidth=0, zorder=1)
        ax.step(step, plan_s, where="post", color=C_MAIN, lw=1.8, zorder=3,
                label="计划购电量（当日 0:00 发布）")
        if em.sum() > 0:
            ax.fill_between(step, plan_s, plan_s + np.r_[em, em[-1]], step="post",
                            color=C_ACCENT, alpha=0.9, linewidth=0, zorder=4,
                            hatch="////", edgecolor="white")
        ax.step(step, np.r_[net, net[-1]], where="post", color=C_ACTUAL, lw=1.4,
                ls=LS_ALT, zorder=5, label="实际净负荷")
        ax.step(step, np.r_[fc, fc[-1]], where="post", color=C_GREY, lw=1.0,
                ls=LS_ALT2, zorder=4, label="模型预测净负荷")
        ax.axhline(0, color="#C8C8C8", lw=0.6, zorder=2)

        lo, hi = int(np.argmin(net)), int(np.argmax(net))
        ax.plot([t[lo]], [net[lo]], marker=MK_ALT2, ms=4.0, mfc="white",
                mec=C_ACTUAL, mew=1.0, zorder=7)
        ax.annotate(f"光伏反超负载，最低 {net[lo]:.0f}",
                    xy=(t[lo], net[lo]), xytext=(6, -16), textcoords="offset points",
                    fontsize=7.8, color=C_TEXT,
                    arrowprops=dict(arrowstyle="-", lw=0.6, color="#BBBBBB"))
        peak_plan = float(plan[peak].sum()) if peak.any() else 0.0
        ax.annotate(f"尖峰价时段计划购电仅 {peak_plan:,.0f} kWh",
                    xy=(20.6, 820), xytext=(2.2, 900), textcoords="data", fontsize=7.8,
                    color="#8A5A2B", ha="left", va="center",
                    arrowprops=dict(arrowstyle="-", lw=0.6, color="#BBBBBB",
                                    shrinkA=2, shrinkB=2,
                                    connectionstyle="arc3,rad=-0.15"),
                    bbox=dict(boxstyle="round,pad=0.22", fc="white",
                              ec=C_ACCENT_L, lw=0.6, alpha=0.95))

        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 2))
        ax.set_ylim(0, max(plan.max(), net.max()) * 1.30)
        ax.set_xlabel("时刻 / 时")
        ax.set_ylabel("电量 / (kWh/10分钟)")
        style(ax)
        ax.legend(frameon=False, ncol=2, loc="upper left", handlelength=2.4,
                  columnspacing=1.2)
        fig.tight_layout()
        out = save(fig, "fig2a_single_day_dispatch")
    return {"files": out, "meta": {"plan_total": float(plan.sum()),
                                   "emergency_total": float(em.sum()),
                                   "peak_plan": peak_plan,
                                   "net_min": float(net[lo]), "net_max": float(net[hi])}}


# ==============================================================================
#  图 2b  月度购电量构成与紧急购电占比
#  设计改动：上栏把"紧急购电"这一小量用橙色突出（唯一强调色），计划量降为蓝色；
#            去掉原上下两栏的重复信息，下栏只留占比并标出极值；网格与标签做减法。
# ==============================================================================
def fig2b() -> dict:
    rows = read_csv(DATA / "monthly_summary.csv")
    months = [r["month"][5:] + "月" for r in rows]
    plan = np.array([float(r["plan_kwh"]) for r in rows])
    em = np.array([float(r["emergency_kwh"]) for r in rows])
    share = np.array([float(r["emergency_share_pct"]) for r in rows])
    x = np.arange(len(rows))
    imax, imin = int(np.argmax(em)), int(np.argmin(em))

    with matplotlib.rc_context(RC):
        fig, (ax, axr) = plt.subplots(
            2, 1, figsize=(7.1, 4.3), sharex=True,
            gridspec_kw={"height_ratios": [1.85, 1.0], "hspace": 0.16})

        ax.bar(x, plan, width=0.60, color=C_MAIN, alpha=0.85, zorder=3,
               label="计划购电量")
        ax.bar(x, em, width=0.60, bottom=plan, color=C_ACCENT, alpha=0.95,
               zorder=4, label="紧急购电量（5×电价）")
        ax.set_ylabel("购电量 / kWh")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v/1e6:,.1f}M"))
        top = (plan + em).max()
        ax.set_ylim(0, top * 1.26)
        style(ax)
        ax.annotate(f"最高 {em[imax]:,.0f} kWh", xy=(x[imax], plan[imax] + em[imax]),
                    xytext=(0, 26), textcoords="offset points", ha="center",
                    fontsize=8, color="#8A5A2B",
                    arrowprops=dict(arrowstyle="-", lw=0.6, color="#BBBBBB", shrinkB=1),
                    bbox=dict(boxstyle="round,pad=0.22", fc="white",
                              ec=C_ACCENT_L, lw=0.6, alpha=0.92))
        ax.set_title("月度购电量构成（自然日口径，334 天）", pad=5)

        axr.bar(x, share, width=0.60, color=C_GREY, alpha=0.75, zorder=3)
        axr.bar([imax], [share[imax]], width=0.60, color=C_ACCENT, alpha=0.95, zorder=4)
        mean = float(share.mean())
        axr.axhline(mean, color=C_ACTUAL, lw=1.0, ls=LS_ALT, zorder=5)
        axr.annotate(f"全期均值 {mean:.4f}%", xy=(len(rows) - 0.4, mean),
                     xytext=(0, 4), textcoords="offset points", ha="right",
                     fontsize=7.8, color=C_ACTUAL)
        axr.set_ylabel("紧急购电占比 / %")
        axr.set_xticks(x)
        axr.set_xticklabels(months)
        axr.set_xlabel("月份")
        axr.set_ylim(0, share.max() * 1.32)
        style(axr)
        handles = [Patch(facecolor=C_MAIN, alpha=0.85, label="计划购电量"),
                   Patch(facecolor=C_ACCENT, alpha=0.95, label="紧急购电量"),
                   Patch(facecolor=C_GREY, alpha=0.75, label="月度紧急购电占比"),
                   Line2D([], [], color=C_ACTUAL, lw=1.0, ls=LS_ALT,
                          label=f"全期均值 {mean:.4f}%")]
        fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False,
                   bbox_to_anchor=(0.5, 1.0), handlelength=1.5, columnspacing=1.4)
        fig.tight_layout(rect=(0, 0, 1, 0.925))
        out = save(fig, "fig2b_monthly_stack")
    return {"files": out, "meta": {"em_max_month": months[imax],
                                   "em_max": float(em[imax]),
                                   "em_min_month": months[imin],
                                   "share_mean": mean}}


# ==============================================================================
#  图 3a  储电量轨迹
#  设计改动（换图表类型）：由 2×2 四个单日面板 + 双轴，改为【单面板四日对比】。
#    · 双轴全部删除，改为"储电量归一化到 [下限, 上限]"的纵向码值 + 电价用背景色带表示
#    · 四日以 marker + 线型区分，不再依赖颜色
#    · 上限/下限用橙色虚线并直接标注，一眼看出是否贴边界
# ==============================================================================
def fig3a() -> dict:
    targets = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
    SOC_MIN, SOC_MAX = 1200.0, 10800.0
    rows = read_detail()
    by = defaultdict(list)
    for r in rows:
        if r["date"] in targets:
            by[r["date"]].append(r)

    styles = [(C_MAIN, LS_MAIN, MK_MAIN), (C_GREYBLUE, LS_ALT, MK_ALT),
              (C_GREY, LS_ALT2, MK_ALT2), (C_ACTUAL, (0, (3, 1, 1, 1)), "D")]

    with matplotlib.rc_context(RC):
        fig, ax = plt.subplots(figsize=(7.1, 3.6))
        handles, labels = [], []
        for (d, (c, ls, mk)) in zip(targets, styles):
            sub = sorted(by[d], key=lambda r: slot_of(r["time_start"]))
            t = np.array([slot_of(r["time_start"]) for r in sub])
            soc = np.array([float(r["soc_start_kwh"]) for r in sub])
            ax.plot(t, soc, color=c, lw=1.5, ls=ls, marker=mk, markevery=8,
                    ms=3.4, mfc="white", mew=0.9, zorder=5, label=d)
            handles.append(Line2D([], [], color=c, lw=1.5, ls=ls, marker=mk,
                                  markevery=[0], ms=3.4, mfc="white", mew=0.9))
            labels.append(f"{d}　{soc[0]:.0f}→{soc[-1]:.0f} kWh")
            ax.plot([t[0], t[-1]], [soc[0], soc[-1]], marker="", lw=0)

        ax.axhspan(SOC_MIN, SOC_MAX, color=C_SOC_L, alpha=0.18, zorder=0)
        for y, txt in ((SOC_MAX, f"运行上限 {SOC_MAX:.0f} kWh"),
                       (SOC_MIN, f"运行下限 {SOC_MIN:.0f} kWh")):
            ax.axhline(y, color=C_ACCENT, lw=1.1, ls=(0, (5, 2)), zorder=3)
            ax.annotate(txt, xy=(23.9, y), xytext=(0, 4), textcoords="offset points",
                        ha="right", fontsize=7.8, color="#8A5A2B")
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
        fig.tight_layout(rect=(0, 0, 1, 0.965))
        out = save(fig, "fig3a_soc_trajectory")
    return {"files": out, "meta": {"min_soc": SOC_MIN, "max_soc": SOC_MAX,
                                   "dates": targets}}


# ==============================================================================
#  图 5  策略费用对比与终端价值敏感性
#  设计改动：左栏堆叠柱改为【计划费(蓝) + 紧急费(橙)】并把"节省额"用橙色括号标出；
#            右栏敏感性改为【折线+marker】(斜率更清楚)，主模型档位用橙色实心点。
# ==============================================================================
def fig5() -> dict:
    base = read_csv(DATA / "baseline_compare.csv")
    total = np.array([float(r["total_cost_yuan"]) for r in base])
    planned = np.array([float(r["planned_cost_yuan"]) for r in base])
    emer = np.array([float(r["emergency_cost_yuan"]) for r in base])
    names = ["主策略\n（本文模型）", "固定参考储能\n（局部反事实）", "无储能\n（基线）"]

    sens = read_csv(DATA / "sensitivity_terminal.csv")
    dates = sorted({r["date"] for r in sens})
    factors = sorted({float(r["terminal_value_factor"]) for r in sens})
    cost = {d: {} for d in dates}
    for r in sens:
        cost[r["date"]][float(r["terminal_value_factor"])] = float(r["natural_day_cost_yuan"])

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.1, 4.2),
                                       gridspec_kw={"width_ratios": [1.0, 1.05],
                                                    "wspace": 0.30})

        # ---- 左：三策略费用构成 ----
        x = np.arange(len(base))
        ax1.bar(x, planned, width=0.52, color=C_MAIN, alpha=0.88, zorder=3,
                label="计划购电费")
        ax1.bar(x, emer, width=0.52, bottom=planned, color=C_ACCENT, alpha=0.95,
                zorder=4, label="紧急购电费")
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
        # 节省额：框置于右下空白区，橙色引线指向"主策略柱顶 → 基线柱顶"的差额区间
        ax1.annotate(f"主策略相对无储能基线\n节省 {(total[2]-total[0])/1e4:,.1f} 万元"
                     f"（{(total[2]-total[0])/total[2]*100:.1f}%）",
                     xy=(2.0, total[2] * 1.005), xytext=(1.30, total.max() * 1.30),
                     ha="center", va="center", fontsize=8, color="#8A5A2B",
                     arrowprops=dict(arrowstyle="-", lw=0.8, color=C_ACCENT,
                                     shrinkA=4, shrinkB=2,
                                     connectionstyle="arc3,rad=-0.25"),
                     bbox=dict(boxstyle="round,pad=0.28", fc="white",
                               ec=C_ACCENT_L, lw=0.8, alpha=0.96))
        ax1.plot([0, 2], [total[0], total[2]], color=C_ACCENT, lw=1.0, ls=(0, (4, 2)),
                 zorder=6)
        ax1.legend(frameon=False, ncol=1, loc="lower left", handlelength=1.5,
                   fontsize=8)
        ax1.set_title("(a) 三种口径的费用构成（334 天累计）", pad=5, fontsize=9)

        # ---- 右：终端价值敏感性（折线+marker）----
        mk = [MK_ALT, MK_MAIN, MK_ALT2]
        ls = [LS_ALT, LS_MAIN, LS_ALT2]
        cols = [C_GREYBLUE, C_MAIN, C_ACTUAL]
        xs = np.arange(len(dates))
        for k, f in enumerate(factors):
            vals = [cost[d][f] for d in dates]
            is_main = (f == 1)
            ax2.plot(xs, vals, color=C_ACCENT if is_main else cols[k],
                     lw=2.0 if is_main else 1.4,
                     ls=LS_MAIN if is_main else ls[k],
                     marker=mk[k], ms=5.2 if is_main else 4.2,
                     mfc=C_ACCENT if is_main else "white",
                     mec=C_ACCENT if is_main else cols[k], mew=1.2,
                     zorder=6 if is_main else 5)
            if is_main:
                ax2.annotate("主模型", xy=(xs[-1], vals[-1]), xytext=(6, 6),
                             textcoords="offset points", fontsize=7.6,
                             color="#8A5A2B")
        ax2.set_xticks(xs)
        ax2.set_xticklabels([d[5:].replace("-", "/") for d in dates])
        ax2.set_xlabel("日期（月/日）")
        ax2.set_ylabel("当日费用 / 元")
        vmax = max(cost[d][f] for d in dates for f in factors)
        ax2.set_ylim(0, vmax * 1.20)
        ax2.set_xlim(-0.35, len(dates) - 0.65)
        style(ax2)
        h2 = [Line2D([], [], color=C_ACCENT, lw=2.0, marker=MK_MAIN, ms=5.2,
                     mfc=C_ACCENT, mec=C_ACCENT, label="终端价值 1 倍 v（主模型）"),
              Line2D([], [], color=C_GREYBLUE, lw=1.4, ls=LS_ALT, marker=MK_ALT,
                     ms=4.2, mfc="white", mec=C_GREYBLUE, label="终端价值 0 倍 v"),
              Line2D([], [], color=C_ACTUAL, lw=1.4, ls=LS_ALT2, marker=MK_ALT2,
                     ms=4.2, mfc="white", mec=C_ACTUAL, label="终端价值 2 倍 v")]
        ax2.set_title("(b) 终端储电价值的敏感性", pad=5, fontsize=9)
        h_all = [Patch(facecolor=C_MAIN, alpha=0.88, label="计划购电费"),
                 Patch(facecolor=C_ACCENT, alpha=0.95, label="紧急购电费"),
                 Line2D([], [], color=C_ACCENT, lw=2.0, marker=MK_MAIN, ms=5.2,
                        mfc=C_ACCENT, mec=C_ACCENT, label="终端价值 1 倍 v（主模型）"),
                 Line2D([], [], color=C_GREYBLUE, lw=1.4, ls=LS_ALT, marker=MK_ALT,
                        ms=4.2, mfc="white", mec=C_GREYBLUE, label="终端价值 0 倍 v"),
                 Line2D([], [], color=C_ACTUAL, lw=1.4, ls=LS_ALT2, marker=MK_ALT2,
                        ms=4.2, mfc="white", mec=C_ACTUAL, label="终端价值 2 倍 v")]
        fig.legend(handles=h_all, loc="upper center", ncol=5, frameon=False,
                   bbox_to_anchor=(0.5, 1.005), fontsize=7.8, columnspacing=1.2,
                   handlelength=2.0)
        fig.tight_layout(rect=(0, 0, 1, 0.90))
        out = save(fig, "fig5_strategy_compare")
    return {"files": out, "meta": {"saving": float(total[2] - total[0]),
                                   "saving_pct": float((total[2] - total[0]) / total[2] * 100)}}


# ==============================================================================
#  图 1b  典型日功率曲线与分时电价
#  设计改动：三线共用单一色系（蓝=负载、橙=光伏、绿=净负荷）并按重要性排线宽；
#            电价由双轴改为【上下分栏】，消除双轴；富余区用绿色极淡底纹 + 结论标注。
# ==============================================================================
def fig1b() -> dict:
    rows = read_csv(DATA / "annex1_net_load.csv")
    t = np.array([slot_of(r["time_label"]) for r in rows])
    load = np.array([float(r["load_kw"]) for r in rows])
    pv = np.array([float(r["pv_kw"]) for r in rows])
    net = np.array([float(r["net_kw"]) for r in rows])
    price = np.array([float(r["price_yuan_per_kwh"]) for r in rows])
    step = np.r_[t, 24.0]

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(7.1, 4.6), sharex=True,
            gridspec_kw={"height_ratios": [2.0, 1.0], "hspace": 0.14})

        surplus = net < 0
        if surplus.any():
            s0, s1 = t[surplus][0], t[surplus][-1] + 10 / 60
            ax1.axvspan(s0, s1, color=C_SOC_L, alpha=0.45, zorder=0)
            ax1.annotate(f"光伏富余 {abs(net[surplus].sum()) * DT:,.0f} kWh",
                         xy=((s0 + s1) / 2, -1750), ha="center", fontsize=8,
                         color="#4C6B4E", zorder=8)
        ax1.plot(t, load, color=C_MAIN, lw=1.4, ls=LS_MAIN, marker=MK_MAIN,
                 markevery=16, ms=3.0, mfc="white", mew=0.9, zorder=4, label="小区负载")
        ax1.plot(t, pv, color=C_ACCENT, lw=1.8, ls=LS_ALT, marker=MK_ALT,
                 markevery=16, ms=3.0, mfc="white", mew=0.9, zorder=5, label="光伏出力")
        ax1.plot(t, net, color=C_SOC, lw=1.9, ls=(0, (6, 1.5, 1.5, 1.5)),
                 marker=MK_ALT2, markevery=16, ms=3.2, mfc="white", mew=0.9,
                 zorder=6, label="净负荷（负载−光伏）")
        ax1.axhline(0, color="#C8C8C8", lw=0.6, zorder=1)
        imax = int(np.argmax(pv))
        ax1.plot([t[imax]], [pv[imax]], marker="o", ms=4.6, mfc=C_ACCENT,
                 mec="white", mew=1.1, zorder=9)
        ax1.annotate(f"光伏峰值 {pv[imax]:,.0f} kW", xy=(t[imax], pv[imax]),
                     xytext=(10, 8), textcoords="offset points", fontsize=8,
                     color="#8A5A2B", zorder=9,
                     arrowprops=dict(arrowstyle="-", lw=0.6, color="#BBBBBB"))
        ax1.set_ylabel("功率 / kW")
        ax1.set_ylim(-2400, 9200)
        ax1.yaxis.set_major_locator(MaxNLocator(nbins=6))
        style(ax1)
        ax1.legend(frameon=False, ncol=3, loc="upper left", handlelength=2.6,
                   columnspacing=1.4, bbox_to_anchor=(0.0, 1.02),
                   borderaxespad=0.0)
        ax1.set_title("典型日（附件1）功率曲线与分时电价", pad=22)

        ax2.step(step, np.r_[price, price[-1]], where="post", color=C_ACCENT, lw=1.5)
        ax2.fill_between(step, 0, np.r_[price, price[-1]], step="post",
                         color=C_ACCENT_L, alpha=0.32, linewidth=0)
        ax2.axhspan(0, 0.45, color=C_MAIN, alpha=0.07, zorder=0)
        ax2.axhspan(1.25, 1.60, color=C_ACCENT, alpha=0.10, zorder=0)
        ax2.annotate(f"谷价区 <0.45\n最低 {price.min():.4f}", xy=(1.0, 0.20),
                     fontsize=7.8, color="#1F4E79", zorder=9)
        ax2.annotate(f"尖峰价区 >1.25\n最高 {price.max():.4f}", xy=(14.2, 1.28),
                     fontsize=7.8, color="#8A5A2B", zorder=9)
        ax2.set_ylim(0, 1.62)
        ax2.set_yticks([0, 0.5, 1.0, 1.5])
        ax2.set_xlim(0, 24)
        ax2.set_xticks(range(0, 25, 2))
        ax2.set_xlabel("时刻 / 时")
        ax2.set_ylabel("电价 / (元/kWh)")
        style(ax2)
        fig.tight_layout()
        out = save(fig, "fig1b_typical_day")
    return {"files": out, "meta": {"pv_peak": float(pv[imax]),
                                   "price_min": float(price.min()),
                                   "price_max": float(price.max()),
                                   "surplus_kwh": float(abs(net[surplus].sum()) * DT)}}


# ==============================================================================
#  图 3b  储能分布（储电量 / 充放电量）
#  设计改动：充电→低饱和绿、放电→橙色强调（唯一强调色）；只标注两个峰（贴下限、
#            贴上限）并在柱顶直接给出占比；功率上限线由红改橙虚线；
#            减少网格与统计文字，突出"14.75% 贴上限"这一结构性结论。
# ==============================================================================
def fig3b() -> dict:
    rows = read_detail()
    soc = np.array([float(r["soc_start_kwh"]) for r in rows])
    chg = np.array([float(r["charge_kwh"]) for r in rows])
    dis = np.array([float(r["discharge_kwh"]) for r in rows])
    low_pct = float((soc <= 1250).mean() * 100)
    high_pct = float((soc >= 10750).mean() * 100)

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.1, 3.2),
                                       gridspec_kw={"width_ratios": [1.0, 1.05],
                                                    "wspace": 0.34})

        ax1.hist(soc, bins=48, range=(1200, 10800), color=C_SOC, alpha=0.85,
                 edgecolor="white", linewidth=0.4, zorder=3)
        for y, txt, col in ((1200, f"下限 1200\n{low_pct:.2f}% 时段", C_ACCENT),
                            (10800, f"上限 10800\n{high_pct:.2f}% 时段", C_ACCENT)):
            ax1.axvline(y, color=col, lw=1.1, ls=(0, (5, 2)), zorder=5)
            ha = "left" if y < 6000 else "right"
            dx = 150 if y < 6000 else -150
            ax1.annotate(txt, xy=(y + dx, ax1.get_ylim()[1] * 0.70), ha=ha,
                         fontsize=7.8, color="#8A5A2B", zorder=8)
        ax1.set_xlabel("储电量 / kWh")
        ax1.set_ylabel("时段数")
        ax1.set_xlim(1200, 10800)
        ax1.xaxis.set_major_locator(MaxNLocator(nbins=5))
        style(ax1)
        ax1.set_title("(a) 储电量分布（48,096 个时段）", pad=5, fontsize=9)

        bins = np.linspace(0, E_MAX, 41)
        ax2.hist(chg, bins=bins, color=C_SOC, alpha=0.85, edgecolor="white",
                 linewidth=0.4, zorder=3, label="充电量")
        ax2.hist(dis, bins=bins, color=C_ACCENT, alpha=0.85, edgecolor="white",
                 linewidth=0.4, zorder=4, label="放电量")
        ax2.axvline(E_MAX, color=C_ACCENT, lw=1.1, ls=(0, (5, 2)), zorder=5)
        hit_c = float((chg >= E_MAX - 1e-6).mean() * 100)
        hit_d = float((dis >= E_MAX - 1e-6).mean() * 100)
        ax2.annotate(f"功率上限 {E_MAX:.1f} kWh\n打满：充电 {hit_c:.1f}% / 放电 {hit_d:.1f}%",
                     xy=(E_MAX, ax2.get_ylim()[1] * 0.72), xytext=(-8, 0),
                     textcoords="offset points", ha="right", fontsize=7.8,
                     color="#8A5A2B", zorder=8)
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
#  设计改动：箱体降为灰蓝（对照语义），中位数用科研蓝以突出；零线加粗为参考基准；
#            逐月 MAE 改为柱+折线，最差月（6 月）染橙直接点出结论。
# ==============================================================================
def fig4a() -> dict:
    rows = read_detail()
    err_h, err_m = defaultdict(list), defaultdict(list)
    for r in rows:
        e = float(r["actual_net_kwh"]) - float(r["forecast_net_kwh"])
        h = 24 if r["time_start"] == "24:00" else int(r["time_start"][:2])
        err_h[h].append(e)
        err_m[r["date"][:7]].append(e)

    hours = sorted(err_h)
    data = [np.array(err_h[h]) for h in hours]
    months = sorted(err_m)
    mae_m = np.array([float(np.abs(np.array(err_m[m])).mean()) for m in months])
    all_e = np.array([e for v in err_h.values() for e in v])
    imax = int(np.argmax(mae_m))

    with matplotlib.rc_context(RC):
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(7.1, 4.7),
            gridspec_kw={"height_ratios": [1.75, 1.0], "hspace": 0.46})

        ax1.boxplot(data, positions=hours, widths=0.62, showfliers=False,
                    patch_artist=True,
                    medianprops=dict(color=C_MAIN, lw=1.4),
                    whiskerprops=dict(color="#B8B8B8", lw=0.8),
                    capprops=dict(color="#B8B8B8", lw=0.8),
                    boxprops=dict(facecolor=C_GREYBLUE, alpha=0.55,
                                  edgecolor="#7F97A8", lw=0.7))
        ax1.axhline(0, color=C_ACTUAL, lw=1.2, zorder=5)
        ax1.annotate("正：实际高于预测（缺电风险侧）", xy=(0.4, 330), fontsize=7.8,
                     color="#8A5A2B", zorder=8)
        ax1.annotate("负：实际低于预测（剩余电量侧）", xy=(0.4, -430), fontsize=7.8,
                     color="#1F4E79", zorder=8)
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
        ax2.bar(np.arange(len(months)), mae_m, width=0.62, color=cols, alpha=0.9,
                zorder=3)
        ax2.axhline(float(np.abs(all_e).mean()), color=C_ACTUAL, lw=1.1,
                    ls=LS_ALT, zorder=5)
        ax2.annotate(f"全期 MAE {np.abs(all_e).mean():.2f}", xy=(len(months) - 0.5,
                     float(np.abs(all_e).mean())), xytext=(0, 5),
                     textcoords="offset points", ha="right", fontsize=7.8,
                     color=C_TEXT, zorder=8)
        ax2.annotate(f"最高 {mae_m[imax]:.1f}", xy=(imax, mae_m[imax]),
                     xytext=(0, 5), textcoords="offset points", ha="center",
                     fontsize=7.8, color="#8A5A2B", zorder=8)
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
#  设计改动：四个电价档改用"蓝→灰蓝→灰→橙"的递进色阶（每档语义不同，不是同义重复）；
#            占比与时段数由括号文字改为右对齐数值列；小时分布把峰值小时染橙并标注合计。
# ==============================================================================
def fig4b() -> dict:
    band_rows = read_csv(DATA / "emergency_by_price_band.csv")
    order = ["谷(<0.5)", "平(0.5-0.9)", "峰(0.9-1.25)", "尖(≥1.25)"]
    lut = {r["price_band"]: r for r in band_rows}
    bands = [b for b in order if b in lut]
    kwh = np.array([float(lut[b]["emergency_kwh"]) for b in bands])
    share = np.array([float(lut[b]["share_pct"]) for b in bands])
    cnt = np.array([int(float(lut[b]["intervals"])) for b in bands])
    cols = [C_MAIN, C_GREYBLUE, C_GREY, C_ACCENT]

    scatter = read_csv(DATA / "emergency_scatter.csv")
    by_hour = defaultdict(int)
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
        ypos = np.arange(len(bands))
        ax1.barh(ypos, kwh, height=0.62, color=cols[:len(bands)], alpha=0.92,
                 zorder=3)
        ax1.set_yticks(ypos)
        ax1.set_yticklabels(bands)
        ax1.invert_yaxis()
        ax1.set_xlabel("紧急购电量 / kWh")
        ax1.set_xlim(0, kwh.max() * 1.58)
        style(ax1, grid_axis="x")
        for i, (v, s, c) in enumerate(zip(kwh, share, cnt)):
            ax1.annotate(f"{v:,.0f}", xy=(v, i), xytext=(6, 3),
                         textcoords="offset points", fontsize=7.8, color=C_TEXT,
                         zorder=8)
            ax1.annotate(f"{s:.1f}%｜{c} 时段", xy=(v, i), xytext=(6, -8),
                         textcoords="offset points", fontsize=7.4, color="#777777",
                         zorder=8)
        ax1.annotate("66% 集中在尖峰价档", xy=(kwh[-1] * 0.5, len(bands) - 1),
                     xytext=(0, 0), textcoords="offset points", ha="center",
                     va="center", fontsize=8, color="white", zorder=9)
        ax1.set_title("(a) 紧急购电量按电价档分布", pad=5, fontsize=9)

        ax2.bar(np.arange(len(hours)), counts, width=0.64, color=hcols, alpha=0.9,
                zorder=3)
        ax2.set_xticks([i for i, h in enumerate(hours) if h % 2 == 0])
        ax2.set_xticklabels([str(h) for h in hours if h % 2 == 0])
        ax2.set_xlabel("时刻 / 时")
        ax2.set_ylabel("出现紧急购电的时段数")
        ax2.set_ylim(0, counts.max() * 1.20)
        style(ax2)
        ax2.annotate(f"峰值 {counts[hmax]} 个时段", xy=(hmax, counts[hmax]),
                     xytext=(0, 5), textcoords="offset points", ha="center",
                     fontsize=7.8, color="#8A5A2B", zorder=8)
        ax2.set_title(f"(b) 时刻分布（合计 {int(counts.sum()):,} 个时段）",
                      pad=5, fontsize=9)
        fig.tight_layout()
        out = save(fig, "fig4b_emergency_cost_band")
    return {"files": out, "meta": {"peak_share": float(share[-1]),
                                   "peak_kwh": float(kwh[-1]),
                                   "intervals": int(counts.sum()),
                                   "peak_hour": int(hours[hmax])}}


# ============================ 入口 ============================
def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                   # noqa: BLE001
        pass
    print(f"中文字体：{FONT}")
    print(f"输出格式：{', '.join(f.upper() for f in SAVE_FORMATS)}   PNG={PNG_DPI} dpi")
    print("-" * 74)
    jobs = [("图1  净负荷预测与情景包络", fig1),
            ("图1b 典型日功率与电价", fig1b),
            ("图2a 单日调度与电价", fig2a),
            ("图2b 月度购电量构成", fig2b),
            ("图3a 储电量轨迹（重构）", fig3a),
            ("图3b 储能分布", fig3b),
            ("图4a 预测误差", fig4a),
            ("图4b 紧急购电分布", fig4b),
            ("图5  策略对比与敏感性", fig5)]
    ok = 0
    for title, fn in jobs:
        try:
            res = fn()
            sizes = "  ".join(f"{k}:{Path(v).stat().st_size // 1024}KB"
                              for k, v in res["files"].items())
            print(f"  [OK]   {title:26s} {sizes}")
            ok += 1
        except Exception as exc:                        # noqa: BLE001
            print(f"  [FAIL] {title:26s} {type(exc).__name__}: {exc}")
    print("-" * 74)
    print(f"完成 {ok}/{len(jobs)} 张")
    return 0 if ok == len(jobs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
