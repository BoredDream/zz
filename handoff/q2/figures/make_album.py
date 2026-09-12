# -*- coding: utf-8 -*-
"""把重设计后的 5 张图合并成一份纯图集 PDF，便于一次性审阅与打印。"""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

HERE = Path(__file__).resolve().parent          # handoff/q2/figures
ALBUM_DIR = HERE.parent                         # 图集写到 handoff/q2/ 下
FONT = next((n for n in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                         "Arial Unicode MS", "DejaVu Sans"]
             if n in {f.name for f in fm.fontManager.ttflist}), "DejaVu Sans")

ITEMS = [
    ("fig1_netload_forecast.png", "图 1　净负荷预测与情景包络（四个指定日期，2×2）"),
    ("fig1b_typical_day.png", "图 1b　典型日（附件1）功率曲线与分时电价"),
    ("fig2a_single_day_dispatch.png", "图 2a　2025-06-21 单日计划购电量、实际净负荷与电价"),
    ("fig2b_monthly_stack.png", "图 2b　月度购电量构成与紧急购电占比"),
    ("fig3a_soc_trajectory.png", "图 3a　四个指定日期的储电量轨迹"),
    ("fig3b_soc_hist.png", "图 3b　储电量分布与单时段充放电量分布"),
    ("fig4a_forecast_error.png", "图 4a　预测误差的日内分布与逐月平均绝对误差"),
    ("fig4b_emergency_cost_band.png", "图 4b　紧急购电量按电价档与按时段的分布"),
    ("fig5_strategy_compare.png", "图 5　三种策略费用构成与终端储电价值敏感性"),
]

with PdfPages(ALBUM_DIR / "图集_第二问_论文版.pdf") as pdf:
    for fname, title in ITEMS:
        img = plt.imread(HERE / fname)
        h, w = img.shape[0], img.shape[1]
        fw = 7.1                                   # A4 正文宽度（英寸）
        fh = fw * h / w + 0.42
        fig = plt.figure(figsize=(fw, fh))
        ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
        ax.imshow(img)
        fig.text(0.5, 0.012, title, ha="center", va="bottom",
                 fontsize=8.5, color="#333333", family=FONT)
        pdf.savefig(fig, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print(f"  已加入: {fname}")

print("\n已生成: 图集_第二问_论文版.pdf",
      (ALBUM_DIR / "图集_第二问_论文版.pdf").stat().st_size, "bytes")
