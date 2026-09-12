# -*- coding: utf-8 -*-
"""把 9 张论文级图件合并成一份纯图集 PDF，便于一次性审阅与打印。
================================================================================
用法（在任意目录均可执行）：
    python make_album.py

输入：handoff/q2/figures/ 下的 9 个 .png
输出：handoff/q2/图集_第二问_论文版.pdf

说明：仅拼装已生成的 PNG，**不重新绘图**；每页底部标注图号与标题。
      若图件尚未生成，请先运行：python run_all_figures.py
================================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

HERE = Path(__file__).resolve().parent      # handoff/q2/code
Q2DIR = HERE.parent                         # handoff/q2
FIGDIR = Q2DIR / "figures"
ALBUM = Q2DIR / "图集_第二问_论文版.pdf"

FONT = next((n for n in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                         "Arial Unicode MS", "DejaVu Sans"]
             if n in {f.name for f in fm.fontManager.ttflist}), "DejaVu Sans")

# 与 q2_figures.FIGURE_INDEX 保持一致的顺序与标题
ITEMS = [
    ("fig1_netload_forecast.png", "图 1　净负荷预测与情景包络（四个指定日期，2×2）"),
    ("fig1b_typical_day.png", "图 1b　典型日负荷、光伏、净负荷与分时电价"),
    ("fig2a_single_day_dispatch.png", "图 2a　2025-06-21 单日计划购电与分时电价"),
    ("fig2b_monthly_stack.png", "图 2b　月度购电量构成与紧急购电占比"),
    ("fig3a_soc_trajectory.png", "图 3a　四个指定日期的储电量轨迹"),
    ("fig3b_soc_hist.png", "图 3b　储电量分布与单时段充放电量分布"),
    ("fig4a_forecast_error.png", "图 4a　预测误差的日内分布与逐月平均绝对误差"),
    ("fig4b_emergency_cost_band.png", "图 4b　紧急购电量的电价档与时段分布"),
    ("fig5_strategy_compare.png", "图 5　三种口径的费用构成与终端储电价值敏感性"),
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass

    missing = [f for f, _ in ITEMS if not (FIGDIR / f).exists()]
    if missing:
        print("缺少以下图件，请先运行 run_all_figures.py：")
        for m in missing:
            print(f"   {m}")
        return 1

    with PdfPages(ALBUM) as pdf:
        for fname, title in ITEMS:
            img = plt.imread(FIGDIR / fname)
            h, w = img.shape[0], img.shape[1]
            fw = 7.1                                     # A4 正文宽度（英寸）
            fh = fw * h / w + 0.42
            fig = plt.figure(figsize=(fw, fh))
            ax = fig.add_axes((0, 0, 1, 1))
            ax.axis("off")
            ax.imshow(img)
            fig.text(0.5, 0.012, title, ha="center", va="bottom",
                     fontsize=8.5, color="#333333", family=FONT)
            pdf.savefig(fig, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            print(f"  已加入: {fname}")

    print(f"\n已生成: {ALBUM}  ({ALBUM.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
