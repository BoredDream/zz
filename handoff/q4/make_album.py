"""构建第四问图集（A4 纵向，每页一张图 + 图号标题）。

用法：python make_album.py
输入：figures/*.png（600 dpi）
输出：图集_第四问_论文版.pdf
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from matplotlib import font_manager, rcParams
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "图集_第四问_论文版.pdf"

# 图号 → (文件名, 图注标题)   共 14 个图号，与 第四问_图表数据需求清单.csv 一致
PAGES = [
    ("图 4-1a", "fig4_1a_price_profile", "附件4 日内电价形态"),
    ("图 4-1b", "fig4_1b_price_forecast", "电价预测精度（四阶段）"),
    ("图 4-2a", "fig4_2a_dispatch_2days", "两日调度对照（4-2 vs 4-3）"),
    ("图 4-2b", "fig4_2b_plan_vs_final", "指定日期计划购电量与最终调整购电量"),
    ("图 4-3a", "fig4_3a_monthly_cost", "月度费用构成与紧急购电占比"),
    ("图 4-3b", "fig4_3b_adjust_profile", "合约调整量的日内分布与阶段分解"),
    ("图 4-4a", "fig4_4a_soc_trajectory", "指定日期储电量轨迹"),
    ("图 4-4b", "fig4_4b_soc_distribution", "储电量分布与边界触及"),
    ("图 4-5a", "fig4_5a_emergency_price_band", "紧急购电的价格档与时刻分布"),
    ("图 4-5b", "fig4_5b_curtail_profile", "弃电量的日内分布"),
    ("图 4-6", "fig4_6_strategy_compare", "四种组合的总费用对照（2×2）"),
    ("图 4-7a", "fig4_7a_solver_stability", "求解器配置稳定性与 LP 退化"),
    ("图 4-7b", "fig4_7b_lambda_sensitivity", "终端储能水价 λ 的全年敏感性"),
    ("图 4-8", "fig4_8_perfect_foresight", "完美预见拆分：与第三问 +5.20% 的构成"),
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
    missing = [stem for _, stem, _ in PAGES if not (FIG / f"{stem}.png").exists()]
    if missing:
        print(f"⚠️ 以下 {len(missing)} 张图缺 PNG，将跳过：")
        for m in missing:
            print(f"    - {m}.png")
        print("   （先运行 figures/figs_q4_paper.py 出图，再装册。）\n")
    if len(missing) == len(PAGES):
        print("一张图都没有，**不生成图集 PDF**（避免产出只有封面的空图集）。")
        return

    with PdfPages(OUT) as pdf:
        # 封面
        fig = plt.figure(figsize=(A4W, A4H))
        fig.text(0.5, 0.62, "第四问　论文图表集", ha="center", va="center", fontsize=20,
                 color="#333333")
        fig.text(0.5, 0.55, "波动电价下的购电策略（4-2 一次决策 / 4-3 四阶段滚动）",
                 ha="center", va="center", fontsize=12, color="#5B6470")
        fig.text(0.5, 0.44,
                 "2025-02-01 至 2025-12-31（334 个自然日）\n"
                 "4-2 总购电费 15,202,115.13 元　·　4-3 总购电费 13,847,794.94 元\n"
                 "K = 30 情景 · 四阶段发布（0:00 / 6:00 / 12:00 / 18:00）\n"
                 "与第三问的 +5.20% 已拆为波动风险 +4.31% 与预测误差 +0.89%",
                 ha="center", va="center", fontsize=10, color="#5B6470", linespacing=1.8)
        fig.text(0.5, 0.06, f"共 {len(PAGES)} 张图 · 600 dpi · SVG/PDF 同源", ha="center",
                 fontsize=9, color="#9AA4AE")
        pdf.savefig(fig)
        plt.close(fig)

        # 每图一页
        n = 0
        for tag, stem, title in PAGES:
            png = FIG / f"{stem}.png"
            if not png.exists():
                print(f"  [跳过] 缺少 {png.name}")
                continue
            im = Image.open(png)
            w, h = im.size
            ar = h / w
            fig = plt.figure(figsize=(A4W, A4H))
            # 版面：标题 0.962，图区 0.085–0.935
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
            n += 1
            print(f"  [入册] {tag}  {title}")

    if n:
        print(f"\n图集已输出：{OUT}  ({OUT.stat().st_size / 1024:.0f} KB，共 {n} 页图)")
    else:
        print("\n未生成图集（一张图都没有）。")


if __name__ == "__main__":
    main()
