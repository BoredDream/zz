# -*- coding: utf-8 -*-
"""第二问图件包（9 张图，每张图一个模块）。

模块清单
--------
    fig1    图1   净负荷预测与情景包络（四个指定日期 2×2）
    fig1b   图1b  典型日负荷 / 光伏 / 净负荷与分时电价
    fig2a   图2a  单日计划购电对分时电价的响应（单主题图）
    fig2b   图2b  月度购电量构成与紧急购电占比
    fig3a   图3a  四个指定日期的储电量轨迹（单面板四日对比）
    fig3b   图3b  储电量分布与单时段充放电量分布
    fig4a   图4a  预测误差的日内分布与逐月平均绝对误差
    fig4b   图4b  紧急购电量按电价档与按时段的分布
    fig5    图5   三种口径的费用构成与终端储电价值敏感性

每个模块都暴露一个无参函数（fig1() / fig1b() / … / fig5()），返回
    {"files": {ext: 路径}, "meta": {关键数值}}
并可直接单独运行，例如：
    python q2_figures/fig2a.py

公共件（路径、配色、样式、工具）统一在 _common.py 定义；一键生成全部图件见
上层目录的 run_all_figures.py。
"""

__all__ = ["fig1", "fig1b", "fig2a", "fig2b", "fig3a",
           "fig3b", "fig4a", "fig4b", "fig5"]

# 各图的中文标题与输出文件名（供 run_all_figures.py 统一列出）
FIGURE_INDEX = [
    ("图1", "净负荷预测与情景包络", "fig1_netload_forecast", "fig1"),
    ("图1b", "典型日负荷、光伏、净负荷与分时电价", "fig1b_typical_day", "fig1b"),
    ("图2a", "单日计划购电对分时电价的响应", "fig2a_single_day_dispatch", "fig2a"),
    ("图2b", "月度购电量构成与紧急购电占比", "fig2b_monthly_stack", "fig2b"),
    ("图3a", "四个指定日期的储电量轨迹", "fig3a_soc_trajectory", "fig3a"),
    ("图3b", "储电量分布与充放电量分布", "fig3b_soc_hist", "fig3b"),
    ("图4a", "预测误差日内分布与逐月 MAE", "fig4a_forecast_error", "fig4a"),
    ("图4b", "紧急购电量的电价档与时段分布", "fig4b_emergency_cost_band", "fig4b"),
    ("图5", "费用构成与终端储电价值敏感性", "fig5_strategy_compare", "fig5"),
]
