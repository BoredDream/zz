# -*- coding: utf-8 -*-
"""第二问图集 · 公共模块
================================================================================
本模块是全部图件的【唯一权威定义】：数据路径、配色、matplotlib 全局样式、
以及各图共用的小工具。任何一张图只从本模块取公共件，不重复定义。

目录约定（本文件位于 handoff/q2/code/q2_figures/_common.py）：
    CODE   = handoff/q2/code              ← 代码目录（run_all_figures.py 在此）
    Q2DIR  = handoff/q2                   ← 交付包根
    DATA   = handoff/q2/_figdata          ← 绘图数据（CSV）
    FIGDIR = handoff/q2/figures           ← 成图输出（svg/pdf/png）
    REPO   = 仓库根（含 outputs/、problem/、src/）

视觉规范（学术插图风格，低饱和蓝灰）：
  · 白底、简洁二维，无渐变 / 发光 / 3D / 阴影
  · 去顶部与右侧边框；仅水平浅灰弱网格（alpha 0.30, lw 0.5）
  · 配色全部低饱和蓝灰系：主色 深蓝灰，强调色 去饱和赤陶
  · 同义同色：同一含义在 9 张图中颜色一致；同图内不同系列以线型 + marker 区分
  · 线型约定：实线/● = 主数据；虚线/■ = 对照或实测；点划线/▲ = 次要
  · 文字统一深灰 #333333；字号 刻度 8.5 / 轴标题 9.5 / 图例 8.5
  · 输出 SVG（矢量、文字可编辑）+ PDF（矢量）+ PNG（600 dpi）
================================================================================
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib
from matplotlib import font_manager as fm
import matplotlib.pyplot as plt

# ============================== 1. 路径 ==============================
HERE = Path(__file__).resolve().parent          # .../handoff/q2/code/q2_figures
CODE = HERE.parent                              # .../handoff/q2/code
Q2DIR = CODE.parent                             # .../handoff/q2
REPO = CODE.parents[2]                          # 仓库根
DATA = Q2DIR / "_figdata"                       # 绘图数据
FIGDIR = Q2DIR / "figures"                      # 成图输出目录

# 让各图模块无论以「包导入」还是「单独运行」方式加载，都能 import q2_figures
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

# ============================== 2. 配色（唯一权威）==============================
C_MAIN = "#4C6E91"        # 主色：计划量 / 模型预测 / 主数据
C_MAIN_D = "#3A5470"      # 主色深版：中位数线、被强调的主数据
C_ACCENT = "#A9705A"      # 强调色（去饱和赤陶）：紧急购电、最大偏差、核心结论
C_ACCENT_L = "#DCC3B6"    # 强调色浅版（填充）
C_ACT = "#5B6470"         # 实测 / 真实观测
C_GREY = "#9AA4AE"        # 对照 / 次要
C_GREY_L = "#C9D0D6"      # 对照浅版（填充）
C_SOC = "#7E9B84"         # 储电量（低饱和绿，含灰调）
C_SOC_L = "#C6D3C8"       # 储电量浅版（填充）
C_GRID = "#DFE3E7"        # 网格
C_TEXT = "#333333"        # 文字
C_SPINE = "#B4BBC2"       # 坐标轴边框

LS_MAIN, LS_ALT, LS_ALT2 = "-", "--", "-."          # 线型约定
MK_MAIN, MK_ALT, MK_ALT2 = "o", "s", "^"            # marker 约定

# ============================== 3. 全局常量 ==============================
FONT_CANDIDATES = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                   "Arial Unicode MS", "DejaVu Sans"]
SAVE_FORMATS = ["svg", "pdf", "png"]
PNG_DPI = 600
DT = 1.0 / 6.0                      # 单个 10 分钟时段的小时数
E_MAX = 5000.0 * DT                 # 833.3333 kWh/时段（题面附录1 功率上限换算）
SOC_MIN, SOC_MAX = 1200.0, 10800.0  # 题面附录1 的储电量运行区间


def pick_font() -> str:
    """依次尝试候选中文字体，返回第一个可用的。

    注意：本项目实测 SimHei / SimSun / KaiTi / FangSong / DengXian /
    Microsoft JhengHei 均缺 U+2212 减号字形，若被选中需配合
    axes.unicode_minus=False 使用，否则坐标轴负号会渲染成空白方框。
    """
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
    "svg.fonttype": "none",          # SVG 内保留文字节点，便于排版二次编辑
    "axes.grid": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
}


# ============================== 4. 共用工具 ==============================
def save(fig, stem: str) -> dict:
    """统一保存：svg / pdf / png(600dpi)，均白底、紧凑边界。"""
    out = {}
    for ext in SAVE_FORMATS:
        p = FIGDIR / f"{stem}.{ext}"
        FIGDIR.mkdir(parents=True, exist_ok=True)
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
        ax.spines[s].set_color(C_SPINE)
    if grid:
        ax.grid(axis=grid_axis, color=C_GRID, lw=0.5, alpha=0.30)
        ax.set_axisbelow(True)
    return ax


def rd(p: Path) -> list[dict]:
    """读 UTF-8-BOM CSV 为 dict 列表。"""
    with p.open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def detail() -> list[dict]:
    """读求解器落盘的逐时段明细（334 天 × 144 时段 = 48,096 条），并校验行数。"""
    rows = rd(REPO / "outputs" / "q2" / "interval_detail.csv")
    if len(rows) != 48_096:
        raise ValueError(f"interval_detail.csv 行数异常：{len(rows)}，应为 48,096")
    return rows


def slot_of(t: str) -> float:
    """时段起点标签 → 当天小时数（'24:00' → 24.0）。"""
    return 24.0 if t == "24:00" else int(t[:2]) + int(t[3:5]) / 60.0


def box(ax, text, xy, xytext, color=None, ha="left", rad=None):
    """结论标注：白底细边、无阴影、无渐变、无圆角大框。"""
    ap = dict(arrowstyle="-", lw=0.6, color=C_GREY, shrinkA=0, shrinkB=2)
    if rad is not None:
        ap["connectionstyle"] = f"arc3,rad={rad}"
    return ax.annotate(text, xy=xy, xytext=xytext, textcoords="offset points",
                       fontsize=8, color=color or C_TEXT, ha=ha, zorder=9,
                       arrowprops=ap,
                       bbox=dict(boxstyle="round,pad=0.22", fc="white",
                                 ec=C_GREY_L, lw=0.6, alpha=0.95))
