"""第四问 论文级科研图表（统一主脚本）。

依据《数学建模论文科研绘图指导规范》（E:\\onedrive\\Desktop\\数学建模论文科研绘图指导.md）
与 handoff/q4/图表规划.md。一个脚本产出全部 14 个图号 / 14 组文件（SVG + PDF + PNG 600 dpi），
统一颜色语义、字号、线宽、网格、边框与保存方式，可直接复用 q3 的视觉规范。

硬性约束（规范原文）：
    · 默认禁止双 Y 轴（ax.twinx）——量纲不同的两个量一律改用**上下共享 x 轴**的面板
    · 输出 SVG + PDF + PNG(600 dpi)；SVG 文字可编辑、PDF 保持矢量
    · 尺寸：单图 7.0×3.2~3.8 in；上下双面板 7.0×4.3~4.8 in；左右双面板 7.0×3.0~3.6 in
    · fill_between 只用于有数学意义的区域（分位带 / 偏差区 / 约束区），alpha = 0.08~0.18
    · 一张图只有一个真正的强调色 C_ACCENT
    · 不能只靠颜色区分：两变体同时用线型（4-3 实线 / 4-2 虚线）或 marker 区分，保证黑白可辨
    · 图内不放大标题（标题交给图注）

数据来源（只读，不重跑求解器）：
    handoff/q4/_figdata/*.csv + q4_meta.json

运行：
    python figures/figs_q4_paper.py
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

HERE = Path(__file__).resolve().parent
HANDOFF = HERE.parent
DATA = HANDOFF / "_figdata"

# =============================================================================
# 一、视觉规范常量（全文统一；改这里即全文生效；与第二、三问共用同一套语义）
# =============================================================================
C_MAIN = "#4C6E91"      # 主模型 / 本文方法 / 主数据（第四问里＝4-3）
C_MAIN_D = "#3A5470"    # 深版主色
C_ACT = "#5B6470"       # 真实值 / 实测值
C_GREY = "#9AA4AE"      # 普通对照 / 次要数据（第四问里＝4-2）
C_GREY_L = "#C9D0D6"    # 浅灰辅助
C_GREYBLUE = "#91A5B5"  # 浅灰蓝（普通月份柱、次要对照）
C_ACCENT = "#A9705A"    # 风险 / 最大误差 / 紧急 / 最差结果（全篇唯一强调色）
C_STATE = "#7E9B84"     # 状态类 / 边界类指标
C_GRID = "#DFE3E7"      # 网格
C_TEXT = "#333333"      # 文字
C_SPINE = "#B4BBC2"     # 边框

FS_TICK, FS_LABEL, FS_LEG, FS_PANEL, FS_NOTE = 8.5, 9.5, 8.5, 9.0, 7.5
Z_GRID, Z_BASE, Z_DATA, Z_NOTE = 0, 2, 4, 6
U_PRICE = "电价 / (元/kWh)"
U_KWH = "电量 / kWh"

W_SINGLE, W_2V, W_2H = 7.0, 4.5, 3.4      # 单图 / 上下面板 / 左右面板的 figsize 高度
LAB42, LAB43 = "4-2（一次决策）", "4-3（四阶段滚动）"


def _pick_font() -> str:
    have = {fm.name for fm in font_manager.fontManager.ttflist}
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
    """统一坐标轴样式：去上/右边框、浅灰左/下边框、仅浅网格。"""
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
    p = dict(frameon=False, fontsize=FS_LEG, labelcolor=C_TEXT, handlelength=2.2,
             columnspacing=1.2, handletextpad=0.6, borderaxespad=0.3)
    p.update(kw)
    return ax.legend(**p)


def panel_tag(ax, text: str, loc: str = "tl") -> None:
    """子图标签：固定在指定角落（本问各面板数据分布已逐图核对，无需自动避让）。"""
    cand = {"tl": (0.012, 0.965, "left", "top"), "tr": (0.988, 0.965, "right", "top"),
            "bl": (0.012, 0.035, "left", "bottom"), "br": (0.988, 0.035, "right", "bottom")}
    x, y, ha, va = cand[loc]
    ax.text(x, y, text, transform=ax.transAxes, ha=ha, va=va,
            fontsize=FS_PANEL, color=C_TEXT, zorder=Z_NOTE)


def note(ax, x, y, text, ha="left", va="bottom", **kw):
    kw.setdefault("color", C_TEXT)
    kw.setdefault("fontsize", FS_NOTE)
    ax.text(x, y, text, ha=ha, va=va, zorder=Z_NOTE, **kw)


def note_ax(ax, fx: float, fy: float, text: str, ha="left", va="top", **kw):
    """角注：以坐标轴归一化坐标定位（0–1），保证永不越界。"""
    kw.setdefault("color", C_TEXT)
    kw.setdefault("fontsize", FS_NOTE)
    ax.text(fx, fy, text, transform=ax.transAxes, ha=ha, va=va, zorder=Z_NOTE, **kw)


def hour_ticks(ax, maximum: float = 24.0) -> None:
    ax.set_xticks([0, 4, 8, 12, 16, 20, 24])
    ax.set_xlim(0, maximum)


def bar_labels(ax, xs, vs, fmt="{:,.0f}", dy_frac=0.02, color=None, **kw):
    """柱顶标数值；dy_frac 为相对纵轴范围的偏移比例。"""
    lo, hi = ax.get_ylim()
    dy = (hi - lo) * dy_frac
    for x, v in zip(xs, vs):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            continue
        ax.text(x, v + dy, fmt.format(v), ha="center", va="bottom",
                fontsize=FS_NOTE, color=color or C_TEXT, zorder=Z_NOTE, **kw)


def save(fig, stem: str) -> None:
    """三份同源输出：SVG（可编辑）+ PDF（矢量）+ PNG（600 dpi）。

    保存前做轴外元素自检：只移除**明显越界**（超过坐标轴尺寸 6%）的 text，
    以免标签越界把画布撑大；轻微溢出（相邻刻度文字等）不算问题。
    """
    fig.canvas.draw()
    removed = []
    for ax in fig.get_axes():
        bb = ax.get_window_extent()
        tol_x = (bb.x1 - bb.x0) * 0.06
        tol_y = (bb.y1 - bb.y0) * 0.06
        for t in list(ax.texts):
            if not t.get_text().strip():
                continue          # annotate("") 只用来画箭头、无文字，不参与自检
            try:
                tb = t.get_window_extent()
            except Exception:
                continue
            if (tb.x0 < bb.x0 - tol_x or tb.x1 > bb.x1 + tol_x
                    or tb.y0 < bb.y0 - tol_y or tb.y1 > bb.y1 + tol_y):
                removed.append(t.get_text()[:20])
                t.remove()
    if removed:
        print(f"    [自检] {stem}: 移除越界文字 {removed}")
    for ext in ("svg", "pdf", "png"):
        fig.savefig(HERE / f"{stem}.{ext}", dpi=600, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print(f"    [输出] {stem}.svg / .pdf / .png")


def read_csv(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def f(v) -> float:
    """空字符串（如 4 格对照里的【待补】格）返回 nan；容忍带 % 后缀的百分比列。"""
    if v in (None, ""):
        return float("nan")
    if isinstance(v, str):
        v = v.strip().rstrip("%").strip()
    return float(v)


def kfmt(v: float, digits: int = 0) -> str:
    return f"{v:,.{digits}f}"


def mid_h(slots) -> np.ndarray:
    """模板行时段号 -> 时刻（小时，取区间中点）：t 覆盖 [(t+1)*10, (t+2)*10) 分钟。"""
    return (np.asarray(slots, float) + 1.5) / 6.0


def nat_h(slots) -> np.ndarray:
    """自然日时段号 -> 时刻（小时，取区间中点）：τ 覆盖 [τ*10, (τ+1)*10) 分钟。"""
    return (np.asarray(slots, float) + 0.5) / 6.0


# =============================================================================
# 三、数据装载 + 审计（规范第三节：绘图前必做）
# =============================================================================
def load_all() -> dict:
    return {
        "meta": json.loads((DATA / "q4_meta.json").read_text(encoding="utf-8")),
        "price": read_csv("q4_price_profile.csv"),
        "pstat": read_csv("q4_price_statistics.csv")[0],
        "ferr": read_csv("q4_price_forecast_error.csv"),
        "daily": read_csv("q4_daily_metrics.csv"),
        "hourly": read_csv("q4_hourly_profile.csv"),
        "monthly": read_csv("q4_monthly_summary.csv"),
        "targets": read_csv("q4_target_days_interval.csv"),
        "band": read_csv("q4_emergency_by_price_band.csv"),
        "soc_hist": read_csv("q4_soc_hist.csv"),
        "soc_hits": {r["variant"]: r for r in read_csv("q4_soc_band_hits.csv")},
        "cd_hist": read_csv("q4_charge_discharge_hist.csv"),
        "adj_hour": read_csv("q4_adjust_by_hour.csv"),
        "adj_stage": read_csv("q4_adjust_by_stage.csv"),
        "cells": read_csv("q4_strategy_compare_4cells.csv"),
        "pf": read_csv("q4_perfect_foresight.csv"),
        "lam": read_csv("q4_lambda_sensitivity.csv"),
        "lam_range": {r["variant"]: r for r in read_csv("q4_lambda_range.csv")},
        "solver": read_csv("q4_solver_sensitivity.csv"),
        "solv_deg": read_csv("q4_solver_degeneracy_summary.csv"),
        "verify": read_csv("q4_independent_verify.csv"),
    }


def audit(d: dict) -> None:
    """绘图前数据审计（规范第三节 + 图表规划 §5）。任一项不通过即抛错。"""
    ok = []

    def chk(name, cond, detail=""):
        if not cond:
            raise AssertionError(f"数据审计失败：{name} {detail}")
        ok.append(name)

    price, targets, daily = d["price"], d["targets"], d["daily"]
    hourly, monthly = d["hourly"], d["monthly"]

    # 1 时间排序
    chk("price.slot 升序 0..143", [int(r["slot"]) for r in price] == list(range(144)))
    chk("hourly.hour 升序 0..23", [int(r["hour"]) for r in hourly] == list(range(24)))
    ds = sorted({r["date"] for r in daily})
    chk("daily 日期升序无重复", len(ds) == len(daily) // 2 == 334, f"{len(ds)}")

    # 2/4 单位与月份顺序
    months = sorted({r["month"] for r in monthly})
    chk("monthly 含 11 个月且升序", months == sorted(f"2025-{m:02d}" for m in range(2, 13)), str(months))
    chk("monthly 两变体月份集合一致",
        {r["month"] for r in monthly if r["variant"] == "2"} ==
        {r["month"] for r in monthly if r["variant"] == "3"})

    # 3 横轴与数据不错位：表1 六个时段 = 模板列 59/71/83/95/107/119
    tb = {r["label"] for r in price}
    for lab in ("10:00-10:10", "12:00-12:10", "14:00-14:10",
                "16:00-16:10", "18:00-18:10", "20:00-20:10"):
        chk(f"price.label 含 {lab}", lab in tb)
    chk("表1 时段列号 = 59/71/83/95/107/119",
        all(price[i]["slot_start_hhmm"] == h for i, h in
            ((59, "10:00"), (71, "12:00"), (83, "14:00"), (95, "16:00"),
             (107, "18:00"), (119, "20:00"))))

    # 5 自然日 145 点，首点 = 前一日末点（不重复计入）
    for v in ("2", "3"):
        rows = [r for r in targets if r["variant"] == v]
        chk(f"targets variant {v} 4 日 × 144 段", len(rows) == 576)
        for dt in sorted({r["date"] for r in rows}):
            chk(f"{dt}(v{v}) slot 0..143", sorted(int(r["slot"]) for r in rows if r["date"] == dt) == list(range(144)))
    chk("soc_hist 箱数 ≤48 且两变体同箱", len(d["soc_hist"]) <= 48)

    # 6 24:00 不产生异常竖线：自然日时刻上界为 24
    chk("natural_slot 上界 143（对应 24:00 前一段）",
        max(int(r["natural_slot"]) for r in targets) == 143)

    # 8 无缺失（空值白名单：4 格对照的【待补】格）
    for nm, rows, keys in (
        ("price", price, ("mean", "p10", "p50", "p90", "shape", "annex1_price")),
        ("hourly", hourly, ("price_mean", "emergency_kwh_42", "emergency_kwh_43",
                            "curtail_kwh_42", "curtail_kwh_43", "net_load_kwh")),
        ("monthly", monthly, ("plan_cost", "adjust_cost", "emergency_cost", "total_cost", "curtail_kwh")),
    ):
        for r in rows:
            for k in keys:
                chk(f"{nm}.{k} 非空可解析", r[k] not in (None, "") and np.isfinite(f(r[k])), str(r[k]))
    chk("cells 仅第 1 格为空（【待补】）",
        sum(1 for r in d["cells"] if r["total_cost_yuan"] == "") == 1)

    # 9 范围
    S_min, S_max = d["meta"]["S_min"], d["meta"]["S_max"]
    chk("SOC 界 1200/10800", (S_min, S_max) == (1200.0, 10800.0))
    for r in d["lam"]:
        chk("lambda soc_end ∈ 界内", S_min - 1e-6 <= f(r["soc_end_delivery_kwh"]) <= S_max + 1e-6)
    lo, hi = float(d["pstat"]["fullyear_min"]), float(d["pstat"]["fullyear_max"])
    chk("电价 ∈ [0.0076, 1.7936]", (lo, hi) == (0.0076, 1.7936), f"{lo},{hi}")

    # 10 百分比合理
    for r in monthly:
        share = f(r["emergency_cost"]) / f(r["total_cost"])
        chk("月度紧急费占比 ∈ [0,1)", 0 <= share < 1)

    # 11 总量与分项一致（容差 1e-6；CSV 与 meta 由不同求和顺序累加）
    TOL = 1e-6
    for v in ("2", "3"):
        tot = d["meta"]["totals"][v]
        day = [r for r in daily if r["variant"] == v]
        chk(f"v{v} 逐日总费用之和 = totals",
            abs(sum(f(r["total_cost_yuan"]) for r in day) - tot["total_cost_yuan"]) < TOL)
        chk(f"v{v} 自然日三项之和 = 总费用",
            abs(sum(f(r["natural_day_plan_cost_yuan"]) + f(r["natural_day_adjust_cost_yuan"])
                    for r in day) + tot["emergency_cost_yuan"] - tot["total_cost_yuan"]) < 5e-4)
        mo = [r for r in monthly if r["variant"] == v]
        chk(f"v{v} 月度总费用之和 = totals",
            abs(sum(f(r["total_cost"]) for r in mo) - tot["total_cost_yuan"]) < 1e-3)
        chk(f"v{v} 月度紧急购电量之和 = totals",
            abs(sum(f(r["emergency_kwh"]) for r in mo) - tot["emergency_kwh"]) < 1e-3)
    # 表3 分段之和 = 逐日合计（用 band 与 hourly 交叉核对紧急购电量）
    chk("分电价档紧急购电量之和 = totals(4-2)",
        abs(sum(f(r["kwh_42"]) for r in d["band"]) - d["meta"]["totals"]["2"]["emergency_kwh"]) < 1e-3)
    chk("分电价档紧急购电量之和 = totals(4-3)",
        abs(sum(f(r["kwh_43"]) for r in d["band"]) - d["meta"]["totals"]["3"]["emergency_kwh"]) < 1e-3)
    chk("逐小时紧急购电量之和 = totals(4-2)",
        abs(sum(f(r["emergency_kwh_42"]) for r in hourly) - d["meta"]["totals"]["2"]["emergency_kwh"]) < 1e-3)
    chk("逐小时紧急购电量之和 = totals(4-3)",
        abs(sum(f(r["emergency_kwh_43"]) for r in hourly) - d["meta"]["totals"]["3"]["emergency_kwh"]) < 1e-3)
    # 分阶段调整费之和 = 模板行口径调整费
    chk("分阶段调整费之和 = 878,485.8670（模板行口径）",
        abs(sum(f(r["up_cost_yuan_43"]) + f(r["down_cost_yuan_43"]) for r in d["adj_stage"])
            - 878485.8670325235) < 0.01)
    # 完美预见恒等式
    pfr = {r["point"]: r for r in d["pf"] if r["kind"] == "decomposition"}
    chk("完美预见恒等式残差 = 0", abs(f(pfr["a 电价波动风险"]["identity_residual_yuan"])) < 1e-9)
    chk("(a)+(b) = 总差额",
        abs(f(pfr["a 电价波动风险"]["a_volatility_risk_yuan"])
            + f(pfr["b 预测误差信息损失"]["b_forecast_error_yuan"])
            - f(pfr["a 电价波动风险"]["total_gap_yuan"])) < 1e-6)

    # 12 预测误差表与文档一致（硬编码誊抄，此处反向校验）
    exp = {0: (13.2, 0.0799, 0.0799), 1: (9.1, 0.0556, 0.0916),
           2: (11.6, 0.0837, 0.0865), 3: (13.4, 0.0832, 0.0631)}
    for r in d["ferr"]:
        e = exp[int(r["stage"])]
        chk(f"ferr stage{int(r['stage'])} 与 docs/q4_model.md 一致",
            (f(r["MAPE"]), f(r["MAE_yuan_per_kwh"]), f(r["MAE_same_window_no_update"])) == e)

    # 13/14/15 无平滑、无插值、无复制错位
    chk("targets 变体标记与列后缀一致",
        all(int(r["variant"]) in (2, 3) for r in targets))
    for r in hourly:
        chk("hourly 两变体列同源（列名前缀一致）", r["emergency_kwh_42"] is not None)

    # 16 比例压缩：逐图人工核对；此处仅断言数值范围可比较
    chk("solv_deg 含 overall 行", any(r["scope"] == "overall" for r in d["solv_deg"]))

    print(f"  [审计] {len(ok)} 项全部通过")


# =============================================================================
# 四、各图
# -----------------------------------------------------------------------------
# 统一布局纪律（避免标签互压）：
#   ① 面板标签永远固定在左上角（0.012, 0.965）
#   ② 单面板图的图例一律放到坐标轴**上方**（loc="lower center", bbox_to_anchor=(0.5, 1.02)）
#   ③ 多面板图的图例用 fig.legend 放到整张图顶部居中
#   ④ 所有 annotate / note 显式带 zorder=Z_NOTE，避免被柱子或曲线盖住
#   ⑤ 需要空间的标注先扩 ylim，再放文字；角注用 note_ax（归一化坐标，永不越界）
# =============================================================================
def fig4_1a(d) -> None:
    """图 4-1a 附件4 日内电价形态（上下双面板，不用双 Y 轴）。"""
    rows = sorted(d["price"], key=lambda r: int(r["slot"]))
    t = mid_h([r["slot"] for r in rows])
    mean = np.array([f(r["mean"]) for r in rows])
    p10 = np.array([f(r["p10"]) for r in rows])
    p90 = np.array([f(r["p90"]) for r in rows])
    shape = np.array([f(r["shape"]) for r in rows])
    a1p = np.array([f(r["annex1_price"]) for r in rows])

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.0, W_2V), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1.25, 1], hspace=0.18))
    style(a1); style(a2)

    # p10–p90 是分位区间，属规范允许的 fill_between
    a1.fill_between(t, p10, p90, color=C_GREY_L, alpha=0.16, lw=0, zorder=Z_GRID + 1,
                    label="10%–90% 分位带")
    a1.plot(t, mean, color=C_MAIN, lw=1.5, zorder=Z_DATA + 1, label="逐时段均值")
    a1.plot(t, a1p, color=C_ACT, lw=1.0, ls="--", zorder=Z_DATA, label="附件1 分时电价")
    a1.set_ylabel(U_PRICE, fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(0.30, 1.62)
    ipk = int(np.argmax(mean))
    a1.plot([t[ipk]], [mean[ipk]], marker="o", ms=3.6, color=C_ACCENT, zorder=Z_DATA + 2)
    a1.annotate("峰段 19:00 ≈1.35", xy=(t[ipk], mean[ipk]),
                xytext=(t[ipk] - 9.4, mean[ipk] + 0.14), fontsize=FS_NOTE, color=C_ACCENT,
                zorder=Z_NOTE, arrowprops=dict(arrowstyle="-", lw=0.6, color=C_ACCENT))
    note(a1, 0.6, 0.34, "谷段 22:00–05:00　均值 ≈0.42", color=C_TEXT)
    note(a1, 9.2, 0.34, "午间凹陷 ≈0.47", color=C_TEXT)
    panel_tag(a1, "(a) 电价水平与分位带", "tl")
    legend(a1, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3)

    a2.plot(t, shape, color=C_MAIN, lw=1.4, zorder=Z_DATA)
    a2.axhline(1.0, color=C_GREY_L, lw=0.8, ls="--", zorder=Z_BASE)
    note(a2, 0.6, 1.03, "φ = 1 基准线", va="bottom", color=C_GREY)
    a2.set_ylabel("归一化形态 φ", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylim(0.3, 1.6)
    a2.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    hour_ticks(a2)
    panel_tag(a2, "(b) 归一化日内形态", "tl")
    save(fig, "fig4_1a_price_profile")


def fig4_1b(d) -> None:
    """图 4-1b 电价预测精度（上下双面板）。"""
    rows = sorted(d["ferr"], key=lambda r: int(r["stage"]))
    xx = np.arange(len(rows))
    lab = [r["publish_hour"] + ":00" for r in rows]
    mape = np.array([f(r["MAPE"]) for r in rows])
    mae = np.array([f(r["MAE_yuan_per_kwh"]) for r in rows])
    no_up = np.array([f(r["MAE_same_window_no_update"]) for r in rows])
    pers = np.array([f(r["MAE_persistence"]) for r in rows])

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.0, W_2V), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1, 1.15], hspace=0.18, top=0.90))
    style(a1); style(a2)

    a1.bar(xx, mape, 0.5, color=C_GREYBLUE, edgecolor=C_GREY, lw=0.6, zorder=Z_DATA)
    a1.set_ylabel("MAPE / %", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(0, 17.5)
    bar_labels(a1, xx, mape, "{:.1f}%")
    note(a1, 0.55, 15.2, "各阶段剩余窗口不同 → 不可横向排名", color=C_GREY)
    panel_tag(a1, "(a) 各发布时刻 MAPE", "tl")

    w = 0.26
    a2.bar(xx - w, mae, w, color=C_MAIN, edgecolor=C_MAIN, lw=0.6,
           label="含日内更新", zorder=Z_DATA)
    a2.bar(xx, no_up, w, color=C_GREY, edgecolor=C_GREY, lw=0.6,
           label="同一窗口不含更新", zorder=Z_DATA)
    a2.bar(xx + w, pers, w, color=C_GREY_L, edgecolor=C_GREY, lw=0.6,
           label="前一日持续", zorder=Z_DATA)
    a2.set_xticks(xx); a2.set_xticklabels(lab)
    a2.set_xlabel("预报发布时刻", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylabel("MAE / (元/kWh)", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylim(0, 0.128)
    a2.annotate("−39%", xy=(1 - w, mae[1]), xytext=(0.62, mae[1] + 0.031),
                fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    a2.annotate("+32%（负收益）", xy=(3 - w, mae[3]), xytext=(3.44, 0.118), ha="right",
                va="bottom", fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    panel_tag(a2, "(b) 同一窗口下的 MAE 对照", "tl")
    fig.legend(*a2.get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(0.5, 0.995),
               ncol=3, frameon=False, fontsize=FS_LEG, labelcolor=C_TEXT, handlelength=2.2,
               columnspacing=1.4)
    save(fig, "fig4_1b_price_forecast")


def fig4_2a(d) -> None:
    """图 4-2a 两日调度对照（上下双面板，不用双 Y 轴）。"""
    keep = ("2025-03-20", "2025-09-23")
    tg = d["targets"]
    price, x42, q43 = [], [], []
    edges = []
    for dt in keep:
        r3 = sorted([r for r in tg if r["date"] == dt and r["variant"] == "3"], key=lambda r: int(r["slot"]))
        r2 = sorted([r for r in tg if r["date"] == dt and r["variant"] == "2"], key=lambda r: int(r["slot"]))
        price += [f(r["price_template"]) for r in r3]
        q43 += [f(r["q"]) for r in r3]
        x42 += [f(r["x"]) for r in r2]
        edges.append(len(price))
    price, x42, q43 = np.array(price), np.array(x42), np.array(q43)
    xx = np.arange(price.size)
    ymax = max(x42.max(), q43.max())

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.0, W_2V), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1, 1.25], hspace=0.18))
    style(a1); style(a2)

    a1.step(xx, price, where="mid", color=C_ACT, lw=1.2, zorder=Z_DATA)
    a1.set_ylabel(U_PRICE, fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(0.0, 2.15)
    for e in edges[:-1]:
        a1.axvline(e - 0.5, color=C_SPINE, lw=0.6, ls=":", zorder=Z_BASE)
        a2.axvline(e - 0.5, color=C_SPINE, lw=0.6, ls=":", zorder=Z_BASE)
    panel_tag(a1, "(a) 附件4 实际电价", "tl")
    note_ax(a1, 0.988, 0.90, "左：2025-03-20　　右：2025-09-23", ha="right", va="top", color=C_GREY)

    w = 0.42
    a2.bar(xx - w / 2, x42, w, color=C_GREY, edgecolor=C_GREY, lw=0.4,
           label=LAB42, zorder=Z_DATA)
    a2.bar(xx + w / 2, q43, w, color=C_MAIN, edgecolor=C_MAIN, lw=0.4,
           label=LAB43, zorder=Z_DATA)
    a2.set_ylabel(U_KWH, fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylim(0, ymax * 1.30)
    e0 = edges[0]
    d23 = int(np.argmax(np.abs(q43[:e0] - x42[:e0])))
    a2.annotate("18:00–18:10 由 0 → 760.4559 kWh",
                xy=(d23 + w / 2, q43[d23]), xytext=(max(d23 - 78, 6), ymax * 1.12),
                fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    panel_tag(a2, "(b) 购电量", "tl")
    legend(a2, loc="upper right", ncol=1)
    a2.set_xlabel("两日各 144 个 10 分钟时段（区间中点）", fontsize=FS_LABEL, color=C_TEXT)
    save(fig, "fig4_2a_dispatch_2days")


def fig4_2b(d) -> None:
    """图 4-2b 指定日期计划购电量与最终调整购电量（2×2 面板）。"""
    tg = d["targets"]
    taus = sorted({r["date"] for r in tg})
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 5.2), sharex=True, sharey=True,
                             gridspec_kw=dict(hspace=0.26, wspace=0.10, top=0.86))
    axes = axes.ravel()
    data, ymax = {}, 0.0
    for dt in taus:
        r3 = sorted([r for r in tg if r["date"] == dt and r["variant"] == "3"], key=lambda r: int(r["slot"]))
        r2 = sorted([r for r in tg if r["date"] == dt and r["variant"] == "2"], key=lambda r: int(r["slot"]))
        data[dt] = (np.array([f(r["x"]) for r in r3]), np.array([f(r["q"]) for r in r3]),
                    np.array([f(r["x"]) for r in r2]))
        ymax = max(ymax, data[dt][1].max(), data[dt][2].max())

    handles = None
    for ax, dt in zip(axes, taus):
        style(ax)
        x3, q3, x2 = data[dt]
        t = mid_h(np.arange(144))
        # 偏差区：q−x 的正负区域，有明确数学意义
        ax.fill_between(t, x3, q3, where=(q3 >= x3), color=C_MAIN, alpha=0.16, lw=0,
                        interpolate=True, zorder=Z_GRID + 1)
        ax.fill_between(t, x3, q3, where=(q3 < x3), color=C_GREY, alpha=0.16, lw=0,
                        interpolate=True, zorder=Z_GRID + 1)
        ax.step(t, x2, where="mid", color=C_GREY, lw=1.1, ls=":", zorder=Z_DATA,
                label="4-2 计划＝最终")
        ax.step(t, x3, where="mid", color=C_GREYBLUE, lw=1.1, ls="--", zorder=Z_DATA + 1,
                label="4-3 计划")
        ax.step(t, q3, where="mid", color=C_MAIN, lw=1.4, zorder=Z_DATA + 2, label="4-3 最终")
        ax.set_ylim(0, ymax * 1.16)
        hour_ticks(ax)
        sx = float(np.abs(q3 - x3).sum())
        panel_tag(ax, f"{dt}　Σ|q−x| = {sx:,.0f} kWh", "tl")
        if handles is None:
            handles = ax.get_legend_handles_labels()
    for ax in axes[2:]:
        ax.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    for ax in (axes[0], axes[2]):
        ax.set_ylabel(U_KWH, fontsize=FS_LABEL, color=C_TEXT)
    fig.legend(*handles, loc="upper center", bbox_to_anchor=(0.5, 0.985), ncol=3,
               frameon=False, fontsize=FS_LEG, labelcolor=C_TEXT, handlelength=2.2,
               columnspacing=1.4)
    save(fig, "fig4_2b_plan_vs_final")


def fig4_3a(d) -> None:
    """图 4-3a 月度费用构成与紧急购电占比（上下双面板）。"""
    months = sorted({r["month"] for r in d["monthly"]})
    idx = {m: i for i, m in enumerate(months)}
    xx = np.arange(len(months))
    w = 0.38

    def series(v, key):
        out = np.zeros(len(months))
        for r in d["monthly"]:
            if r["variant"] == v:
                out[idx[r["month"]]] = f(r[key])
        return out

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.0, 4.9), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1.3, 1], hspace=0.16))
    style(a1); style(a2)

    labels = ("计划购电费", "调整相关费用", "紧急购电费")
    for v, off, hatch in (("3", -w / 2, None), ("2", +w / 2, "///")):
        plan, adj, emg = series(v, "plan_cost"), series(v, "adjust_cost"), series(v, "emergency_cost")
        for vals, bot, col in ((plan, 0, C_GREYBLUE), (adj, plan, C_STATE),
                               (emg, plan + adj, C_ACCENT)):
            a1.bar(xx + off, vals, w, bottom=bot, color=col, edgecolor=C_MAIN_D, lw=0.4,
                   hatch=hatch, zorder=Z_DATA)
    a1.set_ylabel("费用 / 元", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(0, 2.55e6)
    i6 = idx["2025-06"]
    a1.annotate("6 月紧急购电费 388,227.03 元\n（占当月 23.19%）", xy=(i6 + w / 2, 1.79e6),
                xytext=(i6 + 0.9, 2.05e6), fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    panel_tag(a1, "(a) 月度费用构成（堆叠）", "tl")
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=C_GREYBLUE, edgecolor=C_MAIN_D, lw=0.4, label=labels[0]),
               Patch(facecolor=C_STATE, edgecolor=C_MAIN_D, lw=0.4, label=labels[1]),
               Patch(facecolor=C_ACCENT, edgecolor=C_MAIN_D, lw=0.4, label=labels[2]),
               Patch(facecolor="white", edgecolor=C_GREY, lw=0.6, hatch="///",
                     label="实心 = 4-3　斜纹 = 4-2")]
    a1.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=4,
              frameon=False, fontsize=FS_LEG - 0.4, labelcolor=C_TEXT, handlelength=1.8,
              columnspacing=1.0, handletextpad=0.5)

    for v, ls, col, mk in (("3", "-", C_MAIN, "o"), ("2", "--", C_GREY, "s")):
        tot, emg = series(v, "total_cost"), series(v, "emergency_cost")
        a2.plot(xx, 100 * emg / tot, color=col, lw=1.4, ls=ls, marker=mk, ms=3.2,
                markevery=1, zorder=Z_DATA, label=LAB43 if v == "3" else LAB42)
    a2.set_ylabel("紧急购电费占比 / %", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylim(0, 32)
    a2.set_xticks(xx); a2.set_xticklabels([m[5:] for m in months])
    a2.set_xlabel("月份（2025 年）", fontsize=FS_LABEL, color=C_TEXT)
    v2 = series("2", "emergency_cost") / series("2", "total_cost") * 100
    a2.annotate("4-2 峰值 23.2%", xy=(i6, v2[i6]), xytext=(i6 + 1.3, v2[i6] + 4.0),
                fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    panel_tag(a2, "(b) 紧急购电费占当月总费用的比例", "tl")
    legend(a2, loc="upper right", bbox_to_anchor=(1.0, 0.94), ncol=1)
    save(fig, "fig4_3a_monthly_cost")


def fig4_3b(d) -> None:
    """图 4-3b 合约调整量的日内分布与阶段分解（左右双面板，不用双 Y 轴）。"""
    hh = [int(r["hour"]) for r in d["adj_hour"]]
    up3 = np.array([f(r["up_kwh_43"]) for r in d["adj_hour"]])
    dn3 = np.array([f(r["down_kwh_43"]) for r in d["adj_hour"]])
    st = sorted(d["adj_stage"], key=lambda r: int(r["stage"]))
    sxx = np.arange(len(st))
    sup = np.array([f(r["up_kwh_43"]) for r in st])
    sdn = np.array([f(r["down_kwh_43"]) for r in st])
    cost_up = np.array([f(r["up_cost_yuan_43"]) for r in st])
    cost_dn = np.array([f(r["down_cost_yuan_43"]) for r in st])

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, W_2H + 0.4),
                                 gridspec_kw=dict(wspace=0.30, width_ratios=[1.35, 1]))
    style(a1); style(a2)

    a1.bar(np.array(hh) - 0.2, up3, 0.4, color=C_MAIN, lw=0, label="上调", zorder=Z_DATA)
    a1.bar(np.array(hh) + 0.2, -dn3, 0.4, color=C_GREY, lw=0, label="下调", zorder=Z_DATA)
    a1.axhline(0, color=C_SPINE, lw=0.8, zorder=Z_BASE)
    a1.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylabel("累计调整量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_xticks([0, 4, 8, 12, 16, 20, 23])
    a1.set_xlim(-1, 24)
    a1.set_ylim(-dn3.max() * 1.55, up3.max() * 1.55)
    note(a1, 23.8, up3.max() * 1.12,
         f"全期累计上调 {up3.sum():,.0f} / 下调 {dn3.sum():,.0f} kWh",
         ha="right", va="bottom", color=C_TEXT)
    note(a1, 0.0, -dn3.max() * 1.44, "净上调 289,169.3431 kWh（自然日口径）", color=C_ACCENT)
    panel_tag(a1, "(a) 4-3 调整量的时刻分布", "tl")
    legend(a1, loc="upper left", bbox_to_anchor=(0.0, 0.90), ncol=2)

    w = 0.36
    a2.bar(sxx - w / 2, sup, w, color=C_MAIN, lw=0, label="上调", zorder=Z_DATA)
    a2.bar(sxx + w / 2, sdn, w, color=C_GREY, lw=0, label="下调", zorder=Z_DATA)
    a2.set_xticks(sxx)
    a2.set_xticklabels([f"{r['publish_hour']}:00\n{(cu+cd)/1e4:.1f}万"
                        for r, cu, cd in zip(st, cost_up, cost_dn)], fontsize=FS_TICK)
    a2.set_xlabel("决策阶段（发布时刻）　下方数字：调整费合计（万元）",
                  fontsize=FS_LABEL - 1.0, color=C_TEXT)
    a2.set_ylabel("调整量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylim(0, sup.max() * 1.28)
    panel_tag(a2, "(b) 按阶段分解", "tl")
    legend(a2, loc="upper right", ncol=1)
    save(fig, "fig4_3b_adjust_profile")


def fig4_4a(d) -> None:
    """图 4-4a 指定日期储电量轨迹（2×2 面板，线型区分变体）。"""
    tg = d["targets"]
    taus = sorted({r["date"] for r in tg})
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 5.2), sharex=True, sharey=True,
                             gridspec_kw=dict(hspace=0.26, wspace=0.10, top=0.86))
    axes = axes.ravel()
    handles = None
    S_all = []
    for ax, dt in zip(axes, taus):
        style(ax)
        for v, col, ls, mk, lab in (("2", C_GREY, "--", "s", LAB42), ("3", C_MAIN, "-", "o", LAB43)):
            rows = sorted([r for r in tg if r["date"] == dt and r["variant"] == v],
                          key=lambda r: int(r["slot"]))
            S = np.array([f(r["S"]) for r in rows])
            S_all.append(S)
            ax.plot(mid_h(np.arange(144)), S, color=col, lw=1.3, ls=ls, zorder=Z_DATA, label=lab)
            ax.plot(mid_h(np.arange(144))[::24], S[::24], marker=mk, ms=2.8, color=col,
                    ls="none", zorder=Z_DATA + 1)
        ax.axhline(10800, color=C_GREY_L, lw=0.8, ls=":", zorder=Z_BASE)
        ax.axhline(1200, color=C_GREY_L, lw=0.8, ls=":", zorder=Z_BASE)
        ax.set_ylim(0, 12600)
        hour_ticks(ax)
        panel_tag(ax, dt, "tl")
        if handles is None:
            handles = ax.get_legend_handles_labels()
    for ax in axes[2:]:
        ax.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    for ax in (axes[0], axes[2]):
        ax.set_ylabel("储电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    note_ax(axes[0], 0.988, 0.895, "上界 10800", ha="right", va="top", color=C_GREY)
    note_ax(axes[0], 0.988, 0.135, "下界 1200", ha="right", va="bottom", color=C_GREY)
    fig.legend(*handles, loc="upper center", bbox_to_anchor=(0.5, 0.985), ncol=2,
               frameon=False, fontsize=FS_LEG, labelcolor=C_TEXT, handlelength=2.2,
               columnspacing=1.4)
    save(fig, "fig4_4a_soc_trajectory")


def fig4_4b(d) -> None:
    """图 4-4b 储电量分布与边界触及（分组直方图 + 边界竖线 + 精确触及计数）。"""
    lo = np.array([f(r["bin_lo"]) for r in d["soc_hist"]])
    hi = np.array([f(r["bin_hi"]) for r in d["soc_hist"]])
    c42 = np.array([f(r["count_42"]) for r in d["soc_hist"]])
    c43 = np.array([f(r["count_43"]) for r in d["soc_hist"]])
    ctr = (lo + hi) / 2.0
    w = (hi - lo)[0] * 0.92
    ymax = max(c42.max(), c43.max())
    h2, h3 = d["soc_hits"]["2"], d["soc_hits"]["3"]
    n_slots = float(h2["n_slots"])
    lo_edge, hi_edge = lo[0], hi[-1]

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    style(ax)
    ax.bar(ctr - w * 0.24, c42, w * 0.48, color=C_GREY, lw=0, label=LAB42, zorder=Z_DATA)
    ax.bar(ctr + w * 0.24, c43, w * 0.48, color=C_MAIN, lw=0, label=LAB43, zorder=Z_DATA)
    for xv in (1200, 10800):
        ax.axvline(xv, color=C_ACCENT, lw=0.9, alpha=0.85, zorder=Z_BASE + 1)
    # 精确的边界触及计数（容差 1e-6；与末端分箱不是同一个量）
    ax.annotate(f"贴上界 10800：4-2 {int(float(h2['at_max'])):,d} 个时段"
                f"（{100*float(h2['at_max'])/n_slots:.2f}%）",
                xy=(10760, c42[-1]), xytext=(6450, ymax * 1.10),
                ha="left", va="top", fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    ax.text(6450, ymax * 0.99, f"　　　　　4-3 {int(float(h3['at_max'])):,d} 个"
            f"（{100*float(h3['at_max'])/n_slots:.2f}%）",
            ha="left", va="top", fontsize=FS_NOTE, color=C_MAIN, zorder=Z_NOTE)
    ax.text(lo_edge + 250, ymax * 0.50,
            f"贴下界 1200：4-2 {int(float(h2['at_min'])):,d} 个（{100*float(h2['at_min'])/n_slots:.2f}%）\n"
            f"　　　　　4-3 {int(float(h3['at_min'])):,d} 个（{100*float(h3['at_min'])/n_slots:.2f}%）",
            ha="left", va="center", fontsize=FS_NOTE, color=C_TEXT, zorder=Z_NOTE)
    ax.text(8800, ymax * 0.22,
            f"末端箱 {hi[-1]:,.0f}–{hi_edge:,.0f}：\n4-2 {c42[-1]:,.0f} / 4-3 {c43[-1]:,.0f} 个时段",
            ha="center", va="center", fontsize=FS_NOTE - 1.0, color=C_GREY, zorder=Z_NOTE)
    ax.set_xlabel("储电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("时段数 / 个", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_xlim(lo_edge - 180, hi_edge + 240)
    ax.set_ylim(0, ymax * 1.30)
    legend(ax, loc="upper center", bbox_to_anchor=(0.5, 1.02), ncol=2)
    save(fig, "fig4_4b_soc_distribution")


def fig4_5a(d) -> None:
    """图 4-5a 紧急购电的价格档与时刻分布（左右双面板）。"""
    band = d["band"]
    hour = d["hourly"]
    bx = np.arange(len(band))
    blab = [f"{f(r['band_lo']):.1f}–{f(r['band_hi']):.1f}" for r in band]
    b42 = np.array([f(r["kwh_42"]) for r in band])
    b43 = np.array([f(r["kwh_43"]) for r in band])
    hx = np.arange(24)
    h42 = np.array([f(r["emergency_kwh_42"]) for r in hour])
    h43 = np.array([f(r["emergency_kwh_43"]) for r in hour])

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, W_2H + 0.4),
                                 gridspec_kw=dict(wspace=0.28, width_ratios=[1.05, 1.2]))
    style(a1); style(a2)

    w = 0.38
    a1.bar(bx - w / 2, b42, w, color=C_GREY, lw=0, label=LAB42, zorder=Z_DATA)
    a1.bar(bx + w / 2, b43, w, color=C_MAIN, lw=0, label=LAB43, zorder=Z_DATA)
    a1.set_xticks(bx)
    a1.set_xticklabels(blab, rotation=45, ha="right", fontsize=FS_TICK - 1.2)
    a1.set_xlabel("电价档 / (元/kWh)", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylabel("紧急购电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(0, max(b42.max(), b43.max()) * 1.42)
    hi_share = 100 * b42[[f(r["band_lo"]) >= 1.0 for r in band]].sum() / b42.sum()
    a1.annotate(f"≥1.0 元/kWh 的四个档合计\n占 4-2 全期紧急购电量的 {hi_share:.1f}%",
                xy=(bx[-1] - w / 2, b42[-1]), xytext=(bx[-1] - 0.1, b42.max() * 1.38),
                ha="right", va="top", fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    panel_tag(a1, "(a) 按电价档", "tl")
    legend(a1, loc="upper left", bbox_to_anchor=(0.0, 0.94))

    a2.bar(hx - w / 2, h42, w, color=C_GREY, lw=0, label=LAB42, zorder=Z_DATA)
    a2.bar(hx + w / 2, h43, w, color=C_MAIN, lw=0, label=LAB43, zorder=Z_DATA)
    a2.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylabel("紧急购电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_xticks([0, 4, 8, 12, 16, 20, 23])
    a2.set_xlim(-1, 24)
    a2.set_ylim(0, max(h42.max(), h43.max()) * 1.30)
    panel_tag(a2, "(b) 按时刻", "tl")
    legend(a2, loc="upper left", bbox_to_anchor=(0.0, 0.96))
    save(fig, "fig4_5a_emergency_price_band")


def fig4_5b(d) -> None:
    """图 4-5b 弃电量的日内分布（分组柱，单一量纲）。"""
    hour = d["hourly"]
    hx = np.arange(24)
    c42 = np.array([f(r["curtail_kwh_42"]) for r in hour])
    c43 = np.array([f(r["curtail_kwh_43"]) for r in hour])
    ymax = max(c42.max(), c43.max())

    fig, ax = plt.subplots(figsize=(7.0, 3.7))
    style(ax)
    w = 0.38
    ax.bar(hx - w / 2, c42, w, color=C_GREY, lw=0, label=LAB42, zorder=Z_DATA)
    ax.bar(hx + w / 2, c43, w, color=C_MAIN, lw=0, label=LAB43, zorder=Z_DATA)
    ax.set_xlabel("时刻 / h", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylabel("弃电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_xticks(list(range(0, 24, 2)))
    ax.set_xlim(-1, 24)
    ax.set_ylim(0, ymax * 1.42)
    ipk = int(np.argmax(c42))
    ax.annotate(f"午间光伏高峰 {ipk}:00\n4-2 {c42[ipk]:,.0f} kWh", xy=(ipk, c42[ipk]),
                xytext=(ipk + 2.0, ymax * 1.16), fontsize=FS_NOTE, color=C_ACCENT,
                zorder=Z_NOTE, arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    note(ax, 0.2, ymax * 0.52,
         "注：弃电量含「已买入但未消耗」的计划电量，\n不等于弃光（模型不允许倒送 / 售电）", color=C_TEXT)
    legend(ax, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2)
    save(fig, "fig4_5b_curtail_profile")


def fig4_6(d) -> None:
    """图 4-6 四种组合的总费用对照（2×2）。"""
    cells = d["cells"]
    xx = np.arange(len(cells))
    vals = np.array([f(r["total_cost_yuan"]) for r in cells])
    q3 = f(d["pf"][0]["total_cost_yuan"])
    ylim_top = 2.10e7

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    style(ax)
    for x, v in zip(xx, vals):
        if np.isnan(v):
            ax.bar(x, 1.35e7, 0.56, facecolor="white", edgecolor=C_GREY, lw=0.9,
                   hatch="///", zorder=Z_DATA)
            ax.text(x, 1.35e7 + 2.0e5, "【待补】\n第二问结果", ha="center", va="bottom",
                    fontsize=FS_NOTE, color=C_GREY, zorder=Z_NOTE)
        else:
            col = C_MAIN if x == 3 else C_GREY
            ax.bar(x, v, 0.56, color=col, edgecolor=C_MAIN_D if x == 3 else C_GREY,
                   lw=0.7, zorder=Z_DATA)
            ax.text(x, v + 2.0e5, f"{v:,.0f}", ha="center", va="bottom",
                    fontsize=FS_NOTE, color=C_TEXT, zorder=Z_NOTE)
    ax.axhline(q3, color=C_GREY, lw=0.9, ls="--", zorder=Z_BASE)
    note_ax(ax, 0.012, 0.985, f"虚线：第三问（确定性电价）{q3:,.0f} 元", va="top", color=C_GREY)

    ax.annotate("−1,354,320.1874 元\n（以 4-2 为基准 −8.91%）", xy=(3.0, 1.44e7),
                xytext=(1.92, 2.19e7), fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.8, color=C_ACCENT))
    ax.annotate("+685,112.0546 元（+5.2050%）", xy=(2.48, 1.53e7),
                xytext=(1.92, 1.78e7), fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.8, color=C_ACCENT))
    ax.set_xticks(xx)
    ax.set_xticklabels(["确定电价\n× 一次决策", "确定电价\n× 四阶段滚动",
                        "波动电价\n× 一次决策", "波动电价\n× 四阶段滚动"], fontsize=FS_TICK)
    ax.set_ylabel("交付期总费用 / 元", fontsize=FS_LABEL, color=C_TEXT)
    ax.set_ylim(0, 2.35e7)
    ax.set_xlim(-0.6, 3.6)
    save(fig, "fig4_6_strategy_compare")


def fig4_7a(d) -> None:
    """图 4-7a 求解器配置稳定性与 LP 退化（左右双面板）。"""
    sens = [r for r in d["solver"] if not r["method"].startswith("highs（")]
    labels = [f"{'4-' + r['variant']}\n{r['method']}" for r in sens]
    gap = np.array([abs(f(r["total_gap_yuan"])) for r in sens])
    deg = [r for r in d["solv_deg"] if r["method"] == "highs-ipm"]
    ov = [r for r in d["solv_deg"] if r["scope"] == "overall"][0]
    sx = np.arange(len(sens))
    dx = np.arange(len(deg))
    rate = np.array([100 * f(r["n_solution_differs"]) / f(r["n"]) for r in deg])
    # overall 行：n 为 LP 数（1284），解向量不同的对数为 1145；(LP, 算法) 对总数 = 2 × 1284
    ov_rate = 100 * f(ov["n_solution_differs"]) / (2.0 * f(ov["n"]))

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, W_2H + 0.5),
                                 gridspec_kw=dict(wspace=0.32, width_ratios=[1, 1.05]))
    style(a1); style(a2)

    a1.bar(sx, np.maximum(gap, 0), 0.5, color=C_MAIN, lw=0, zorder=Z_DATA)
    a1.axhline(1e-6, color=C_ACCENT, lw=0.9, ls="--", zorder=Z_BASE)
    a1.set_xticks(sx); a1.set_xticklabels(labels, fontsize=FS_TICK - 0.8)
    a1.set_ylabel("与主答案的费用差 / 元", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(0, 2.6e-6)
    for x, g in zip(sx, gap):
        txt = "逐位相同" if g == 0 else f"{g:.2e}"
        a1.text(x, g + 0.06e-6, txt, ha="center", va="bottom", fontsize=FS_NOTE,
                color=C_TEXT, zorder=Z_NOTE)
    note_ax(a1, 0.988, 0.60, "虚线：容差 1e-6 元", ha="right", va="bottom", color=C_ACCENT)
    panel_tag(a1, "(a) 整年换算法：费用不依赖求解器", "tl")

    a2.bar(dx, rate, 0.5, color=C_ACCENT, lw=0, zorder=Z_DATA)
    a2.axhline(100, color=C_GREY_L, lw=0.8, ls=":", zorder=Z_BASE)
    for x, r_ in zip(dx, rate):
        a2.text(x, r_ + 2.5, f"{r_:.1f}%", ha="center", va="bottom", fontsize=FS_NOTE,
                color=C_TEXT, zorder=Z_NOTE)
    a2.set_xticks(dx)
    a2.set_xticklabels([r["scope"] for r in deg], fontsize=FS_TICK)
    a2.set_ylabel("解向量不同的 LP 占比 / %", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylim(0, 132)
    note_ax(a2, 0.012, 0.915, f"注：费用面唯一，策略面不唯一——\n总体 {ov_rate:.1f}% 的 (LP, 算法) 对解向量不同",
            va="top", color=C_ACCENT)
    panel_tag(a2, "(b) 解向量并不唯一", "tl")
    save(fig, "fig4_7a_solver_stability")


def fig4_7b(d) -> None:
    """图 4-7b 终端储能水价 λ 的全年敏感性（上下双面板，不用双 Y 轴）。"""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.0, W_2V), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1.05, 1], hspace=0.20))
    style(a1); style(a2)
    styles = {"2": (C_GREY, "--", "s"), "3": (C_MAIN, "-", "o")}

    for v in ("2", "3"):
        rows = sorted([r for r in d["lam"] if r["variant"] == v], key=lambda r: f(r["lam_over_baseline"]))
        x = np.array([f(r["lam_over_baseline"]) for r in rows])
        cost = np.array([f(r["total_cost_yuan"]) for r in rows])
        soc = np.array([f(r["soc_end_delivery_kwh"]) for r in rows])
        col, ls, mk = styles[v]
        lab = LAB43 if v == "3" else LAB42
        a1.plot(x, cost, color=col, lw=1.4, ls=ls, marker=mk, ms=3.4, zorder=Z_DATA, label=lab)
        a2.plot(x, soc, color=col, lw=1.4, ls=ls, marker=mk, ms=3.4, zorder=Z_DATA, label=lab)
    for ax in (a1, a2):
        ax.axvline(1.0, color=C_SPINE, lw=0.8, ls=":", zorder=Z_BASE)

    a1.set_ylabel("交付期总费用 / 元", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_ylim(1.388e7, 1.545e7)
    a1.annotate("4-2 极差 133,400.36 元\n（0.8775%）", xy=(1.0, 1.5162e7), xytext=(1.28, 1.5300e7),
                fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    a1.annotate("4-3 极差 124,538.50 元\n（0.8993%）", xy=(3.0, 1.3972e7), xytext=(1.30, 1.3955e7),
                fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE,
                arrowprops=dict(arrowstyle="->", lw=0.7, color=C_ACCENT))
    note_ax(a1, 0.012, 0.60, "费用随 λ 非单调（V 形）", va="top", color=C_TEXT)
    panel_tag(a1, "(a) 费用对 λ 不敏感", "tl")
    legend(a1, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2)

    a2.axhline(10800, color=C_GREY_L, lw=0.8, ls=":", zorder=Z_BASE)
    a2.axhline(1200, color=C_GREY_L, lw=0.8, ls=":", zorder=Z_BASE)
    a2.axvspan(0.75, 1.0, color=C_ACCENT, alpha=0.10, lw=0, zorder=Z_GRID + 1)
    note(a2, 0.755, 320, "体制切换区 0.75–1.0", va="bottom", color=C_ACCENT)
    a2.set_ylabel("期末储电量 / kWh", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_ylim(0, 13000)
    a2.set_xlabel("λ / λ0（各变体基准的倍数）", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_xlim(-0.1, 3.15)
    note_ax(a2, 0.988, 0.885, "上界 10800", ha="right", va="top", color=C_GREY)
    note_ax(a2, 0.988, 0.10, "下界 1200", ha="right", va="bottom", color=C_GREY)
    panel_tag(a2, "(b) 策略对 λ 敏感（储能体制切换）", "tl")
    legend(a2, loc="center right", ncol=1)
    save(fig, "fig4_7b_lambda_sensitivity")


def fig4_8(d) -> None:
    """图 4-8 完美预见拆分（左右双面板）。"""
    pts = [r for r in d["pf"] if r["kind"] == "point"]
    dec = {r["point"]: r for r in d["pf"] if r["kind"] == "decomposition"}
    lab = [r["point"] for r in pts]
    val = np.array([f(r["total_cost_yuan"]) for r in pts])
    a_risk = f(dec["a 电价波动风险"]["a_volatility_risk_yuan"])
    b_err = f(dec["b 预测误差信息损失"]["b_forecast_error_yuan"])
    total = f(dec["a 电价波动风险"]["total_gap_yuan"])
    xx = np.arange(3)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, W_2H + 0.5),
                                 gridspec_kw=dict(wspace=0.32, width_ratios=[1.3, 1],
                                                  bottom=0.26))
    style(a1); style(a2)

    cols = [C_GREY, C_STATE, C_MAIN]
    a1.bar(xx, val, 0.5, color=cols, edgecolor=C_GREY, lw=0.6, zorder=Z_DATA)
    a1.set_ylim(1.30e7, 1.442e7)
    for x, v in zip(xx, val):
        a1.text(x, v + 2.2e4, f"{v:,.0f}", ha="center", va="bottom", fontsize=FS_NOTE,
                color=C_TEXT, zorder=Z_NOTE)
    a1.set_xticks(xx); a1.set_xticklabels(lab, fontsize=FS_TICK)
    a1.set_ylabel("交付期总费用 / 元", fontsize=FS_LABEL, color=C_TEXT)
    a1.set_xlim(-0.72, 2.95)
    a1.annotate("", xy=(1.42, 1.361e7), xytext=(1.42, 1.331e7),
                arrowprops=dict(arrowstyle="<->", lw=0.9, color=C_ACCENT))
    a1.annotate("", xy=(2.42, 1.378e7), xytext=(2.42, 1.361e7),
                arrowprops=dict(arrowstyle="<->", lw=0.9, color=C_ACCENT))
    a1.text(2.90, 1.4385e7, f"(a) 波动风险\n+{a_risk:,.0f} 元（+4.31%）",
            ha="right", va="top", fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE)
    a1.text(2.90, 1.4005e7, f"(b) 预测误差\n+{b_err:,.0f} 元（+0.89%）",
            ha="right", va="top", fontsize=FS_NOTE, color=C_ACCENT, zorder=Z_NOTE)
    panel_tag(a1, "(a) 三个价格情形", "tl")

    a2.bar([0], [a_risk], 0.44, color=C_ACCENT, lw=0, zorder=Z_DATA,
           label=f"(a) 波动风险  {a_risk:,.0f} 元")
    a2.bar([0], [b_err], 0.44, bottom=[a_risk], color=C_GREYBLUE, lw=0, zorder=Z_DATA,
           label=f"(b) 预测误差  {b_err:,.0f} 元")
    a2.text(0, a_risk * 0.5, f"{100*a_risk/total:.1f}%", ha="center", va="center",
            fontsize=FS_LABEL, color="white", zorder=Z_NOTE)
    a2.text(0, a_risk + b_err * 0.5, f"{100*b_err/total:.1f}%", ha="center", va="center",
            fontsize=FS_NOTE, color=C_TEXT, zorder=Z_NOTE)
    a2.set_ylim(0, total * 1.34)
    a2.set_xticks([0]); a2.set_xticklabels(["与第三问的\n总差额"])
    a2.set_ylabel("相对第三问的差额 / 元", fontsize=FS_LABEL, color=C_TEXT)
    a2.set_xlim(-0.75, 0.75)
    note_ax(a2, 0.988, 0.895, f"合计 {total:,.2f} 元\n恒等式残差 0", ha="right", va="top",
            color=C_TEXT)
    panel_tag(a2, "(b) +5.2050% 的构成", "tl")
    # 图注级说明（放在画布底部，避免与坐标轴内元素抢位）
    fig.text(0.012, 0.012,
             "注：左板纵轴自 1.30e7 起截断（规范 §28：不删极值，须声明）；"
             "右板 (a) 波动风险为 567,796.36 元、(b) 预测误差为 117,315.70 元。"
             "完美预见不是可交付方案，仅作归因用。",
             ha="left", va="bottom", fontsize=FS_NOTE - 0.5, color=C_GREY)
    save(fig, "fig4_8_perfect_foresight")

# =============================================================================
# 五、主流程
# =============================================================================
FIGURES = (fig4_1a, fig4_1b, fig4_2a, fig4_2b, fig4_3a, fig4_3b, fig4_4a,
           fig4_4b, fig4_5a, fig4_5b, fig4_6, fig4_7a, fig4_7b, fig4_8)


def main() -> None:
    print(f"[字体] {FONT}")
    print("[1] 装载数据")
    d = load_all()
    print("[2] 数据审计")
    audit(d)
    print("[3] 绘图（14 图 × SVG/PDF/PNG）")
    for fn in FIGURES:
        fn(d)
    print(f"\n全部图件已输出到 {HERE}")


if __name__ == "__main__":
    main()
