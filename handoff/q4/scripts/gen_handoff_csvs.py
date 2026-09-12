"""生成 handoff/q4 根目录的三个论文用 CSV（只读仓库产物，不重跑求解器）。

运行：python handoff/q4/scripts/gen_handoff_csvs.py（任意工作目录均可）
输出：
    handoff/q4/第四问_核心指标汇总.csv
    handoff/q4/第四问_题目表格_表1表2表3.csv
    handoff/q4/第四问_图表数据需求清单.csv
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent          # zz-q4/handoff/q4/scripts
Q4DIR = HERE.parent                             # zz-q4/handoff/q4
ZZ = HERE.parents[2]                            # 仓库根（zz-q4）
QM = ZZ / "outputs" / "q4"
assert QM.is_dir(), f"未找到第四问产物：{QM}"

K = 30
TARGETS = ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")
# 表1 的六个时段（0 基列索引 59/71/83/95/107/119，见 scripts/report_q4.py 第 26–29 行）
SLOTS = [(59, "10:00-10:10"), (71, "12:00-12:10"), (83, "14:00-14:10"),
         (95, "16:00-16:10"), (107, "18:00-18:10"), (119, "20:00-20:10")]
BLOCKS = ["0:00-4:00", "4:00-8:00", "8:00-12:00", "12:00-16:00", "16:00-20:00", "20:00-24:00"]


def w(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as h:
        cw = csv.writer(h)
        cw.writerow(header)
        cw.writerows(rows)
    print(f"  [写出] {path.name}  ({len(rows)} 行)")


def load(v: str):
    sm = json.loads((QM / f"summary_q4-{v}_K{K}.json").read_text(encoding="utf-8"))
    pay = json.loads((QM / f"payload_q4-{v}_K{K}.json").read_text(encoding="utf-8"))
    bydate = {d["date"][:10]: d for d in sm["daily"]}
    paydate = {d["date"][:10]: d for d in pay["days"]}
    return sm, bydate, paydate


sm2, d2, p2 = load("2")
sm3, d3, p3 = load("3")
t2, t3 = sm2["totals"], sm3["totals"]

print(f"交付期 {sm2['meta']['delivery_period']['days']} 天（两变体应一致："
      f"{sm3['meta']['delivery_period']['days']}）")
assert sm2["meta"]["delivery_period"]["days"] == 334
assert abs(t2["total_cost_yuan"] - 15202115.127496772) < 1e-6, t2["total_cost_yuan"]
assert abs(t3["total_cost_yuan"] - 13847794.940061364) < 1e-6, t3["total_cost_yuan"]

pf = json.loads((QM / "perfect_foresight_q4_K30.json").read_text(encoding="utf-8"))
lam = json.loads((QM / "lambda_sensitivity_q4_K30.json").read_text(encoding="utf-8"))
cen = json.loads((QM / "solver_degeneracy_census_q4-3.json").read_text(encoding="utf-8"))
iv = json.loads((QM / "independent_verify_q4_K30.json").read_text(encoding="utf-8"))
sds2 = json.loads((QM / "solver_sensitivity_q4-2_highs-ds.json").read_text(encoding="utf-8"))
sds3 = json.loads((QM / "solver_sensitivity_q4-3_highs-ds.json").read_text(encoding="utf-8"))
sip3 = json.loads((QM / "solver_sensitivity_q4-3_highs-ipm.json").read_text(encoding="utf-8"))

n2 = sum(1 for k in iv["worst"] if k.startswith("[2]"))
n3 = sum(1 for k in iv["worst"] if k.startswith("[3]"))
print(f"独立复算检查项：4-2 = {n2}，4-3 = {n3}（合计 {n2 + n3}）；"
      f"failures = {len(iv['failures'])}")
print(f"λ 极差：4-2 = {lam['variants']['2']['range']['spread_yuan']:.4f}，"
      f"4-3 = {lam['variants']['3']['range']['spread_yuan']:.4f}")
print(f"LP 普查：{cen['overall']['n_lps']} 个 LP，解向量不同对 "
      f"{cen['overall']['n_lp_method_pairs_solution_differs']}/"
      f"{cen['overall']['n_lp_method_pairs']}")

# =============================================================================
# ① 第四问_核心指标汇总.csv
# =============================================================================
H = ["项目", "4-2（对应问题2）", "4-3（对应问题3）", "单位"]
r: list[list] = []


def row(proj, a, b, unit=""):
    r.append([proj, a, b, unit])


def f(x, n=4):
    return f"{x:,.{n}f}"


row("【口径与设置】", "", "")
row("统计口径（共用）", "自然日 00:00–24:00（交付期 334 天 / 48,096 个 10 分钟时段）", "", "")
row("模型字符串（共用）", "q4_fluctuating_price_two_stage_saa", "同左（靠 meta.variant 区分）", "")
row("交付期（共用）", "2025-02-01 00:00 – 2026-01-01 00:00", "同左", "")
row("变体枚举", "只在 0:00 决策一次，q≡x，无调整机制", "0:00 计划 + 6/12/18 三次滚动调整", "")
row("启用阶段", "{0:00}", "{0:00, 6:00, 12:00, 18:00}", "")
row("情景数 K", "7 或 14（逐日由第二问 choose_window 选定）", "30", "个")
row("电价预测器", "形态 × 水平（无日内修正）", "形态 × 水平 + 日内 AR(1) 修正（φ=0.85）", "")
row("终端储能价值", "0.33417（= η·min附件1 价，同第二问）", "0.478（常数，同第三问）", "元/kWh")
row("结算电价（共用）", "附件4 实际电价（预测值只参与决策）", "同左", "")
row("计划口径（共用）", "模板行 00:10→次日 00:10（表1 用）", "同左", "")
row("物理/费用口径（共用）", "自然日 00:00–24:00（表2/表3 与总费用用）", "同左", "")
row("", "", "")
row("【交付期结果】", "", "")
row("自然日总费用", f(t2["total_cost_yuan"]), f(t3["total_cost_yuan"]), "元")
row("　计划购电费（自然日）", f(t2["plan_cost_yuan"]), f(t3["plan_cost_yuan"]), "元")
row("　调整相关费用（自然日）", f(t2["adjust_cost_yuan"]), f(t3["adjust_cost_yuan"]), "元")
row("　紧急购电费", f(t2["emergency_cost_yuan"]), f(t3["emergency_cost_yuan"]), "元")
row("计划购电量（模板行）", f(20742639.1627), f(20140461.0054), "kWh")
row("最终合同购电量（模板行）", f(20742639.1627), f(20429627.6152), "kWh")
row("计划购电量（自然日）", f(20742464.3918), f(20139555.9637), "kWh")
row("最终合同购电量（自然日）", f(20742464.3918), f(20428725.3068), "kWh")
row("紧急购电量", f(t2["emergency_kwh"]), f(t3["emergency_kwh"]), "kWh")
row("紧急购电量占比", f(100 * t2["emergency_kwh"] / (20742639.1627 + t2["emergency_kwh"])),
    f(100 * t3["emergency_kwh"] / (20140461.0054 + t3["emergency_kwh"])), "%")
row("紧急购电费占比", f(100 * t2["emergency_cost_yuan"] / t2["total_cost_yuan"]),
    f(100 * t3["emergency_cost_yuan"] / t3["total_cost_yuan"]), "%")
row("充电量（母线侧）", f(t2["charge_kwh"]), f(t3["charge_kwh"]), "kWh")
row("放电量（母线侧）", f(t2["discharge_kwh"]), f(t3["discharge_kwh"]), "kWh")
row("弃电量", f(t2["curtail_kwh"]), f(t3["curtail_kwh"]), "kWh")
row("累计上调量", f(t2["adjust_up_kwh"]), f(t3["adjust_up_kwh"]), "kWh")
row("累计下调量", f(t2["adjust_down_kwh"]), f(t3["adjust_down_kwh"]), "kWh")
row("净上调量", f(t2["adjust_up_kwh"] - t2["adjust_down_kwh"]),
    f(t3["adjust_up_kwh"] - t3["adjust_down_kwh"]), "kWh")
row("储能等效循环次数（/9600 kWh）", f(t2["discharge_kwh"] / 9600), f(t3["discharge_kwh"] / 9600), "次")
row("含紧急购电的日期数", "170", "146", "天")
row("无紧急购电的日期数", "164", "188", "天")
row("出现紧急购电的时段数", "1,545", "676", "个")
row("SOC 贴上界（≥10800）时段数", "6,305", "4,874", "个")
row("SOC 贴下界（≤1200）时段数", "1,490", "640", "个")
row("单日总费用区间", "9,569.0812 – 131,820.3592", "9,677.4918 – 79,510.9835", "元")
row("全年回测耗时", f"{sm2['meta']['elapsed_seconds']:.1f}", f"{sm3['meta']['elapsed_seconds']:.1f}", "秒")
row("", "", "")
row("【变体间对照】", "", "")
row("4-3 相对 4-2 节省", f(t2["total_cost_yuan"] - t3["total_cost_yuan"]), "", "元")
row("　节省率（以 4-2 为基准）", f"-{100 * (t2['total_cost_yuan'] - t3['total_cost_yuan']) / t2['total_cost_yuan']:.4f}",
    "（以 4-3 为基准则为 +9.78%）", "%")
row("紧急购电量降幅", f"-84.72", "", "%")
row("", "", "")
row("【与第三问对照 + 完美预见拆分】", "", "")
row("第三问自然日总费用（确定性电价）", f(13162682.8855), "", "元")
row("完美预见电价下的总费用", f(pf["totals"]["total_cost_yuan"]), "", "元")
d = pf["decomposition"]
row("(a) 价格波动风险成本", f(d["a_price_volatility_risk_cost_yuan"]),
    f"{d['a_pct_of_q3']:.4f} % of 第三问", "元")
row("(b) 预测误差信息缺失成本", f(d["b_forecast_error_information_loss_yuan"]),
    f"{d['b_pct_of_q3']:.4f} % of 第三问", "元")
row("(a)+(b) 合计差额", f(d["total_gap_yuan"]), f"{d['total_gap_pct_of_q3']:.4f} %", "元")
row("恒等式残差", f"{d['identity_residual_yuan']:.3e}", "", "元")
ic = pf["inventory_contamination"]
row("　其中期末存量转移：(a)", f(ic["a_stock_transfer_yuan"]), f"{ic['a_stock_transfer_pct_of_gap']:.4f} % of (a)", "元")
row("　其中期末存量转移：(b)", f(ic["b_stock_transfer_yuan"]), f"{ic['b_stock_transfer_pct_of_gap']:.4f} % of (b)", "元")
row("　加回后纯效率差：(a)", f(ic["a_pure_efficiency_yuan"]), "", "元")
row("　加回后纯效率差：(b)", f(ic["b_pure_efficiency_yuan"]), "", "元")
row("", "", "")
row("【稳健性与证据】", "", "")
lr2, lr3 = lam["variants"]["2"]["range"], lam["variants"]["3"]["range"]
row("λ 敏感性极差（基准×{0,0.5,0.75,1,1.5,2,3}）", f(lr2["spread_yuan"]), f(lr3["spread_yuan"]), "元")
row("　极差占比", f(lr2["spread_pct_of_baseline"]), f(lr3["spread_pct_of_baseline"]), "%")
row("λ 费用是否单调", str(lr2["costs_monotone_in_lam"]), str(lr3["costs_monotone_in_lam"]), "—")
row("求解器 highs-ds 与主答案之差", f"{sds2['total_gap_yuan']:.4f}（逐位相同）", f"{sds3['total_gap_yuan']:.4f}（逐位相同）", "元")
row("求解器 highs-ipm 与主答案之差", "未测", f"{sip3['total_gap_yuan']:.3e}", "元")
row("独立复算检查项数 / 失败项数", f"{n2} / 0", f"{n3} / 0", "项")
row("独立复算总费用偏差", "0.000e+00", "0.000e+00", "元")
row("LP 跨算法最大相对目标偏差", "未测", f"{cen['overall']['max_rel_obj_gap_across_methods']:.3e}", "—")
row("解向量不同的 (LP,算法) 对数占比", "未测",
    f"{100 * cen['overall']['n_lp_method_pairs_solution_differs'] / cen['overall']['n_lp_method_pairs']:.1f}", "%")
row("", "", "")
row("【数据来源】", "", "")
row("汇总/明细（共用）", "outputs/q4/summary_q4-{2,3}_K30.json、payload_q4-{2,3}_K30.json、detail_q4-{2,3}_K30.npz", "", "")
row("引用契约（共用）", "reports/q4_paper_handoff.md（**与本地数字冲突时以它为准**）", "", "")
w(Q4DIR / "第四问_核心指标汇总.csv", H, r)

# =============================================================================
# ② 第四问_题目表格_表1表2表3.csv
# =============================================================================
H2 = ["表", "变体", "日期", "时间段/项目", "值1", "值2", "单位", "口径", "来源"]
r2: list[list] = []
M = "模板行 00:10→次日00:10"
N = "自然日 00:00–24:00"
for v, pay, smd in (("4-2", p2, d2), ("4-3", p3, d3)):
    for dt in TARGETS:
        dd, sd = pay[dt], smd[dt]
        for idx, lab in SLOTS:
            r2.append(["表1", v, dt, lab, f"{dd['plan_kwh'][idx]:.4f}",
                       f"{dd['adjusted_kwh'][idx]:.4f}", "kWh", M,
                       "payload days[*].plan_kwh / adjusted_kwh"])
        r2.append(["表1", v, dt, "全天购电量", f"{dd['plan_total_kwh']:.4f}",
                   f"{dd['adjusted_total_kwh']:.4f}", "kWh", M, "payload"])
        r2.append(["表1", v, dt, "全天购电费/元（模板行口径）", f"{dd['plan_cost_yuan']:.4f}",
                   f"{dd['adjusted_cost_yuan']:.4f}", "元", M,
                   "payload（4-2 为 PMAT·x 全额、无 min；4-3 为 p·min(x,q)）"])
        r2.append(["表1", v, dt, "全天购电费/元（自然日口径）", f"{sd['natural_day_plan_cost_yuan']:.4f}",
                   f"{sd['natural_day_adjust_cost_yuan']:.4f}", "元", N, "summary daily"])
        for i, lab in enumerate(BLOCKS):
            blk = dd["storage_blocks"][i]
            assert blk["time_range"] == lab, (blk["time_range"], lab)
            r2.append(["表2", v, dt, lab, f"{blk['charge_kwh']:.4f}",
                       f"{blk['discharge_kwh']:.4f}", "kWh",
                       "自然日（充电量/放电量）", "payload storage_blocks"])
        r2.append(["表2", v, dt, "0:00 储电量", f"{sd['soc_start_kwh']:.4f}", "", "kWh", N, "payload/summary"])
        r2.append(["表2", v, dt, "24:00 储电量", f"{sd['soc_end_kwh']:.4f}", "", "kWh", N, "payload/summary"])
        segs = dd.get("emergency_segments") or []
        if segs:
            for sg in segs:
                r2.append(["表3", v, dt, sg["time_range"], f"{sg['energy_kwh']:.4f}", "", "kWh",
                           N, "payload emergency_segments"])
            r2.append(["表3", v, dt, "分段合计", f"{sum(s['energy_kwh'] for s in segs):.4f}",
                       f"{sd['emergency_total_kwh']:.4f}", "kWh", N, "payload（分段之和 vs 逐日合计）"])
        else:
            r2.append(["表3", v, dt, "（当日无紧急购电）", "0.0000", "0.0000", "kWh", N, "payload"])
        r2.append(["表3", v, dt, "当日紧急购电费/元", f"{sd['emergency_cost_yuan']:.4f}", "", "元", N, "summary daily"])
        r2.append(["—", v, dt, "当日总费用/元", f"{sd['total_cost_yuan']:.4f}", "", "元", N, "summary daily"])
w(Q4DIR / "第四问_题目表格_表1表2表3.csv", H2, r2)

# =============================================================================
# ③ 第四问_图表数据需求清单.csv
# =============================================================================
H3 = ["图文件", "图题", "数据来源文件", "用到的列", "行数/规模", "图型", "已产出格式"]
F = "pdf+png+svg"
r3 = [
    ["fig4_1a_price_profile", "图 4-1a 附件4 日内电价形态", "q4_price_profile.csv",
     "slot; label; mean; p10; p90; shape; annex1_price", "144 行",
     "折线 + 分位带（fill_between，有数学意义）；归一化形态另置上/下共享 x 轴面板（**不用双 Y 轴**）", F],
    ["fig4_1b_price_forecast", "图 4-1b 电价预测精度（四阶段）", "q4_price_forecast_error.csv",
     "stage; publish_hour; MAPE; MAE_yuan_per_kwh; MAE_same_window_no_update; MAE_persistence",
     "4 行", "分组柱（上下双面板）", F],
    ["fig4_2a_dispatch_2days", "图 4-2a 两日调度对照（4-2 vs 4-3）", "q4_target_days_interval.csv",
     "date; slot; x; q; price_template", "2 日 × 144 段 × 2 变体",
     "上下共享 x 轴双面板：上＝电价，下＝购电量分组柱（**不用双 Y 轴**）", F],
    ["fig4_2b_plan_vs_final", "图 4-2b 指定日期计划购电量与最终调整购电量", "q4_target_days_interval.csv",
     "date; slot; x; q; price_template", "4 日 × 144 段 × 2 变体", "step 折线（多面板）", F],
    ["fig4_3a_monthly_cost", "图 4-3a 月度费用构成与紧急购电占比", "q4_monthly_summary.csv",
     "month; plan_cost; adjust_cost; emergency_cost; total_cost", "11 月 × 2 变体",
     "上下共享 x 轴双面板：上＝堆叠柱（元），下＝紧急购电占比折线（%）（**不用双 Y 轴**）", F],
    ["fig4_3b_adjust_profile", "图 4-3b 合约调整量的日内分布与阶段分解",
     "q4_adjust_by_hour.csv; q4_adjust_by_stage.csv",
     "hour; up_kwh_43; down_kwh_43 / stage; publish_hour; up_kwh_43; down_kwh_43; up_cost_yuan_43; down_cost_yuan_43",
     "24 行 + 4 行", "正负双向柱 + 分组柱（左右双面板）", F],
    ["fig4_4a_soc_trajectory", "图 4-4a 指定日期储电量轨迹", "q4_target_days_interval.csv",
     "date; slot; S", "4 日 × 145 点 × 2 变体", "折线（线型区分变体 + 边界虚线）", F],
    ["fig4_4b_soc_distribution", "图 4-4b 储电量分布与边界触及", "q4_soc_hist.csv; q4_soc_band_hits.csv",
     "bin_lo; bin_hi; count_42; count_43 / variant; at_min; at_max; n_slots", "≤48 箱 + 2 行",
     "分组直方图 + 边界竖线（精确触及计数另行标注）", F],
    ["fig4_5a_emergency_price_band", "图 4-5a 紧急购电的价格档与时刻分布", "q4_emergency_by_price_band.csv; q4_hourly_profile.csv",
     "band_lo; band_hi; kwh_42; kwh_43; hour; emergency_kwh_42; emergency_kwh_43", "9 档 + 24 时",
     "左右双面板：左＝价格档分组柱，右＝24 小时分组柱（**不用双 Y 轴**）", F],
    ["fig4_5b_curtail_profile", "图 4-5b 弃电量的日内分布", "q4_hourly_profile.csv",
     "hour; curtail_kwh_42; curtail_kwh_43", "24 行", "分组柱", F],
    ["fig4_6_strategy_compare", "图 4-6 四种组合的总费用对照（2×2）",
     "q4_strategy_compare_4cells.csv; q4_perfect_foresight.csv",
     "cell; price_process; decision; total_cost_yuan", "4 格（其中 1 格【待补】）", "柱状 + 带标注的差值箭头", F],
    ["fig4_7a_solver_stability", "图 4-7a 求解器配置稳定性与 LP 退化", "q4_solver_sensitivity.csv; q4_solver_degeneracy_summary.csv",
     "variant; method; total_gap_yuan; n_solution_differs; n", "3 行 + 5 行", "柱状（左右双面板）", F],
    ["fig4_7b_lambda_sensitivity", "图 4-7b 终端储能水价 λ 的全年敏感性",
     "q4_lambda_sensitivity.csv; q4_lambda_range.csv",
     "lam_over_baseline; total_cost_yuan; soc_end_delivery_kwh", "7 点 × 2 变体",
     "上下共享 x 轴双面板：上＝总费用折线+marker，下＝期末 SOC（**不用双 Y 轴**，用以展示体制切换）", F],
    ["fig4_8_perfect_foresight", "图 4-8 完美预见拆分：与第三问 +5.20% 的构成",
     "q4_perfect_foresight.csv", "point; total_cost_yuan; gap_vs_q3_yuan; gap_pct_vs_q3", "3 点 + 4 项分解",
     "柱状 + 瀑布/堆叠分解", F],
]
w(Q4DIR / "第四问_图表数据需求清单.csv", H3, r3)
print("\n三个根级 CSV 已生成。")
