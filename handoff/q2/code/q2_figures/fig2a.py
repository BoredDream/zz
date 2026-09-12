# -*- coding: utf-8 -*-
"""图 2a　单日计划购电对分时电价的响应（单主题图）
================================================================================
核心任务（本图只回答这一个问题）
    模型是否实现了"低价多购、高价少购"的电价响应策略？

信息结构（共享 x 轴，上 35% / 下 65%）
    · 上面板：仅分时电价 —— 赤陶阶梯线 + 尖峰价时段极浅底纹（alpha 0.10）
      无右轴、不叠加任何其他变量
    · 下面板：仅计划购电量 —— 窄柱（宽 0.84×10 分钟），深蓝灰 #4C6E91 单一主色，
      无面积填充；紧急购电量仅在确实存在时以同色赤陶叠加（示例日恰为 0，故不出现）

刻意不画的内容（避免与图1 职责重叠、降低视觉噪声）
    · 实际净负荷、模型预测净负荷 —— 预测准确性由图1 承担
    · 大框标注、长弯箭头 —— 尖峰价时段的计划购电合计放到图注与正文（方案A）
    · 图内数值标注 —— 全部移入图注

数据
    完全来自 outputs/q2/interval_detail.csv 的 2025-06-21 原始记录，
    未平滑、未插值、未改单位、未改时间范围。

口径提醒
    本图 x 轴为【自然日 00:00–24:00】时刻，因此使用的是 interval_detail.csv 的
    committed_plan_kwh（自然日口径），**不是** result2.xlsx 的模板行口径；
    两者错开一格、合计相差约 1,200 kWh/天，引用"全天"时须注明。
================================================================================
"""
from __future__ import annotations

try:
    from ._common import (C_ACCENT, C_MAIN, FONT, RC, detail, save, slot_of, style)
except ImportError:
    from _common import (C_ACCENT, C_MAIN, FONT, RC, detail, save, slot_of, style)

import numpy as np
import matplotlib
import matplotlib.pyplot as plt

TARGET_DATE = "2025-06-21"
PEAK_PRICE = 1.25          # 尖峰价阈值（元/kWh），与图1b、图4b 的分档保持一致


def fig2a() -> dict:
    """绘制图2a，返回 {"files": …, "meta": …}。"""
    rows = sorted([r for r in detail() if r["date"] == TARGET_DATE],
                  key=lambda r: slot_of(r["time_start"]))
    if len(rows) != 144:
        raise ValueError(f"{TARGET_DATE} 时段数异常：{len(rows)}，应为 144")

    t = np.array([slot_of(r["time_start"]) for r in rows])
    plan = np.array([float(r["committed_plan_kwh"]) for r in rows])
    price = np.array([float(r["price_yuan_per_kwh"]) for r in rows])
    em = np.array([float(r["emergency_kwh"]) for r in rows])

    step_x = np.r_[t, 24.0]
    step_y = np.r_[price, price[-1]]
    peak = price >= PEAK_PRICE
    peak_plan = float(plan[peak].sum()) if peak.any() else 0.0
    has_em = bool(em.sum() > 1e-7)

    with matplotlib.rc_context(RC):
        fig, (axp, axb) = plt.subplots(
            2, 1, figsize=(7.1, 3.9), sharex=True,
            gridspec_kw={"height_ratios": [0.54, 1.0], "hspace": 0.10})

        # ---------------- 上面板：分时电价（唯一变量） ----------------
        if peak.any():
            axp.axvspan(t[peak][0], t[peak][-1] + 10 / 60,
                        color=C_ACCENT, alpha=0.10, zorder=0, lw=0)
            axp.annotate("尖峰价时段",
                         xy=((t[peak][0] + t[peak][-1] + 10 / 60) / 2, price.max() * 1.06),
                         ha="center", va="bottom", fontsize=7.8, color=C_ACCENT, zorder=6)
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
        axp.set_title(f"{TARGET_DATE} 单日计划购电与分时电价", pad=5)

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
        "date": TARGET_DATE,
        "plan_total_kwh": float(plan.sum()),
        "plan_max_kwh": float(plan.max()),
        "emergency_total_kwh": float(em.sum()), "has_emergency": has_em,
        "peak_intervals": int(peak.sum()), "peak_plan_kwh": peak_plan,
        "peak_plan_share_pct": float(peak_plan / plan.sum() * 100),
        "zero_plan_intervals": int((plan <= 1e-9).sum()),
        "price_min": float(price.min()), "price_max": float(price.max()),
    }}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig2a()
    print(f"[图2a] 单日计划购电对分时电价的响应  字体 {FONT}")
    for k, v in res["meta"].items():
        print(f"   {k} = {v}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
