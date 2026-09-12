"""第三问 论文级科研图表（统一主脚本）。

依据《数学建模论文科研绘图指导规范》与 handoff/q3/图表规划.md。
一个脚本产出全部 9 个图号 / 14 个文件，统一颜色语义、字号、线宽、网格、边框与保存方式。

数据来源（只读，不重跑求解器）：
    handoff/q3/_figdata/*.csv + q3_meta.json

运行：
    python figures/figs_q3_paper.py
输出：
    figures/*.svg / *.pdf / *.png(600dpi)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager, rcParams
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
HANDOFF = HERE.parent
DATA = HANDOFF / "_figdata"

# =============================================================================
# 一、视觉规范常量（全文统一；改这里即全文生效）
# =============================================================================
C_MAIN = "#4C6E91"      # 主模型 / 本文方法 / 主数据
C_MAIN_D = "#3A5470"    # 深版主色
C_ACT = "#5B6470"       # 真实值 / 实测值
C_GREY = "#9AA4AE"      # 普通对照 / 次要数据
C_GREY_L = "#C9D0D6"    # 浅灰辅助
C_ACCENT = "#A9705A"    # 风险 / 最大误差 / 紧急 / 最差结果（全篇唯一强调色）
C_STATE = "#7E9B84"     # 状态类 / 边界类指标
C_GRID = "#DFE3E7"      # 网格
C_TEXT = "#333333"      # 文字
C_SPINE = "#B4BBC2"     # 边框

FS_TICK, FS_LABEL, FS_LEG, FS_PANEL, FS_NOTE = 8.5, 9.5, 8.5, 9.0, 7.5

Z_GRID, Z_BASE, Z_DATA, Z_NOTE = 0, 2, 4, 6
U_PRICE = "电价 / (元/kWh)"
U_KWH = "电量 / kWh"
U_POWER = "功率 / kW"


def _pick_font() -> str:
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC",
                 "PingFang SC", "WenQuanYi Zen Hei"):
        if name in have:
            return name
    return "DejaVu Sans"


FONT = _pick_font()
rcParams.update({
    "font.family": FONT,
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
    "svg.fonttype": "none",          # SVG 文字保持可编辑
    "pdf.fonttype": 42,              # PDF 矢量 + 可编辑文字
    "font.size": FS_TICK,
})


# =============================================================================
# 二、公共工具
# =============================================================================
def style(ax, grid_axis: str = "y") -> None:
    """统一坐标轴样式：去上/右边框、浅灰左/下边框、仅水平浅网格。"""
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(C_SPINE)
        ax.spines[s].set_linewidth(0.7)
    ax.tick_params(colors=C_TEXT, labelsize=FS_TICK, width=0.7, length=3,
                   color=C_SPINE, direction="out")
    if grid_axis in ("y", "both"):
        ax.grid(axis="y", color=C_GRID, lw=0.5, alpha=0.20, zorder=Z_GRID)
    if grid_axis in ("x", "both"):
        ax.grid(axis="x", color=C_GRID, lw=0.5, alpha=0.20, zorder=Z_GRID)
    ax.set_axisbelow(True)


def legend(ax, **kw):
    """统一图例：无边框、短名称、必要时在轴外顶部。"""
    p = dict(frameon=False, fontsize=FS_LEG, labelcolor=C_TEXT, handlelength=2.2,
             columnspacing=1.2, handletextpad=0.6, borderaxespad=0.3)
    p.update(kw)
    return ax.legend(**p)


def panel_tag(ax, text: str, prefer=("tl", "tr", "bl", "br"), pad=0.012):
    """把子图标签放在数据最空的角落，避免压住曲线/柱子。"""
    cand = {"tl": (0.012, 0.965, "left", "top"), "tr": (0.988, 0.965, "right", "top"),
            "bl": (0.012, 0.035, "left", "bottom"), "br": (0.988, 0.035, "right", "bottom")}
    order = list(prefer) + [k for k in cand if k not in prefer]

    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    dx = (xlim[1] - xlim[0]) or 1.0
    dy = (ylim[1] - ylim[0]) or 1.0

    def occ_of(fx0, fx1, fy0, fy1) -> int:
        x0, x1 = xlim[0] + fx0 * dx, xlim[0] + fx1 * dx
        y0, y1 = ylim[0] + fy0 * dy, ylim[0] + fy1 * dy
        occ = 0
        for ln in ax.lines:
            xd = np.asarray(ln.get_xdata(), float)
            yd = np.asarray(ln.get_ydata(), float)
            if xd.size == 0:
                continue
            m = (xd >= x0) & (xd <= x1) & (yd >= y0) & (yd <= y1)
            occ += int(m.sum())
        for pt in ax.patches:
            b = pt.get_bbox()
            if b.x1 >= x0 and b.x0 <= x1 and b.y1 >= y0 and b.y0 <= y1:
                occ += 40
        return occ

    best, best_occ = order[-1], None
    for k in order:
        _, _, ha, va = cand[k]
        fx0, fx1 = (0.0, 0.40) if ha == "left" else (0.60, 1.0)
        fy0, fy1 = (0.55, 1.0) if va == "top" else (0.0, 0.45)
        o = occ_of(fx0, fx1, fy0, fy1)
        if best_occ is None or o < best_occ:
            best, best_occ = k, o
    x, y, ha, va = cand[best]
    ax.text(x, y, text, transform=ax.transAxes, ha=ha, va=va,
            fontsize=FS_PANEL, color=C_TEXT, zorder=Z_NOTE)


def note(ax, x: float, y: float, text: str, ha="left", va="bottom", **kw):
    """关键标注：无框文字（规范第十二节优先顺序第 1 档）。"""
    kw.setdefault("color", C_TEXT)
    kw.setdefault("fontsize", FS_NOTE)
    ax.text(x, y, text, ha=ha, va=va, zorder=Z_NOTE, **kw)


def hour_ticks(ax, maximum: float = 24.0) -> None:
    """24 小时时间轴统一刻度：0/4/8/12/16/20/24。"""
    ax.set_xticks([0, 4, 8, 12, 16, 20, 24])
    ax.set_xlim(0, maximum)


def save(fig, stem: str) -> None:
    """三份同源输出：SVG（可编辑）+ PDF（矢量）+ PNG（600 dpi）。

    保存前做轴外元素自检：任何落在坐标轴外的 text 会被移除并报告，
    以免将来再次出现"标签越界把画布撑大"的问题。
    """
    fig.canvas.draw()
    removed = []
    for ax in fig.get_axes():
        bb = ax.get_window_extent()
        for t in list(ax.texts):
            try:
                tb = t.get_window_extent()
            except Exception:
                continue
            if tb.x0 < bb.x0 - 2 or tb.x1 > bb.x1 + 2 or tb.y0 < bb.y0 - 2 or tb.y1 > bb.y1 + 2:
                removed.append(t.get_text()[:20])
                t.remove()
    if removed:
        print(f"    [自检] {stem}: 移除越界文字 {removed}")
    for ext in ("svg", "pdf", "png"):
        fig.savefig(HERE / f"{stem}.{ext}", dpi=600, bbox_inches="tight",
                    pad_inches=0.02)
    plt.close(fig)
    print(f"    [输出] {stem}.svg / .pdf / .png")


def read_csv(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def f(v) -> float:
    return float(v)


def kfmt(v: float, digits: int = 0) -> str:
    return f"{v:,.{digits}f}"


# =============================================================================
# 三、数据装载 + 审计（规范第三节：绘图前必做）
# =============================================================================
def load_all() -> dict:
    d = {
        "meta": json.loads((DATA / "q3_meta.json").read_text(encoding="utf-8")),
        "daily": read_csv("q3_daily_metrics.csv"),
        "hourly": read_csv("q3_hourly_profile.csv"),
        "band": read_csv("q3_emergency_by_price_band.csv"),
        "monthly": read_csv("q3_monthly_summary.csv"),
        "targets": read_csv("q3_target_days_interval.csv"),
        "soc_hist": [f(r["soc_end_kwh"]) for r in read_csv("q3_soc_hist.csv")],
        "cd_hist": [(r["kind"], f(r["kwh_per_interval"]))
                    for r in read_csv("q3_charge_discharge_hist.csv")],
        "stage": read_csv("q3_stage_comparison.csv"),
        "shapley": read_csv("q3_shapley.csv"),
        "cmarg": read_csv("q3_conditional_marginal.csv"),
        "lam": read_csv("q3_lambda_sensitivity.csv"),
        "lam_range": {r["item"]: r["value"] for r in read_csv("q3_lambda_range.csv")},
        "solver": read_csv("q3_solver_sensitivity.csv"),
        "solv_deg": {r["item"]: r["value"] for r in read_csv("q3_solver_degeneracy_summary.csv")},
        "q4": read_csv("q3_vs_q4.csv"),
    }
    return d


def audit(d: dict) -> None:
    """绘图前数据审计（规范第三节）。任一项不通过即抛错，绝不"为了好看"改数据。"""
    ok = []

    def chk(name, cond, detail=""):
        if not cond:
            raise AssertionError(f"数据审计失败：{name} {detail}")
        ok.append(name)

    daily, hourly, targets = d["daily"], d["hourly"], d["targets"]
    chk("日度行数=334", len(daily) == 334, f"实为 {len(daily)}")
    ds = [r["date"] for r in daily]
    chk("日度日期升序无重复", ds == sorted(ds) and len(set(ds)) == 334)
    chk("日度首末", ds[0] == "2025-02-01" and ds[-1] == "2025-12-31", f"{ds[0]}..{ds[-1]}")
    chk("小时行数=24", len(hourly) == 24, f"实为 {len(hourly)}")
    chk("小时升序 0..23", [int(r["hour"]) for r in hourly] == list(range(24)))
    chk("目标日 4×144", len(targets) == 576 and len({r["date"] for r in targets}) == 4)
    for dt in sorted({r["date"] for r in targets}):
        ts = [int(r["t_template"]) for r in targets if r["date"] == dt]
        chk(f"{dt} 段号 0..143", ts == list(range(144)))

    # 无缺失
    for nm, rows, keys in (
        ("daily", daily, ("total_cost_yuan", "emergency_kwh", "curtail_kwh", "adjust_up_kwh",
                          "adjust_down_kwh", "plan_total_kwh", "final_contract_total_kwh")),
        ("hourly", hourly, ("price_yuan_per_kwh", "net_load_kwh", "emergency_kwh", "curtail_kwh")),
        ("monthly", d["monthly"], ("plan_cost_yuan", "adjust_cost_yuan", "emergency_cost_yuan",
                                   "total_cost_yuan", "curtail_kwh")),
    ):
        for r in rows:
            for k in keys:
                v = r[k]
                chk(f"{nm}.{k} 非空且可解析", v not in (None, "") and np.isfinite(f(v)), str(v))

    # 合计一致（与 meta.totals 对齐）
    # 容差 1e-6：CSV 与 meta 由不同的求和顺序累加 334 天，浮点结合律差异量级 ~1e-9
    TOL = 1e-6
    tot_meta = d["meta"]["totals"]["total_cost_yuan"]
    tot_daily = sum(f(r["total_cost_yuan"]) for r in daily)
    chk("日度总费用之和 = meta.totals", abs(tot_daily - tot_meta) < TOL,
        f"{tot_daily!r} vs {tot_meta!r} 差 {tot_daily - tot_meta:.3e}")
    for r in daily:
        s = (f(r["plan_cost_yuan_natural"]) + f(r["adjust_cost_yuan_natural"])
             + f(r["emergency_cost_yuan"]))
        chk(f"{r['date']} 三项费用之和=总费用", abs(s - f(r["total_cost_yuan"])) < TOL,
            f"{s!r} vs {r['total_cost_yuan']!r}")
    checks = [("plan_cost_yuan", "plan_cost_yuan_natural"),
              ("adjust_cost_yuan", "adjust_cost_yuan_natural"),
              ("emergency_cost_yuan", "emergency_cost_yuan"),
              ("emergency_kwh", "emergency_kwh"), ("curtail_kwh", "curtail_kwh"),
              ("adjust_up_kwh", "adjust_up_kwh"), ("adjust_down_kwh", "adjust_down_kwh")]
    for mk, col in checks:
        sd = sum(f(r[col]) for r in daily)
        chk(f"日度之和 = meta.{mk}", abs(sd - d["meta"]["totals"][mk]) < TOL,
            f"差 {sd - d['meta']['totals'][mk]:.3e}")
    msum = sum(f(r["total_cost_yuan"]) for r in d["monthly"])
    chk("月度合计 = 全期合计", abs(msum - tot_meta) < TOL, f"差 {msum - tot_meta:.3e}")

    # 单位与量级
    chk("电价范围合理", all(0.3 < f(r["price_yuan_per_kwh"]) < 1.5 for r in hourly))
    emg_share_cost = (d["meta"]["totals"]["emergency_cost_yuan"] / tot_meta * 100)
    chk("紧急购电费占总费用 1.6331%", abs(emg_share_cost - 1.6331) < 0.01, f"{emg_share_cost:.4f}%")
    emg_kwh = d["meta"]["totals"]["emergency_kwh"]
    plan_kwh = sum(f(r["plan_total_kwh"]) for r in daily)
    emg_share_kwh = emg_kwh / (plan_kwh + emg_kwh) * 100
    chk("紧急购电量占计划量 0.1918%", abs(emg_share_kwh - 0.1918) < 0.001, f"{emg_share_kwh:.4f}%")
    soc = np.array(d["soc_hist"])
    chk("SOC 全部在 [1200,10800]", soc.min() >= 1200 - 1e-6 and soc.max() <= 10800 + 1e-6,
        f"[{soc.min():.2f},{soc.max():.2f}]")
    chk("SOC 样本数 = 48096", soc.size == 48096, str(soc.size))
    chk("阶段组合 8 组", len(d["stage"]) == 8)
    chk("Shapley 三者之和 = 全启用节省",
        abs(sum(f(r["shapley_saving_yuan"]) for r in d["shapley"])
            - d["meta"]["stage_comparison"]["saving_vs_0_only_yuan"]) < 1e-6)

    # 时间轴：自然日 0–24 无重复端点（不产生 24:00 异常竖线）
    for dt in sorted({r["date"] for r in targets}):
        row = [r for r in targets if r["date"] == dt]
        t0 = [r["time_start"] for r in row if int(r["t_template"]) == 0][0]
        chk(f"{dt} 首段为 0:10", t0 == "0:10", t0)
    chk("小时轴仅 0..23（不含 24）", max(int(r["hour"]) for r in hourly) == 23)

    print(f"    数据审计通过：{len(ok)} 项断言")


# =============================================================================
# 四、各图
# =============================================================================
def fig3_1a(d) -> None:
    hourly = sorted(d["hourly"], key=lambda r: int(r["hour"]))
    h = np.array([int(r["hour"]) for r in hourly])
    price = np.array([f(r["price_yuan_per_kwh"]) for r in hourly])
    net = np.array([f(r["net_load_kw"]) / 1e3 for r in hourly])   # 转 MW，避免 1e6 计数

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.1, 4.7), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1, 1.25], hspace=0.18))
    style(a1); style(a2)

    a1.step(h, price, where="mid", color=C_MAIN, lw=1.4, zorder=Z_DATA)
    ipk = int(np.argmax(price))
    a1.plot([h[ipk]], [price[ipk]], marker="o", ms=3.6, color=C_ACCENT, zorder=Z_DATA + 1)
    a1.annotate("峰价", xy=(h[ipk], price[ipk]), xytext=(h[ipk] - 3.4, price[ipk] - 0.13),
                fontsize=FS_NOTE, color=C_ACCENT,
                arrowprops=dict(arrowstyle="-", lw=0.6, color=C_ACCENT))
    a1.set_ylabel(U_PRICE, fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(0.30, 1.50)
    panel_tag(a1, "(a) 电价", prefer=("tl", "tr", "bl"))

    a2.plot(h, net, color=C_ACT, lw=1.4, zorder=Z_DATA, label="净负荷")
    a2.fill_between(h, net, 0, where=(net < 0), interpolate=True,
                    color=C_STATE, alpha=0.12, zorder=Z_GRID + 1)
    a2.axhline(0, color=C_SPINE, lw=0.7, zorder=Z_BASE)
    neg = np.where(net < 0)[0]
    if neg.size:
        note(a2, h[neg].mean(), net[neg].min() * 0.55, "光伏富余", ha="center", va="top")
    a2.set_ylabel("净负荷 / MW", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    hour_ticks(a2)
    panel_tag(a2, "(b) 净负荷", prefer=("tl", "tr", "br"))
    save(fig, "fig3_1a_system_profile")


def fig3_1b(d) -> None:
    issues = ["0:00", "6:00", "12:00", "18:00"]
    combo = [355.0, 284.0, 188.0, np.nan]      # 18:00 附件未给标定值
    single = [543.0, np.nan, np.nan, np.nan]   # 仅 0:00 有成对数字
    xx = np.arange(len(issues))
    w = 0.34

    fig, ax = plt.subplots(figsize=(7.1, 3.5))
    style(ax)
    b1 = ax.bar(xx - w / 2, [0 if np.isnan(v) else v for v in single], w,
                color=C_GREY_L, edgecolor=C_GREY, lw=0.6, label="仅附件3 单源", zorder=Z_DATA)
    b2 = ax.bar(xx + w / 2, [0 if np.isnan(v) else v for v in combo], w,
                color=C_MAIN, edgecolor=C_MAIN, lw=0.6, label="双源组合", zorder=Z_DATA)
    for xi, v in zip(xx, combo):
        if not np.isnan(v):
            ax.text(xi + w / 2, v + 8, f"{v:.0f}", ha="center", va="bottom",
                    fontsize=FS_NOTE, color=C_TEXT, zorder=Z_NOTE)
    ax.text(-w / 2, 543 + 8, "543", ha="center", va="bottom", fontsize=FS_NOTE, color=C_TEXT)
    ax.annotate("", xy=(w / 2, 355), xytext=(-w / 2, 543),
                arrowprops=dict(arrowstyle="->", lw=0.8, color=C_ACCENT,
                                connectionstyle="arc3,rad=0.25"))
    note(ax, 0.0, 430, "−35%", ha="center", va="bottom", color=C_ACCENT)
    ax.set_xticks(xx); ax.set_xticklabels(issues)
    ax.set_xlabel("预报发布时刻", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("白天 RMSE / kW", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylim(0, 620)
    legend(ax, loc="upper right")
    note(ax, 3.0, 60, "18:00 无标定值", ha="center", va="bottom", color=C_GREY)
    save(fig, "fig3_1b_forecast_accuracy")


def fig3_2a(d) -> None:
    daily = d["daily"]
    n = len(daily)
    up = np.array([f(r["adjust_up_kwh"]) for r in daily])
    dn = -np.array([f(r["adjust_down_kwh"]) for r in daily])
    xx = np.arange(n)

    fig, ax = plt.subplots(figsize=(7.1, 3.6))
    style(ax)
    ax.bar(xx, up, width=1.0, color=C_MAIN, lw=0, label="上调", zorder=Z_DATA)
    ax.bar(xx, dn, width=1.0, color=C_GREY, lw=0, label="下调", zorder=Z_DATA)
    ax.axhline(0, color=C_SPINE, lw=0.7, zorder=Z_BASE)
    ax.set_xlim(-1, n)
    ax.set_xlabel("日期（2025 年）", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("调整量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    net = up.sum() + dn.sum()
    note(ax, 4, up.max() * 1.06, f"全年净上调 {net:,.0f} kWh", va="top")
    ax.set_ylim(dn.min() * 1.30, up.max() * 1.16)
    legend(ax, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 1.005))
    save(fig, "fig3_2a_adjust_overview")


def fig3_2b(d) -> None:
    keep = ("2025-03-20", "2025-09-23")
    price = None
    fig, axes = plt.subplots(3, 1, figsize=(7.1, 5.4), sharex=True,
                             gridspec_kw=dict(height_ratios=[0.8, 1, 1], hspace=0.16))
    for ax in axes:
        style(ax)
    rows0 = [r for r in d["targets"] if r["date"] == keep[0]]
    price = np.array([f(r["price_yuan_per_kwh"]) for r in rows0])
    axes[0].step((np.arange(144) + 0.5) / 6.0, price, where="mid", color=C_MAIN, lw=1.3,
                 zorder=Z_DATA)
    axes[0].set_ylabel(U_PRICE, fontsize=FS_LABEL, color=C_TEXT)
    axes[0].set_ylim(0.30, 1.50)
    panel_tag(axes[0], "(a) 电价", prefer=("tl", "tr", "bl"))

    for ax, dt, tag in ((axes[1], keep[0], "(b) 2025-03-20"), (axes[2], keep[1], "(c) 2025-09-23")):
        rows = sorted([r for r in d["targets"] if r["date"] == dt],
                      key=lambda r: int(r["t_template"]))
        t = (np.arange(144) + 0.5) / 6.0
        plan = np.array([f(r["plan_kwh"]) for r in rows])
        fin = np.array([f(r["natural_final_kwh"]) for r in rows])
        ax.step(t, plan, where="mid", color=C_GREY, lw=1.1, ls="--", label="计划购电量",
                zorder=Z_DATA)
        ax.step(t, fin, where="mid", color=C_MAIN, lw=1.3, label="最终合约量", zorder=Z_DATA + 1)
        ax.set_ylabel(U_KWH, fontsize=FS_LABEL, color=C_TEXT)
        panel_tag(ax, tag, prefer=("tl", "tr", "bl"))
    axes[2].set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    hour_ticks(axes[2])
    legend(axes[0], loc="lower center", ncol=2, bbox_to_anchor=(0.5, 1.02))
    save(fig, "fig3_2b_plan_vs_final")


def fig3_3a(d) -> None:
    mon = sorted(d["monthly"], key=lambda r: r["month"])
    lbl = [f"{int(r['month'][5:7])}月" for r in mon]
    xx = np.arange(len(mon))
    pl = np.array([f(r["plan_cost_yuan"]) for r in mon])
    aj = np.array([f(r["adjust_cost_yuan"]) for r in mon])
    em = np.array([f(r["emergency_cost_yuan"]) for r in mon])
    cu = np.array([f(r["curtail_kwh"]) for r in mon])

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.1, 4.9), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1.5, 1], hspace=0.16))
    style(a1); style(a2)
    a1.bar(xx, pl / 1e4, 0.62, color=C_MAIN, lw=0, label="计划购电费", zorder=Z_DATA)
    a1.bar(xx, aj / 1e4, 0.62, bottom=pl / 1e4, color=C_GREY, lw=0, label="调整相关费用",
           zorder=Z_DATA)
    a1.bar(xx, em / 1e4, 0.62, bottom=(pl + aj) / 1e4, color=C_ACCENT, lw=0,
           label="紧急购电费", zorder=Z_DATA)
    tot = pl + aj + em
    k = int(np.argmax(tot))
    a1.text(xx[k], tot[k] / 1e4 * 1.012, f"{tot[k] / 1e4:.1f} 万元", ha="center", va="bottom",
            fontsize=FS_NOTE, color=C_TEXT)
    a1.set_ylabel("费用 / 万元", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(0, tot.max() / 1e4 * 1.16)
    vals = a1.get_yticks()
    a1.set_yticks(vals)
    a1.set_yticklabels([f"{v:,.0f}" for v in vals])
    legend(a1, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.035))
    panel_tag(a1, "(a) 月度费用构成", prefer=("tr", "tl", "br"))

    a2.bar(xx, cu / 1e3, 0.62, color=C_GREY_L, edgecolor=C_GREY, lw=0.6, zorder=Z_DATA)
    k2 = int(np.argmax(cu))
    a2.text(xx[k2], cu[k2] / 1e3 * 1.03, f"{cu[k2] / 1e3:.1f}", ha="center", va="bottom",
            fontsize=FS_NOTE, color=C_TEXT)
    a2.set_ylabel("弃电量 / (×10³ kWh)", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylim(0, cu.max() / 1e3 * 1.18)
    a2.set_xticks(xx); a2.set_xticklabels(lbl)
    for _ax in (a1, a2):
        _ax.set_xlim(-0.75, len(mon) - 0.05)   # 右侧留白，避免子图标签压柱
    panel_tag(a2, "(b) 弃电量", prefer=("tr", "tl", "br"))
    save(fig, "fig3_3a_monthly_cost")


def fig3_3b(d) -> None:
    hourly = sorted(d["hourly"], key=lambda r: int(r["hour"]))
    h = np.array([int(r["hour"]) for r in hourly])
    cu = np.array([f(r["curtail_kwh"]) for r in hourly])
    hot = (h >= 11) & (h <= 15)

    fig, ax = plt.subplots(figsize=(7.1, 3.5))
    style(ax)
    ax.bar(h[~hot], cu[~hot], 0.72, color=C_GREY_L, edgecolor=C_GREY, lw=0.6, zorder=Z_DATA)
    ax.bar(h[hot], cu[hot], 0.72, color=C_MAIN, edgecolor=C_MAIN, lw=0.6, zorder=Z_DATA)
    share = cu[hot].sum() / cu.sum() * 100
    note(ax, 13, cu[hot].max() * 1.04, f"11:00–15:00 占全年弃电 {share:.1f}%", ha="center")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlim(-0.7, 23.7)
    ax.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("弃电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylim(0, cu.max() * 1.16)
    save(fig, "fig3_3b_curtail_profile")


def fig3_4a(d) -> None:
    days = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
    styles = [(C_MAIN, "-", "o"), (C_MAIN_D, "--", "s"), (C_STATE, "-.", "^"), (C_ACT, ":", "D")]
    fig, ax = plt.subplots(figsize=(7.1, 3.7))
    style(ax)
    ax.axhline(10800, color=C_STATE, lw=0.8, ls=":", zorder=Z_BASE)
    ax.axhline(1200, color=C_STATE, lw=0.8, ls=":", zorder=Z_BASE)
    for dt, (c, ls, mk) in zip(days, styles):
        rows = sorted([r for r in d["targets"] if r["date"] == dt],
                      key=lambda r: int(r["t_template"]))
        t = np.array([(int(r["t_template"]) + 0.5) / 6.0 for r in rows])
        s = np.array([f(r["soc_end_kwh"]) for r in rows])
        ax.plot(t, s, color=c, lw=1.35, ls=ls, marker=mk, ms=3.0, markevery=24,
                markeredgewidth=0, label=dt, zorder=Z_DATA)
    ax.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("储电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylim(600, 11600)
    hour_ticks(ax)
    note(ax, 24, 11040, "运行上界 10800", ha="right")
    note(ax, 0, 11040, "运行下界 1200", ha="left")
    ax.set_ylim(400, 11900)
    legend(ax, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.30))
    save(fig, "fig3_4a_soc_trajectory")


def fig3_4b(d) -> None:
    soc = np.array(d["soc_hist"])
    fig, ax = plt.subplots(figsize=(7.1, 3.6))
    style(ax)
    ax.hist(soc, bins=48, range=(1200, 10800), color=C_MAIN, edgecolor="white", lw=0.3,
            zorder=Z_DATA)
    ax.axvline(10800, color=C_STATE, lw=0.9, ls=":", zorder=Z_BASE)
    ax.axvline(1200, color=C_STATE, lw=0.9, ls=":", zorder=Z_BASE)
    hi = (soc >= 10800 - 1e-6).mean() * 100
    lo = (soc <= 1200 + 1e-6).mean() * 100
    note(ax, 10500, ax.get_ylim()[1] * 0.92, f"贴上限 {hi:.2f}%", ha="right", va="top")
    note(ax, 1500, ax.get_ylim()[1] * 0.92, f"贴下限 {lo:.2f}%", ha="left", va="top")
    ax.set_xlabel("储电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("时段数", fontsize=FS_LABEL, color=C_TEXT)
    save(fig, "fig3_4b_soc_distribution")


def fig3_4c(d) -> None:
    ch = np.array([v for k, v in d["cd_hist"] if k == "charge"])
    di = np.array([v for k, v in d["cd_hist"] if k == "discharge"])
    fig, ax = plt.subplots(figsize=(7.1, 3.5))
    style(ax)
    bins = np.linspace(0, 840, 43)
    ax.hist(ch, bins=bins, color=C_MAIN, alpha=0.85, lw=0, label=f"充电（{ch.size:,} 时段）",
            zorder=Z_DATA)
    ax.hist(di, bins=bins, histtype="step", color=C_ACCENT, lw=1.5,
            label=f"放电（{di.size:,} 时段）", zorder=Z_DATA + 1)
    ax.axvline(833.3333, color=C_ACCENT, lw=0.9, ls=":", zorder=Z_BASE)
    note(ax, 826, ax.get_ylim()[1] * 0.94, "功率上限 833.3", ha="right", va="top",
         color=C_ACCENT)
    ax.set_xlabel("单时段充/放电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("时段数", fontsize=FS_LABEL, color=C_TEXT)
    legend(ax, loc="upper center")
    save(fig, "fig3_4c_charge_discharge")


def fig3_5a(d) -> None:
    hourly = sorted(d["hourly"], key=lambda r: int(r["hour"]))
    h = np.array([int(r["hour"]) for r in hourly])
    em = np.array([f(r["emergency_kwh"]) for r in hourly])
    hot = (h >= 19) & (h <= 21)
    fig, ax = plt.subplots(figsize=(7.1, 3.5))
    style(ax)
    ax.bar(h[~hot], em[~hot], 0.72, color=C_GREY_L, edgecolor=C_GREY, lw=0.6, zorder=Z_DATA)
    ax.bar(h[hot], em[hot], 0.72, color=C_ACCENT, edgecolor=C_ACCENT, lw=0.6, zorder=Z_DATA)
    share = em[hot].sum() / em.sum() * 100
    note(ax, 20, em.max() * 1.04, f"19:00–21:00 占 {share:.1f}%", ha="center", color=C_ACCENT)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlim(-0.7, 23.7)
    ax.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("紧急购电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylim(0, em.max() * 1.16)
    save(fig, "fig3_5a_emergency_profile")


def fig3_5b(d) -> None:
    band = sorted(d["band"], key=lambda r: f(r["price_low"]))
    lbl = [f"{f(r['price_low']):.2f}–{f(r['price_high']):.2f}" for r in band]
    xx = np.arange(len(band))
    kw = np.array([f(r["emergency_kwh"]) for r in band])
    cost = np.array([f(r["emergency_cost_yuan"]) for r in band])
    w = 0.36
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.1, 4.6), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1, 1], hspace=0.16))
    style(a1); style(a2)
    hi = len(band) - 1
    col_k = [C_GREY_L] * len(band); col_k[hi] = C_MAIN
    col_c = [C_GREY_L] * len(band); col_c[hi] = C_ACCENT
    a1.bar(xx, kw, w * 2, color=col_k, edgecolor=C_GREY, lw=0.6, zorder=Z_DATA)
    a2.bar(xx, cost, w * 2, color=col_c, edgecolor=C_GREY, lw=0.6, zorder=Z_DATA)
    for xi, v in zip(xx, kw):
        a1.text(xi, v + kw.max() * 0.02, f"{v:,.0f}", ha="center", va="bottom",
                fontsize=FS_NOTE, color=C_TEXT)
    for xi, v in zip(xx, cost):
        a2.text(xi, v + cost.max() * 0.02, f"{v:,.0f}", ha="center", va="bottom",
                fontsize=FS_NOTE, color=C_TEXT)
    a1.set_ylabel("紧急购电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(0, kw.max() * 1.18)
    a2.set_ylabel("紧急购电费 / 元", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylim(0, cost.max() * 1.18)
    a2.set_xticks(xx); a2.set_xticklabels(lbl)
    a2.set_xlabel("电价档 / (元/kWh)", fontsize=FS_LABEL, color=C_TEXT)
    panel_tag(a1, "(a) 电量", prefer=("tl", "tr", "bl"))
    panel_tag(a2, "(b) 费用", prefer=("tl", "tr", "bl"))
    save(fig, "fig3_5b_emergency_price_band")


def fig3_6(d) -> None:
    rows = sorted(d["stage"], key=lambda r: f(r["total_cost_yuan"]))
    lbl = [r["policy"] for r in rows]
    val = np.array([f(r["total_cost_yuan"]) for r in rows])
    yy = np.arange(len(rows))[::-1]
    base = val.max()
    best = val.min()

    fig, ax = plt.subplots(figsize=(7.1, 3.9))
    style(ax, grid_axis="x")
    cols = []
    for r in rows:
        p = r["policy"]
        cols.append(C_MAIN if p == "0+6+12+18" else (C_GREY if p == "0-only" else C_GREY_L))
    edges = [C_MAIN if r["policy"] == "0+6+12+18" else
             (C_GREY if r["policy"] == "0-only" else C_GREY_L) for r in rows]
    ax.barh(yy, val - 1.30e7, left=1.30e7, height=0.62, color=cols, edgecolor=edges, lw=0.6,
            zorder=Z_DATA)
    for y, v in zip(yy, val):
        ax.text(v + 1.6e3, y, f"{v / 1e4:.2f} 万", va="center", ha="left",
                fontsize=FS_NOTE, color=C_TEXT)
    ax.axvline(base, color=C_GREY, lw=1.0, ls="--", zorder=Z_BASE)
    note(ax, base - 2.0e3, len(rows) - 1.2, "仅 0:00 发布（基线）", ha="right", va="top")
    note(ax, 1.3055e7, 0.15, f"全启用省 {base - best:,.0f} 元（{(base - best) / base * 100:.4f}%）")
    ax.set_yticks(yy); ax.set_yticklabels(lbl)
    ax.set_xlim(1.3e7, val.max() * 1.028)
    ax.set_xlabel("交付期总费用 / 元（横轴自 13.0 百万元起）", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("预报发布组合", fontsize=FS_LABEL, color=C_TEXT)
    save(fig, "fig3_6_stage_value")


def fig3_7a(d) -> None:
    """画『相对主答案的偏差』而非绝对费用——两者仅差 28 元，绝对刻度无法同时看清三根柱。
    y 轴为有数学意义的差值（基准 0 = 主答案），不是截断坐标轴。"""
    rows = d["solver"]
    lbl = [r["label"] for r in rows]
    gap = np.array([f(r["gap_yuan"]) for r in rows])
    xx = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(7.1, 3.5))
    style(ax)
    cols = [C_MAIN, C_MAIN, C_ACCENT]
    axes_ = ax.bar(xx, gap, width=0.46, color=cols, edgecolor=cols, lw=0.6, zorder=Z_DATA)
    ax.axhline(0, color=C_SPINE, lw=0.8, zorder=Z_BASE)
    for xi, g in zip(xx, gap):
        ax.text(xi, g + 1.2, "0.00" if g == 0 else f"{g:,.2f}", ha="center", va="bottom",
                fontsize=FS_NOTE, color=C_TEXT)
    ax.set_xticks(xx); ax.set_xticklabels(lbl)
    ax.set_ylabel("相对主答案的偏差 / 元", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_xlabel("线性规划求解算法", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylim(min(gap.min() * 1.55, -6), max(gap.max() * 1.55, 6))
    note(ax, 1.15, gap.min() * 0.60, "仅内点法有差异：−28.21 元（−0.0002%）",
         ha="center", va="top", color=C_ACCENT)
    save(fig, "fig3_7a_solver_stability")


def fig3_7b(d) -> None:
    lam = sorted(d["lam"], key=lambda r: f(r["lam_over_baseline"]))
    x = np.array([f(r["lam_over_baseline"]) for r in lam])
    y = np.array([f(r["total_cost_yuan"]) for r in lam])
    fig, ax = plt.subplots(figsize=(7.1, 3.6))
    style(ax)
    yw = y / 1e4
    ax.plot(x, yw, color=C_MAIN, lw=1.4, marker="o", ms=4.2, markeredgewidth=0,
            label="交付期总费用", zorder=Z_DATA)
    ax.axhline(d["meta"]["totals"]["total_cost_yuan"] / 1e4, color=C_GREY, lw=0.9, ls="--",
               zorder=Z_BASE)
    kb = int(np.argmin(np.abs(x - 1.0)))
    ax.plot([x[kb]], [yw[kb]], marker="o", ms=7.5, mfc="none", mec=C_ACCENT, mew=1.2,
            zorder=Z_DATA + 1)
    ax.axvspan(0.75, 1.0, color=C_ACCENT, alpha=0.08, zorder=Z_GRID + 1)
    note(ax, 0.70, (y.min() + 260) / 1e4, "机制切换区间", ha="center", va="bottom",
         color=C_ACCENT)
    note(ax, 1.06, (y.min() - 200) / 1e4, "主答案 λ = 0.478", ha="left", va="top")
    ax.set_xlabel("λ 相对基准的倍数", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("交付期总费用 / 万元", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_xlim(-0.08, 3.12)
    rng = d["lam_range"]
    note(ax, 3.05, (y.max() - 60) / 1e4,
         f"0–3 倍极差 {f(rng['spread_yuan']):,.0f} 元（{f(rng['spread_pct_of_baseline']):.4f}%）",
         ha="right", va="top")
    save(fig, "fig3_7b_lambda_sensitivity")


# =============================================================================
# 五、主流程
# =============================================================================
def main() -> None:
    print(f"[字体] {FONT}")
    print("[1] 装载数据")
    d = load_all()
    print("[2] 数据审计")
    audit(d)
    print("[3] 绘图")
    for fn in (fig3_1a, fig3_1b, fig3_2a, fig3_2b, fig3_3a, fig3_3b,
               fig3_4a, fig3_4b, fig3_4c, fig3_5a, fig3_5b, fig3_6, fig3_7a, fig3_7b):
        fn(d)
    print(f"\n全部图件已输出到 {HERE}")


if __name__ == "__main__":
    main()
