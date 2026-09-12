"""构建第三问图集（A4 纵向，每页一张图 + 图号标题）。

用法：python make_album.py
输入：figures/*.png（600 dpi）
输出：图集_第三问_论文版.pdf
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from matplotlib import font_manager, rcParams
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "图集_第三问_论文版.pdf"

# 图号 → (文件名, 图注标题)
PAGES = [
    ("图 3-1a", "fig3_1a_system_profile", "日内电价与净负荷形态"),
    ("图 3-1b", "fig3_1b_forecast_accuracy", "光伏预报精度：双源组合对比"),
    ("图 3-2a", "fig3_2a_adjust_overview", "各日合约量调整量"),
    ("图 3-2b", "fig3_2b_plan_vs_final", "指定日期计划购电量与最终合约量"),
    ("图 3-3a", "fig3_3a_monthly_cost", "月度费用构成与弃电量"),
    ("图 3-3b", "fig3_3b_curtail_profile", "弃电量的日内分布"),
    ("图 3-4a", "fig3_4a_soc_trajectory", "指定日期储电量轨迹"),
    ("图 3-4b", "fig3_4b_soc_distribution", "储电量分布与边界触及"),
    ("图 3-4c", "fig3_4c_charge_discharge", "充电量与放电量的分布"),
    ("图 3-5a", "fig3_5a_emergency_profile", "紧急购电量的日内分布"),
    ("图 3-5b", "fig3_5b_emergency_price_band", "紧急购电按电价档的分布"),
    ("图 3-6", "fig3_6_stage_value", "八种预报发布组合的交付期总费用"),
    ("图 3-7a", "fig3_7a_solver_stability", "三种求解算法下的费用偏差"),
    ("图 3-7b", "fig3_7b_lambda_sensitivity", "终端储能水价 λ 的全年敏感性"),
]


def pick_font() -> str:
    have = {f.name for f in font_manager.fontManager.ttflist}
    for n in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC"):
        if n in have:
            return n
    return "DejaVu Sans"


FONT = pick_font()
rcParams.update({"font.family": FONT, "axes.unicode_minus": False})

A4W, A4H = 8.27, 11.69


def main() -> None:
    with PdfPages(OUT) as pdf:
        # 封面
        fig = plt.figure(figsize=(A4W, A4H))
        fig.text(0.5, 0.62, "第三问　论文图表集", ha="center", va="center", fontsize=20,
                 color="#333333")
        fig.text(0.5, 0.55, "含日内预报更新的多阶段随机规划购电策略", ha="center", va="center",
                 fontsize=12, color="#5B6470")
        fig.text(0.5, 0.46,
                 "2025-02-01 至 2025-12-31（334 个自然日）\n"
                 "总购电费 13,162,682.89 元\n"
                 "K = 30 情景 · 四阶段发布（0:00 / 6:00 / 12:00 / 18:00）",
                 ha="center", va="center", fontsize=10, color="#5B6470", linespacing=1.8)
        fig.text(0.5, 0.06, f"共 {len(PAGES)} 张图 · 600 dpi · SVG/PDF 同源", ha="center",
                 fontsize=9, color="#9AA4AE")
        pdf.savefig(fig)
        plt.close(fig)

        # 每图一页
        for tag, stem, title in PAGES:
            png = FIG / f"{stem}.png"
            if not png.exists():
                print(f"  [跳过] 缺少 {png.name}")
                continue
            im = Image.open(png)
            w, h = im.size
            ar = h / w
            fig = plt.figure(figsize=(A4W, A4H))
            # 版面：标题 0.955，图区 0.10–0.93
            top, bot, left, right = 0.935, 0.085, 0.07, 0.93
            avail_w = right - left
            avail_h = top - bot
            box_w = avail_w
            box_h = box_w * ar
            if box_h > avail_h:
                box_h = avail_h
                box_w = box_h / ar
            x0 = left + (avail_w - box_w) / 2
            y0 = bot + (avail_h - box_h) / 2
            ax = fig.add_axes([x0, y0, box_w, box_h])
            ax.imshow(im)
            ax.set_axis_off()
            fig.text(0.07, 0.962, f"{tag}　{title}", ha="left", va="top", fontsize=11,
                     color="#333333")
            pdf.savefig(fig)
            plt.close(fig)
            print(f"  [入册] {tag}  {title}")
    print(f"\n图集已输出：{OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
