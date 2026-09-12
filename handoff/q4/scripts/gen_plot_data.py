"""生成 handoff/q4/_figdata 的绘图数据（对齐仓库现行第四问产物，不重跑求解器）。

运行：python handoff/q4/scripts/gen_plot_data.py（任意工作目录均可）

数据源（只读）：zz-q4/outputs/q4/ 下的 summary/payload/detail/lambda/solver 系列产物
            + problem/data/附件1.xlsx、附件4.xlsx
            + docs/q4_model.md 第 57–62 行的预测误差表（产物中未落盘，脚本内硬编码誊抄）
输出：handoff/q4/_figdata/*.csv / *.json（共 18 个文件）

两个变体：
  variant "2" = 4-2，只在 0:00 决策一次（继承问题 2，q ≡ x，无调整机制）
  variant "3" = 4-3，0:00 计划 + 6/12/18 点三次滚动（继承问题 3）
两变体共用同一 model 字符串 "q4_fluctuating_price_two_stage_saa"，靠 meta["variant"] 区分。
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent          # zz-q4/handoff/q4/scripts
Q4DIR = HERE.parent                             # zz-q4/handoff/q4
ZZ = HERE.parents[2]                            # 仓库根（zz-q4）
QM = ZZ / "outputs" / "q4"
OUT = Q4DIR / "_figdata"
OUT.mkdir(parents=True, exist_ok=True)
assert (ZZ / "outputs").is_dir(), f"未找到仓库产物目录：{ZZ / 'outputs'}"
assert QM.is_dir(), f"未找到第四问产物：{QM}"

VARIANTS = ("2", "3")
T, DT = 144, 1.0 / 6.0
K = 30
TARGETS = ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")
# 交付期 = 2025-02-01 起 334 天；全年回测 365 天（1 月仅作预热）
DELIV  = ("2025-02-01", "2025-12-31")

# docs/q4_model.md 第 57–62 行的实测误差表（2025 年留出预热 30 天后）。
# 该表只存在于文档，产物里没有落盘，故硬编码誊抄；列含义见文件末尾说明。
#   stage, publish_hour, MAPE, MAE(元/kWh), 同一窗口下 0:00 版 MAE, 前一日持续 MAE
FORECAST_ERROR = [
    (0, 0,  13.2, 0.0799, 0.0799, 0.0846),   # 文档行 59
    (1, 6,   9.1, 0.0556, 0.0916, 0.0950),   # 文档行 60
    (2, 12, 11.6, 0.0837, 0.0865, 0.0892),   # 文档行 61
    (3, 18, 13.4, 0.0832, 0.0631, 0.0651),   # 文档行 62
]

# 问题 1/2/3 与 4-2 共用的储能/购电参数（与 src/q3_multistage.py 第 36–41 行一致）
ETA = 0.9
SMIN, SMAX = 1200.0, 10800.0
CMAX = 5000.0 * DT                              # 833.3333 kWh/时段（交流母线侧）


def w(name: str, header: list[str], rows: list[list]) -> None:
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as h:
        cw = csv.writer(h)
        cw.writerow(header)
        cw.writerows(rows)
    print(f"  [写出] {name}  ({len(rows)} 行)")


def r(v) -> str:
    """按 q3 模板的约定：数值一律 repr(float(v))，保留全精度，不做格式化截断。"""
    return repr(float(v))


# ---------------- 读入 ----------------
det = {v: np.load(QM / f"detail_q4-{v}_K{K}.npz") for v in VARIANTS}
pay = {v: json.loads((QM / f"payload_q4-{v}_K{K}.json").read_text(encoding="utf-8"))
       for v in VARIANTS}
sm = {v: json.loads((QM / f"summary_q4-{v}_K{K}.json").read_text(encoding="utf-8"))
      for v in VARIANTS}
tot = {v: sm[v]["meta"]["totals"] for v in VARIANTS}
days = {v: pay[v]["days"] for v in VARIANTS}              # 334 条，每条含 144 长数组
daily = {v: sm[v]["daily"] for v in VARIANTS}             # 334 条

dates = [str(d) for d in det["3"]["dates"]]               # 365 天
D0 = dates.index(DELIV[0])
sl = slice(D0, len(dates))                                # 交付期切片（334 天）
NDELIV = len(dates) - D0

x = {v: det[v]["x"][sl] for v in VARIANTS}
q = {v: det[v]["q"][sl] for v in VARIANTS}
cc = {v: det[v]["c"][sl] for v in VARIANTS}
gg = {v: det[v]["g"][sl] for v in VARIANTS}
zz_ = {v: det[v]["z"][sl] for v in VARIANTS}
ww = {v: det[v]["w"][sl] for v in VARIANTS}
nx = {v: det[v]["natural_x"][sl] for v in VARIANTS}
nq = {v: det[v]["natural_q"][sl] for v in VARIANTS}
SS = {v: det[v]["S"][sl] for v in VARIANTS}                # 145 列（第 0 列 = 当日起点）
S0s = {v: det[v]["S0"][sl] for v in VARIANTS}
PMAT = {v: det[v]["price"][sl] for v in VARIANTS}          # 交付期实际电价 334×144
PMAT_FULL = det["3"]["price"]                              # 全年 365×144

# 附件1：模板行 144 段（00:10–24:00）的确定性分时电价与冷启动负荷/光伏
a1 = pd.read_excel(ZZ / "problem" / "data" / "附件1.xlsx", header=0)
a1.columns = ["t", "p", "L", "G"]
P1 = a1.p.to_numpy(float)
L1 = a1.L.to_numpy(float)
G1 = a1.G.to_numpy(float)
price_nat = np.r_[P1[-1], P1[:-1]]          # 自然日价格向量（首段取模板行末列）

# 附件4：365×145（第 1 列日期，后 144 列电价），即 PMAT_FULL 的原始来源
a4 = pd.read_excel(ZZ / "problem" / "data" / "附件4.xlsx", header=0)
PM4 = a4.iloc[:, 1:].to_numpy(float)

lam = json.loads((QM / f"lambda_sensitivity_q4_K{K}.json").read_text(encoding="utf-8"))
pf = json.loads((QM / f"perfect_foresight_q4_K{K}.json").read_text(encoding="utf-8"))
iv = json.loads((QM / f"independent_verify_q4_K{K}.json").read_text(encoding="utf-8"))

print(f"交付期 {NDELIV} 天（{DELIV[0]} ~ {DELIV[1]}）；全年回测 {len(dates)} 天；"
      f"明细 {x['3'].shape}")

# ======================================================================
# 1) q4_meta.json —— 元信息（参数口径 + 两变体总费用 + 关键说明）
# ======================================================================
meta = {
    "model_shared": sm["3"]["meta"]["model"],
    "variant_note": "两变体共用同一 model 字符串，靠 variant 区分："
                    "variant='2' 为 4-2（仅 0:00 决策一次，q ≡ x），"
                    "variant='3' 为 4-3（0:00 计划 + 6/12/18 点三次滚动调整）",
    "variants": {
        "2": {"label": "4-2 波动电价 × 一次决策", "stages": sm["2"]["meta"]["stages"],
              "base_model": sm["2"]["meta"]["variant2_base_model"],
              "total_cost_yuan": tot["2"]["total_cost_yuan"],
              "elapsed_seconds": sm["2"]["meta"]["elapsed_seconds"]},
        "3": {"label": "4-3 波动电价 × 四阶段滚动", "stages": sm["3"]["meta"]["stages"],
              "total_cost_yuan": tot["3"]["total_cost_yuan"],
              "elapsed_seconds": sm["3"]["meta"]["elapsed_seconds"]},
    },
    "delivery_period": {"start": DELIV[0], "end": DELIV[1], "days": NDELIV,
                        "note": "交付期自 2025-02-01 起 334 天；全年回测 365 天，"
                                "2025 年 1 月仅作预热（附件2 缺 1/1 午夜负荷与光伏）"},
    "backtest_days": len(dates),
    "K": K,
    "S0": 6000.0,
    "eta": ETA,
    "S_max": SMAX,
    "S_min": SMIN,
    "C_max": CMAX,
    "interval_limit_kwh": sm["3"]["meta"]["interval_limit_kwh"],
    "soc_recursion": sm["3"]["meta"]["soc_recursion"],
    "storage_convention": sm["3"]["meta"]["storage_convention"],
    "plan_adjust_time_frame": sm["3"]["meta"]["plan_adjust_time_frame"],
    "physical_reporting_time_frame": sm["3"]["meta"]["physical_reporting_time_frame"],
    "settlement_price": sm["3"]["meta"]["settlement_price"],
    "lambda_baseline": {v: lam["meta"]["baseline_lam"][v] for v in VARIANTS},
    "totals": {v: {k: float(xv) for k, xv in tot[v].items()} for v in VARIANTS},
    "delivery_aggregates": {
        "d0_index_in_backtest": D0,
        "charge_kwh": {v: float(cc[v].sum()) for v in VARIANTS},
        "discharge_kwh": {v: float(gg[v].sum()) for v in VARIANTS},
        "emergency_kwh": {v: float(zz_[v].sum()) for v in VARIANTS},
        "curtail_kwh": {v: float(ww[v].sum()) for v in VARIANTS},
    },
    "price": {"annex1_mean_yuan_per_kwh": float(P1.mean()),
              "annex4_full_mean_yuan_per_kwh": float(PMAT_FULL.mean()),
              "annex4_delivery_mean_yuan_per_kwh": float(PMAT["3"].mean()),
              "annex4_min_yuan_per_kwh": float(PMAT_FULL.min()),
              "annex4_max_yuan_per_kwh": float(PMAT_FULL.max()),
              "per_slot_mean_max_abs_diff_vs_annex1": float(np.abs(PM4.mean(0) - P1).max())},
    "notes": [
        "payload 的 plan_cost_yuan / adjusted_cost_yuan 是【表1 模板行口径】；"
        "总费用与 natural_day_plan_cost_yuan + natural_day_adjust_cost_yuan + "
        "emergency_cost_yuan 是【自然日口径】，两者不同，不可混用。",
        "natural_x / natural_q 首段取【前一日模板行末段】（跨日右移），"
        "sum(natural_x) 与 sum(x) 相差当日末段购电量。",
        "SOC 轨迹 S 为自然日口径（S[:,0] = 当日 0:00 起点，等于 payload.soc_start_kwh），"
        "模板行与自然日在时段值上正好对齐。",
        "费用口径均为附件4 实际电价结算，预测值只参与决策、不参与结算。",
        "summary.daily 与 payload.days 两条日度序列逐字段完全一致（已核），可互替使用。",
        "solver_sensitivity 两变体的基准值就是交付版 highs 解，故 highs-ds 的 gap 恒为 0，"
        "真正外部的算法对照只有 4-3 的 highs-ipm。",
    ],
}
(OUT / "q4_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
print("  [写出] q4_meta.json")

# ======================================================================
# 2) q4_daily_metrics.csv —— 334 天 × 两变体（加 variant 列）
# 口径说明：payload 的 plan_cost_yuan / adjusted_cost_yuan 是【表1 模板行口径】，
#   而 total_cost_yuan 与三项之和是【自然日口径】，两者相差一个午夜列：
#     variant 2：Σplan_cost_yuan - Σnatural_day_plan_cost_yuan = +0.28 元
#     variant 3：Σplan_cost_yuan - Σnatural_day_plan_cost_yuan = +488.54 元
#   为免混用，本文件的费用列以【自然日口径】为准：
#     计划购电费 = natural_day_plan_cost_yuan，调整费 = natural_day_adjust_cost_yuan，
#     紧急费 = emergency_cost_yuan（本就是自然日口径），三者之和 = total_cost_yuan。
#   同时保留表1 模板行口径两列（plan_cost_yuan_template / adjust_cost_yuan_template），
#   供论文核表1 使用。
rows = []
for v in VARIANTS:
    for d in days[v]:
        rows.append([v, d["date"], r(d["plan_total_kwh"]), r(d["plan_cost_yuan"]),
                     r(d["adjusted_total_kwh"]), r(d["adjusted_cost_yuan"]),
                     r(d["emergency_total_kwh"]), r(d["emergency_cost_yuan"]),
                     r(d["total_cost_yuan"]), r(d["curtail_kwh"]),
                     r(d["adjust_up_kwh"]), r(d["adjust_down_kwh"]),
                     r(d["soc_start_kwh"]), r(d["soc_end_kwh"]),
                     r(d["natural_day_plan_cost_yuan"]), r(d["natural_day_adjust_cost_yuan"])])
w("q4_daily_metrics.csv",
  ["variant", "date", "plan_total_kwh", "plan_cost_yuan_template",
   "final_contract_total_kwh", "adjust_cost_yuan_template", "emergency_kwh",
   "emergency_cost_yuan", "total_cost_yuan", "curtail_kwh", "adjust_up_kwh",
   "adjust_down_kwh", "soc_start_kwh", "soc_end_kwh", "natural_day_plan_cost_yuan",
   "natural_day_adjust_cost_yuan"], rows)

# ======================================================================
# 3) q4_price_profile.csv —— 144 行模板时段的价格形态
# mean/p10/p50/p90/min/max 由附件4 全表 365×144 逐列统计；
# shape = 逐列均值 ÷ 全表均值（日内形态，供跨时段比较）；
# annex1_price = 附件1 电价列；slot_start_hhmm = 该模板行起点钟点（10 分钟粒度）。
pm_full = PMAT_FULL
mcol = pm_full.mean(axis=0)
gmean = float(pm_full.mean())
rows = []
for t in range(T):
    m = (t + 1) * 10
    rows.append([t, f"{m // 60}:{m % 60:02d}-{(m + 10) // 60}:{(m + 10) % 60:02d}",
                 f"{m // 60}:{m % 60:02d}",
                 r(mcol[t]), r(np.percentile(pm_full[:, t], 10)),
                 r(np.percentile(pm_full[:, t], 50)), r(np.percentile(pm_full[:, t], 90)),
                 r(pm_full[:, t].min()), r(pm_full[:, t].max()),
                 r(mcol[t] / gmean), r(P1[t])])
w("q4_price_profile.csv",
  ["slot", "label", "slot_start_hhmm", "mean", "p10", "p50", "p90", "min", "max",
   "shape", "annex1_price"], rows)

# ======================================================================
# 4) q4_price_statistics.csv —— 单行汇总（含附件1 vs 附件4 逐时段均值差）
# 断言：逐时段均值最大绝对差 < 1e-4（预期 ≈ 5.151e-05）
# ======================================================================
mad = float(np.abs(PM4.mean(axis=0) - P1).max())
mae_ = float(np.abs(PM4.mean(axis=0) - P1).mean())
assert mad < 1e-4, f"附件1 与附件4 逐时段均值最大绝对差过大：{mad!r}"
deliv_price = PMAT["3"]
rows = [[r(P1.min()), r(P1.max()), r(P1.mean()),
         r(deliv_price.min()), r(deliv_price.max()), r(deliv_price.mean()),
         r(pm_full.min()), r(pm_full.max()), r(pm_full.mean()),
         r(pm_full.mean(axis=1).min()), r(pm_full.mean(axis=1).max()),
         r(mad), r(mae_), NDELIV, len(dates)]]
w("q4_price_statistics.csv",
  ["annex1_min", "annex1_max", "annex1_mean",
   "delivery_min", "delivery_max", "delivery_mean",
   "fullyear_min", "fullyear_max", "fullyear_mean",
   "daily_mean_min", "daily_mean_max",
   "per_slot_mean_max_abs_diff_annex1_vs_annex4",
   "per_slot_mean_mean_abs_diff_annex1_vs_annex4",
   "delivery_days", "fullyear_days"], rows)

# ======================================================================
# 5) q4_price_forecast_error.csv —— 4 行（阶段 0/1/2/3）
# 【硬编码誊抄】来源：docs/q4_model.md 第 57–62 行的实测误差表（2025 年留出预热
#   30 天后）。这些数由 src 里的电价预测子模型评估产生，但【没有落盘到 outputs/】，
#   故只能从文档誉抄；若日后产物中新增该表，应改为读产物。
# ======================================================================
rows = [[st, ph, f"{mape:.1f}%", r(mae), r(same), r(pers)]
        for (st, ph, mape, mae, same, pers) in FORECAST_ERROR]
w("q4_price_forecast_error.csv",
  ["stage", "publish_hour", "MAPE", "MAE_yuan_per_kwh",
   "MAE_same_window_no_update", "MAE_persistence"], rows)

# ======================================================================
# 6) q4_target_days_interval.csv —— 4 个指定日期 × 144 段 × 两变体
# 口径：slot 为【模板行】（0:10–24:00 起算），natural_slot = (slot+1) mod 144，
#   clock 为模板行起点钟点，与附件1 的行序一致。
#   x/q/c/g/z/w 取模板行口径；natural_x/natural_q 首段取前一日末段（跨日右移）。
#   S 取该模板时段【结束】时的储电量（S[:,0]=0:00 起点=当日 soc_start）。
#   price_template = PMAT[d, slot]（模板行时段电价，即该行所属采样时刻的电价）；
#   price_natural = PMAT[d, natural_slot]（自然日对齐价，首段取前一日末段）。
# ======================================================================
rows = []
for v in VARIANTS:
    for dt in TARGETS:
        i = dates.index(dt) if dt in dates else None
        assert i is not None, f"指定日期不在明细日期轴内：{dt}"
        j = i - D0                                  # 交付期内的日序号
        assert 0 <= j < NDELIV, f"{dt} 不在交付期内"
        Prow = det[v]["price"][i]
        for t in range(T):
            m = (t + 1) * 10
            nt = (t + 1) % T
            rows.append([v, dt, t, nt, f"{m // 60}:{m % 60:02d}",
                         r(det[v]["x"][i, t]), r(det[v]["q"][i, t]),
                         r(det[v]["natural_x"][i, t]), r(det[v]["natural_q"][i, t]),
                         r(det[v]["c"][i, t]), r(det[v]["g"][i, t]),
                         r(det[v]["z"][i, t]), r(det[v]["w"][i, t]),
                         r(det[v]["S"][i, t + 1]),
                         r(Prow[t]), r(PMAT_FULL[i, nt] if t > 0 else det[v]["price"][i - 1, T - 1])])
w("q4_target_days_interval.csv",
  ["variant", "date", "slot", "natural_slot", "clock", "x", "q", "natural_x",
   "natural_q", "c", "g", "z", "w", "S", "price_template", "price_natural"], rows)

# ======================================================================
# 7) q4_monthly_summary.csv —— 11 个月（2025-02 ~ 2025-12）× 两变体
# 费用一律自然日口径：plan_cost = natural_day_plan_cost_yuan，
#   adjust_cost = natural_day_adjust_cost_yuan，两者 + emergency_cost = total_cost。
# ======================================================================
rows = []
for v in VARIANTS:
    mon = defaultdict(lambda: defaultdict(float))
    for d in days[v]:
        b = mon[d["date"][:7]]
        b["days"] += 1
        b["plan"] += d["plan_total_kwh"]
        b["contract"] += d["adjusted_total_kwh"]
        b["plan_cost"] += d["natural_day_plan_cost_yuan"]
        b["adjust_cost"] += d["natural_day_adjust_cost_yuan"]
        b["emg_kwh"] += d["emergency_total_kwh"]
        b["emg_cost"] += d["emergency_cost_yuan"]
        b["total"] += d["total_cost_yuan"]
        b["curtail"] += d["curtail_kwh"]
    for mth, b in sorted(mon.items()):
        rows.append([v, mth, int(b["days"]), r(b["plan"]), r(b["contract"]),
                     r(b["plan_cost"]), r(b["adjust_cost"]), r(b["emg_kwh"]),
                     r(b["emg_cost"]), r(b["total"]), r(b["curtail"])])
w("q4_monthly_summary.csv",
  ["variant", "month", "days", "plan_kwh", "contract_kwh", "plan_cost", "adjust_cost",
   "emergency_kwh", "emergency_cost", "total_cost", "curtail_kwh"], rows)

# ======================================================================
# 8) q4_hourly_profile.csv —— 24 行（自然日小时 0:00–24:00）
# 小时 = 6 个 10 分钟时段；price_mean 取自然日小时的第 1 个时段电价（与 q3 一致）；
#   net_load_kwh = Σ_t (L1[t] - G1[t])·DT（附件1 的日净负荷，逐日相同）。
# ======================================================================
phour = np.tile(price_nat, (PMAT_FULL.shape[0], 1))
rows = []
for h in range(24):
    t0 = h * 6
    rec = [h, r(phour[:, t0].mean())]
    for v in VARIANTS:
        rec.append(r(zz_[v][:, t0:t0 + 6].sum()))
    for v in VARIANTS:
        rec.append(r(cc[v][:, t0:t0 + 6].sum()))
    for v in VARIANTS:
        rec.append(r(gg[v][:, t0:t0 + 6].sum()))
    for v in VARIANTS:
        rec.append(r(ww[v][:, t0:t0 + 6].sum()))
    rec.append(r(float(np.sum((L1[t0:t0 + 6] - G1[t0:t0 + 6]) * DT))))
    rows.append(rec)
w("q4_hourly_profile.csv",
  ["hour", "price_mean", "emergency_kwh_42", "emergency_kwh_43", "charge_kwh_42",
   "charge_kwh_43", "discharge_kwh_42", "discharge_kwh_43", "curtail_kwh_42",
   "curtail_kwh_43", "net_load_kwh"], rows)

# ======================================================================
# 9) q4_emergency_by_price_band.csv —— 电价档归因（档宽 0.2 元/kWh，0 → 1.8）
# 只输出非空档（最后一档含上边界 1.7936）；价格取该时段【实际电价】（结算口径）。
# 紧急购电费按结算式 C = 5·p·z 计算（5 为惩罚倍数）。
# ======================================================================
rows = []
for b0 in np.arange(0.0, 1.8, 0.2):
    b1 = b0 + 0.2
    if b1 >= 1.8:
        m = (PMAT["3"] >= b0) & (PMAT["3"] <= b1 + 1e-12)
    else:
        m = (PMAT["3"] >= b0) & (PMAT["3"] < b1)
    if not m.any():
        continue
    rec = [f"{b0:.1f}", f"{b1:.1f}", int(m.sum())]
    for v in VARIANTS:
        rec.append(int((zz_[v][m] > 1e-9).sum()))
    for v in VARIANTS:
        rec.append(r(zz_[v][m].sum()))
    for v in VARIANTS:
        rec.append(r(float((5.0 * PMAT[v][m] * zz_[v][m]).sum())))
    rows.append(rec)
w("q4_emergency_by_price_band.csv",
  ["band_lo", "band_hi", "slots", "intervals_42", "intervals_43", "kwh_42", "kwh_43",
   "cost_42", "cost_43"], rows)

# ======================================================================
# 10) q4_soc_hist.csv —— 储电量分箱（箱宽 200 kWh，1200–10800，共 48 箱）
# 口径：交付期逐时段【结束】储电量 S[:,1:]，两变体各自统计。
# ======================================================================
NB = int(round((SMAX - SMIN) / 200.0))              # 48
soc_idx = {}
for v in VARIANTS:
    s = SS[v][:, 1:].ravel()
    soc_idx[v] = np.clip(((s - SMIN) // 200.0).astype(int), 0, NB - 1)
rows = []
for b in range(NB):
    b0 = SMIN + 200.0 * b
    b1 = b0 + 200.0
    rec = [f"{b0:.1f}", f"{b1:.1f}"]
    for v in VARIANTS:
        rec.append(int((soc_idx[v] == b).sum()))
    rows.append(rec)
w("q4_soc_hist.csv", ["bin_lo", "bin_hi", "count_42", "count_43"], rows)

# ======================================================================
# 11) q4_charge_discharge_hist.csv —— 充/放电量分箱（箱宽 25 kWh，0–833.3333）
# 上限 CMAX = 833.3333 kWh/时段 归入最后一箱（并箱处理）。
# ======================================================================
NCB = int(np.ceil(CMAX / 25.0))                     # 34
rows = []
for b in range(NCB):
    b0 = 25.0 * b
    b1 = b0 + 25.0
    rec = [f"{b0:.4f}", f"{b1:.4f}"]
    for v in VARIANTS:
        arr = cc[v].ravel()
        idx = np.clip((arr / 25.0).astype(int), 0, NCB - 1)
        rec.append(int(((idx == b) & (arr > 1e-9)).sum()))
    for v in VARIANTS:
        arr = gg[v].ravel()
        idx = np.clip((arr / 25.0).astype(int), 0, NCB - 1)
        rec.append(int(((idx == b) & (arr > 1e-9)).sum()))
    rows.append(rec)
w("q4_charge_discharge_hist.csv",
  ["bin_lo", "bin_hi", "charge_count_42", "charge_count_43",
   "discharge_count_42", "discharge_count_43"], rows)

# ======================================================================
# 12) q4_strategy_compare_4cells.csv —— 2×2 策略对照（4 行）
# ① 确定电价 × 一次决策 = 【待补】，素材在第二问包 §D1，本脚本不补数（占位空值）；
# ② 确定电价 × 四阶段滚动 = 第三问主答案（solver_sensitivity 参考值 / summary totals）；
# ③ 波动电价 × 一次决策 = 4-2；④ 波动电价 × 四阶段滚动 = 4-3。
# ======================================================================
q3_total = pf["decomposition"]["c_q3_deterministic_price_known_yuan"]
rows = [
    ["确定电价×一次决策", "deterministic", "known", "once", "",
     "", "【待补：见第二问素材包 §D1】"],
    ["确定电价×四阶段滚动", "deterministic", "known", "four_stage_rolling",
     r(q3_total), "", "docs/q3_model.md + handoff/q3/_figdata/q3_meta.json（第三问主答案）"],
    ["波动电价×一次决策", "volatile_attachment4", "forecast", "once",
     r(tot["2"]["total_cost_yuan"]), r(tot["2"]["emergency_kwh"]),
     "outputs/q4/summary_q4-2_K30.json#meta.totals"],
    ["波动电价×四阶段滚动", "volatile_attachment4", "forecast", "four_stage_rolling",
     r(tot["3"]["total_cost_yuan"]), r(tot["3"]["emergency_kwh"]),
     "outputs/q4/summary_q4-3_K30.json#meta.totals"],
]
w("q4_strategy_compare_4cells.csv",
  ["cell", "price_process", "price_known", "decision", "total_cost_yuan",
   "emergency_kwh", "source"], rows)

# ======================================================================
# 13) q4_perfect_foresight.csv —— 3 行对照 + 4 行分解（用 kind 区分）
# 分解口径：a = 电价波动风险（确定已知 → 波动已知），b = 预测误差信息损失
#   （波动已知 → 波动预测），两者之和 = 第三问 → 4-3 的总差；
#   a_stock_transfer / b_stock_transfer 为终端储电量估值污染项（λ = 0.478 计价），
#   a_pure_efficiency = a - a_stock_transfer，b_pure_efficiency 同理。
# ======================================================================
dc = pf["decomposition"]
ic = pf["inventory_contamination"]
d_ = dc
A, B = d_["a_price_volatility_risk_cost_yuan"], d_["b_forecast_error_information_loss_yuan"]
# 公共列尾（5 个分解量）：point 行留空，分解行按行填写
CARRY = [r(A), r(B), r(d_["total_gap_yuan"]), r(d_["identity_residual_yuan"]),
         r(ic["a_stock_transfer_yuan"]), r(ic["b_stock_transfer_yuan"])]
BLANK = ["", "", "", "", "", ""]
rows = [
    ["point", "第三问", "deterministic", "known",
     r(d_["c_q3_deterministic_price_known_yuan"]), "0.0", "0.0000000000",
     "", ""] + BLANK,
    ["point", "完美预见", "volatile_attachment4", "known",
     r(d_["c_q4_PF_volatile_price_known_yuan"]),
     r(d_["c_q4_PF_volatile_price_known_yuan"] - d_["c_q3_deterministic_price_known_yuan"]),
     f'{d_["a_pct_of_q3"]:+.4f}', "", ""] + BLANK,
    ["point", "4-3", "volatile_attachment4", "forecast",
     r(d_["c_q4_3_volatile_price_forecast_yuan"]), r(d_["total_gap_yuan"]),
     f'{d_["total_gap_pct_of_q3"]:+.4f}', "", ""] + BLANK,
    ["decomposition", "a 电价波动风险", "deterministic->volatile", "known",
     "0.0", r(A), f'{d_["a_pct_of_q3"]:+.4f}', r(A), ""] + CARRY,
    ["decomposition", "b 预测误差信息损失", "volatile: known->forecast", "forecast",
     "0.0", r(B), f'{d_["b_pct_of_q3"]:+.4f}', "", r(B)] + CARRY,
    ["decomposition", "a 纯效率（剔库存转移）", "deterministic->volatile", "known",
     "0.0", r(ic["a_pure_efficiency_yuan"]),
     f'{ic["a_pure_efficiency_yuan"] / q3_total * 100.0:+.4f}',
     r(ic["a_pure_efficiency_yuan"]), ""] + CARRY,
    ["decomposition", "b 纯效率（剔库存转移）", "volatile: known->forecast", "forecast",
     "0.0", r(ic["b_pure_efficiency_yuan"]),
     f'{ic["b_pure_efficiency_yuan"] / q3_total * 100.0:+.4f}',
     "", r(ic["b_pure_efficiency_yuan"])] + CARRY,
]
w("q4_perfect_foresight.csv",
  ["kind", "point", "price_process", "price_known", "total_cost_yuan",
   "gap_vs_q3_yuan", "gap_pct_vs_q3", "a_pure_efficiency_yuan", "b_pure_efficiency_yuan",
   "a_volatility_risk_yuan", "b_forecast_error_yuan",
   "total_gap_yuan", "identity_residual_yuan", "a_stock_transfer_yuan",
   "b_stock_transfer_yuan"], rows)

# ======================================================================
# 14) q4_lambda_sensitivity.csv —— 两变体 × 7 点 = 14 行
# at_min / at_max = 交付期内 SOC 触及下限/上限的时段数（soc_band_hits_delivery）。
# ======================================================================
rows = []
for v in VARIANTS:
    for rec in lam["variants"][v]["scan"]:
        hits = rec["soc_band_hits_delivery"]
        rows.append([v, r(rec["lam"]), r(rec["lam_over_baseline"]), r(rec["total_cost_yuan"]),
                     r(rec["delta_vs_baseline_yuan"]), r(rec["delta_pct"]),
                     r(rec["emergency_kwh"]), r(rec["charge_kwh"]), r(rec["discharge_kwh"]),
                     r(rec["curtail_kwh"]), r(rec["soc_end_delivery_kwh"]),
                     int(hits["at_min"]), int(hits["at_max"])])
w("q4_lambda_sensitivity.csv",
  ["variant", "lam", "lam_over_baseline", "total_cost_yuan", "delta_vs_baseline_yuan",
   "delta_pct", "emergency_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh",
   "soc_end_delivery_kwh", "at_min", "at_max"], rows)

# ======================================================================
# 15) q4_lambda_range.csv —— 每变体 1 行（最低/最高费用点与摆幅）
# ======================================================================
rows = []
for v in VARIANTS:
    rg = lam["variants"][v]["range"]
    rows.append([v, r(lam["meta"]["baseline_lam"][v]), r(rg["spread_yuan"]),
                 r(rg["spread_pct_of_baseline"]), r(rg["min_cost"]["lam"]),
                 r(rg["max_cost"]["lam"]),
                 str(bool(rg["costs_monotone_in_lam"]))])
w("q4_lambda_range.csv",
  ["variant", "baseline_lam", "spread_yuan", "spread_pct_of_baseline", "min_lam",
   "max_lam", "costs_monotone_in_lam"], rows)

# ======================================================================
# 16) q4_solver_sensitivity.csv —— 3 行（主答案 + 两个替代算法点）
# 参考值 = 交付版 summary 的总费用；alt = 换算法重算的总费用。
# ======================================================================
rows = [[v, "highs（主答案）", r(tot[v]["total_cost_yuan"]), r(tot[v]["total_cost_yuan"]),
         "0.000000", "0.000000", "0.000000", 0, r(sm[v]["meta"]["elapsed_seconds"])]
        for v in VARIANTS]
for fname in ("solver_sensitivity_q4-2_highs-ds.json",
              "solver_sensitivity_q4-3_highs-ds.json",
              "solver_sensitivity_q4-3_highs-ipm.json"):
    s = json.loads((QM / fname).read_text(encoding="utf-8"))
    rows.append([s["variant"], s["method"], r(s["reference_total_cost_yuan"]),
                 r(s["alt_total_cost_yuan"]), r(s["total_gap_yuan"]),
                 r(s["total_gap_pct"]), r(s["max_abs_daily_gap_yuan"]),
                 int(s["days_with_gap_over_1yuan"]), r(s["elapsed_seconds"])])
w("q4_solver_sensitivity.csv",
  ["variant", "method", "reference_total_cost_yuan", "alt_total_cost_yuan",
   "total_gap_yuan", "total_gap_pct", "max_abs_daily_gap_yuan",
   "days_with_gap_over_1yuan", "elapsed_seconds"], rows)

# ======================================================================
# 17) q4_solver_degeneracy_summary.csv —— 4 阶段 × 2 方法 = 8 行 + 1 行 overall
# scope=stageX 行的度量相对 highs-ds（基准，其自身偏差恒为 0，故不单列）；
#   highs-ipm 行 = 内点法与对偶单纯形法的比较，jitter 行 = 目标系数 ±1e-7 相对抖动。
# overall 行只填可汇总项：n = n_lps，max_rel_obj_gap = 跨算法最大相对目标偏差，
#   n_solution_differs = (LP,算法) 解向量不同的对数，max_sol_diff 空；
#   jitter_* 三项写在行尾专属列。
# ======================================================================
cen = json.loads((QM / "solver_degeneracy_census_q4-3.json").read_text(encoding="utf-8"))
by_stage = cen["by_stage"]


def _stage_key(k: str) -> int:
    """stageN 或 stageN-N → 起始阶段序号 N。"""
    body = k[5:]
    return int(body.split("-")[0])


rows = []
for sk in sorted(by_stage, key=_stage_key):
    blk = by_stage[sk]
    for method in ("highs-ipm", "jitter"):
        m = blk[method]
        n = int(m["n"] if "n" in m else m["solvable"])
        rows.append([sk, method, n, r(m["max_rel_obj_gap"]),
                     int(m.get("n_obj_gap_gt_1e-9", 0)), int(m.get("n_obj_gap_gt_1e-6", 0)),
                     int(m["n_solution_differs"]), r(m["max_sol_diff"]),
                     "", "", "", ""])
ov = cen["overall"]
rows.append(["overall", "cross-method", int(ov["n_lps"]),
             r(ov["max_rel_obj_gap_across_methods"]), int(ov["n_lps_obj_gap_gt_1e-9"]),
             int(ov["n_lps_obj_gap_gt_1e-6"]), int(ov["n_lp_method_pairs_solution_differs"]),
             "", r(ov["jitter_max_rel_obj_gap"]), int(ov["jitter_n_solution_differs"]),
             int(ov["jitter_n"]), r(cen["jitter_rel"])])
w("q4_solver_degeneracy_summary.csv",
  ["scope", "method", "n", "max_rel_obj_gap", "n_obj_gap_gt_1e-9", "n_obj_gap_gt_1e-6",
   "n_solution_differs", "max_sol_diff", "jitter_max_rel_obj_gap",
   "jitter_n_solution_differs", "jitter_n", "jitter_rel"], rows)

# ======================================================================
# 18) q4_independent_verify.csv —— 把 worst 字典展平成行
# 尾部另附三条汇总信息（check 名固定），failures_count 为独立验收的失败检查数。
# ======================================================================
worst = iv["worst"]
rows = [[k, r(val)] for k, val in worst.items()]
rows.append(["failures_count", str(len(iv["failures"]))])
rows.append(["checks_count", str(len(worst))])
rows.append(["realtime_replay_covered", "|".join(str(s) for s in iv["realtime_replay_covered"])])
w("q4_independent_verify.csv", ["check", "max_abs_deviation"], rows)

# ======================================================================
# 自检汇总（任一断言不成立直接 raise）
# ======================================================================
print("\n" + "=" * 68)
print("自检汇总")
print("=" * 68)

# (1) 交付期天数 = 334
assert NDELIV == 334, f"交付期天数应为 334，实际 {NDELIV}"
assert len(days["2"]) == 334 and len(days["3"]) == 334, "payload 天数不是 334"
print(f"[1] 交付期天数 = {NDELIV}（{DELIV[0]} ~ {DELIV[1]}），"
      f"全年回测 {len(dates)} 天，1 月预热 {D0} 天  ✓")

# (2) 两变体总费用对上给定值
EXPECT = {"2": 15202115.1275, "3": 13847794.9401}
for v in VARIANTS:
    got = float(tot[v]["total_cost_yuan"])
    assert abs(got - EXPECT[v]) < 1e-3, f"variant {v} 总费用 {got!r} 未对上 {EXPECT[v]}"
    ssum = sum(float(d["total_cost_yuan"]) for d in days[v])
    assert abs(ssum - got) < 1e-6, f"variant {v} 逐日总费用之和 {ssum!r} ≠ totals {got!r}"
    comp = (sum(float(d["natural_day_plan_cost_yuan"]) for d in days[v])
            + sum(float(d["natural_day_adjust_cost_yuan"]) for d in days[v])
            + tot[v]["emergency_cost_yuan"])
    assert abs(comp - got) < 1e-4, f"variant {v} 三项之和 {comp!r} ≠ 总费用 {got!r}"
    print(f"[2] variant {v} 总费用 = {got:.4f} 元（逐日和 {ssum:.4f}，"
          f"计划+调整+紧急 {comp:.4f}）  ✓")
d_tpl = {v: sum(float(d["plan_cost_yuan"]) for d in days[v])
            - sum(float(d["natural_day_plan_cost_yuan"]) for d in days[v]) for v in VARIANTS}
a_tpl = {v: sum(float(d["adjusted_cost_yuan"]) for d in days[v])
            - sum(float(d["natural_day_adjust_cost_yuan"]) for d in days[v]) for v in VARIANTS}
for v in VARIANTS:
    assert a_tpl[v] < 1.0, f"variant {v} 调整费两口径差 {a_tpl[v]!r} 异常"
    # 自然日口径三项之和必须精确等于总费用（本脚本取数前提，必须成立）
    assert abs(sum(float(d["natural_day_plan_cost_yuan"]) for d in days[v])
               + sum(float(d["natural_day_adjust_cost_yuan"]) for d in days[v])
               + float(tot[v]["emergency_cost_yuan"])
               - float(tot[v]["total_cost_yuan"])) < 5e-4, \
        f"variant {v} 自然日三项之和 ≠ 总费用"
print(f"    表1 模板行口径 vs 自然日口径（仅计划购电费一项）：v2 差 {d_tpl['2']:+.2f} 元、"
      f"v3 差 {d_tpl['3']:+.2f} 元；调整费两口径差 v2 {a_tpl['2']:+.2f}、v3 {a_tpl['3']:+.2f} 元"
      f"——plan/adjust 的模板行口径之和 Σ(计划+调整) 仍等于 totals 的 plan+adjust，"
      f"但单项不可直接与自然日口径混用，CSV 中已分列")

# (3) 附件1 与附件4 逐时段均值最大差 ≈ 5.151e-05
assert abs(mad - 5.150684931509719e-05) < 1e-9, f"最大差 {mad!r} 与预期不符"
assert mad < 1e-4, f"最大差 {mad!r} ≥ 1e-4"
print(f"[3] 附件1 vs 附件4 逐时段均值最大绝对差 = {mad:.6e}（预期 ≈ 5.151e-05），"
      f"平均绝对差 = {mae_:.6e}  ✓")

# (4) 两变体同时充放电时段数 = 0
for v in VARIANTS:
    nsim = int(((cc[v] > 1e-9) & (gg[v] > 1e-9)).sum())
    assert nsim == 0, f"variant {v} 存在 {nsim} 个同时充放电时段"
    print(f"[4] variant {v} 同时充放电时段数 = {nsim}  ✓")

# (5) 附加一致性核验
for v in VARIANTS:
    assert abs(float(cc[v].sum()) - tot[v]["charge_kwh"]) < 1e-6
    assert abs(float(gg[v].sum()) - tot[v]["discharge_kwh"]) < 1e-6
    assert abs(float(zz_[v].sum()) - tot[v]["emergency_kwh"]) < 1e-6
    assert abs(float(ww[v].sum()) - tot[v]["curtail_kwh"]) < 1e-6
    assert SS[v].min() >= SMIN - 1e-9 and SS[v].max() <= SMAX + 1e-9
    assert float(cc[v].max()) <= CMAX + 1e-9 and float(gg[v].max()) <= CMAX + 1e-9
print("[5] 两变体 delivery 期 Σc/Σg/Σz/Σw 与 totals 一致；"
      f"SOC ∈ [{min(SS[v].min() for v in VARIANTS):.1f}, "
      f"{max(SS[v].max() for v in VARIANTS):.1f}]，C ≤ {CMAX:.4f}  ✓")
assert float(np.abs(PMAT["3"] - PM4[D0:]).max()) == 0.0, "npz.price 与附件4 交付期不一致"
print("[6] npz.price 交付期与附件4 逐段一致（差 0.0）  ✓")
assert float(PMAT_FULL.max()) <= 1.8, "全年电价上界超过分箱上界 1.8"

# =============================================================================
# 附：SOC 边界触及的精确计数（供图 4-4b）
#   与 q4_soc_hist.csv 的"末端分箱"不同——这里按**容差 1e-6**判定是否真的贴在下/上界，
#   分母为交付期 334 天 × 145 个储电量时刻 = 48,430。
# =============================================================================
rows = []
for v in VARIANTS:
    Sv = SS[v]
    rows.append([v, int((Sv <= SMIN + 1e-6).sum()), int((Sv >= SMAX - 1e-6).sum()), int(Sv.size)])
w("q4_soc_band_hits.csv", ["variant", "at_min", "at_max", "n_slots"], rows)
for r_ in rows:
    print(f"[8] variant {r_[0]} SOC 贴下界 {r_[1]:,d} / 贴上界 {r_[2]:,d}（分母 {r_[3]:,d}）")

# =============================================================================
# 附：调整量的逐小时 / 分阶段聚合（供图 4-3b）
#   口径：模板行（t=0 覆盖 0:10–0:20，t=143 覆盖次日 0:00–0:10）
#   4-2 无调整机制（q ≡ x），故其四项恒为 0 —— 这一点在下面断言
# =============================================================================
STAGE_EDGE = [0, 35, 71, 107, 144]        # 与 TSTAGE 一致（src/q4_solver.py 第 30 行）
STAGE_HOUR = [0, 6, 12, 18]


def _stage_of(t: int) -> int:
    for m_i in range(4):
        if STAGE_EDGE[m_i] <= t < STAGE_EDGE[m_i + 1]:
            return m_i
    raise AssertionError(f"时段 {t} 不属于任何阶段")


adj = {v: q[v] - x[v] for v in VARIANTS}
up = {v: np.clip(adj[v], 0.0, None) for v in VARIANTS}
dn = {v: np.clip(-adj[v], 0.0, None) for v in VARIANTS}
assert float(np.abs(adj["2"]).max()) < 1e-9, "variant 2 应无调整（q ≡ x）"

# 逐小时：模板行时段 t 对应的钟点为 ((t+1)*10) 分钟
hour_of = np.array([min(((t + 1) * 10) // 60, 23) for t in range(T)])
rows = [[hh,
         r(up["2"][:, hour_of == hh].sum()), r(dn["2"][:, hour_of == hh].sum()),
         r(up["3"][:, hour_of == hh].sum()), r(dn["3"][:, hour_of == hh].sum())]
        for hh in range(24)]
w("q4_adjust_by_hour.csv",
  ["hour", "up_kwh_42", "down_kwh_42", "up_kwh_43", "down_kwh_43"], rows)

# 分阶段：附上 4-3 的调整费（上调 1.5p、下调 0.5p，按交付期实际电价结算）
rows = []
for m_i in range(4):
    idx = np.array([_stage_of(t) == m_i for t in range(T)])
    rows.append([m_i, STAGE_HOUR[m_i],
                 r(up["2"][:, idx].sum()), r(dn["2"][:, idx].sum()),
                 r(up["3"][:, idx].sum()), r(dn["3"][:, idx].sum()),
                 r((1.5 * PMAT["3"][:, idx] * up["3"][:, idx]).sum()),
                 r((0.5 * PMAT["3"][:, idx] * dn["3"][:, idx]).sum())])
w("q4_adjust_by_stage.csv",
  ["stage", "publish_hour", "up_kwh_42", "down_kwh_42", "up_kwh_43", "down_kwh_43",
   "up_cost_yuan_43", "down_cost_yuan_43"], rows)

# 自检：模板行逐时段累计净上调，与 totals 的自然日口径对照
for v in VARIANTS:
    net_tpl = float(up[v].sum() - dn[v].sum())
    net_tot = float(tot[v]["adjust_up_kwh"]) - float(tot[v]["adjust_down_kwh"])
    print(f"[7] variant {v} 模板行净上调 {net_tpl:,.4f} kWh；"
          f"totals 净上调 {net_tot:,.4f} kWh（口径差 {net_tpl - net_tot:+.4f}，属模板行 vs 自然日）")
    if v == "3":
        assert abs(net_tpl - net_tot) < 3.0, f"variant 3 净上调两口径差 {net_tpl - net_tot!r} 偏大"

print("\n产出文件（共 21 个）：")
for i, p in enumerate(sorted(OUT.iterdir()), 1):
    print(f"  {i:2d}. {p.name}  ({p.stat().st_size} 字节)")
print(f"\n全部数据已写入 {OUT}")
