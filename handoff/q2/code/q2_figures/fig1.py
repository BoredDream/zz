# -*- coding: utf-8 -*-
"""图 1　净负荷预测与情景包络（四个指定日期，2×2）
================================================================================
核心任务
    模型预测的净负荷与真实观测在题目四个指定日期上的吻合程度，以及预测的不确定性范围。

信息结构
    · 上面板×4：每个日期一个面板，深灰虚线 = 真实观测值，深蓝灰实线 = 本文模型中心预测
    · 情景包络只画 **10–90 分位带**（全距带与它几乎重合，属无效信息，已删）
    · 橙色实心点只出现在 **本图内最大偏差所在的面板**，避免被误读为"每格都有极值点"

口径护栏
    · 色带是「历史残差情景包络」，**不是置信区间、不是预测区间**；
      本模型只有 7 或 14 条等权情景，n=7 时在数学上无法给出 95% 分位
    · 全期为留出集回测，48,096 条预测全部有真实值配对，无未来外推
    · 图注的覆盖率口径必须与图内一致：图内只画分位带 → 引用分位带覆盖率

数据源
    _figdata/netload_scenarios_4days.csv（由 code/gen_scenarios.py 生成；
    中心预测与 outputs/q2/interval_detail.csv 的 forecast_net_kwh 逐位一致）
================================================================================
"""
from __future__ import annotations

try:                                       # 包导入（推荐：python -m / run_all_figures.py）
    from ._common import (C_ACCENT, C_ACT, C_GREY_L, C_MAIN, DATA, FONT, LS_ALT,
                          LS_MAIN, MK_ALT, MK_MAIN, RC, box, rd, save, style)
except ImportError:                        # 单独运行本文件
    from _common import (C_ACCENT, C_ACT, C_GREY_L, C_MAIN, DATA, FONT, LS_ALT,
                         LS_MAIN, MK_ALT, MK_MAIN, RC, box, rd, save, style)

from collections import defaultdict

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator

TARGET_DATES = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]


def fig1() -> dict:
    """绘制图1，返回 {"files": …, "meta": …}。"""
    rows = rd(DATA / "netload_scenarios_4days.csv")
    by: dict = defaultdict(lambda: {"scen": defaultdict(dict)})
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
        for ax, d in zip(axes, TARGET_DATES):
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
        axw = axes[TARGET_DATES.index(d)]
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


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                    # noqa: BLE001
        pass
    res = fig1()
    print(f"[图1] 净负荷预测与情景包络  字体 {FONT}")
    for k, v in res["meta"].items():
        print(f"   {k} = {v}")
    for k, v in res["files"].items():
        print(f"   {k}: {v}")
