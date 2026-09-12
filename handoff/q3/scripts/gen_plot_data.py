"""生成 handoff/q3/_figdata 的绘图数据（对齐仓库现行第三问产物，不重跑求解器）。

运行：python handoff/q3/scripts/gen_plot_data.py（任意工作目录均可）

数据源：zz/outputs/q3_multistage/{summary,payload,detail}_* + q3_stage_comparison + lambda_sensitivity
输出：handoff/q3/_figdata/*.csv
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent          # zz/handoff/q3/scripts
Q3DIR = HERE.parent                             # zz/handoff/q3
ZZ = HERE.parents[2]                            # 仓库根（zz）
QM = ZZ / "outputs" / "q3_multistage"
OUT = Q3DIR / "_figdata"
OUT.mkdir(parents=True, exist_ok=True)
assert (ZZ / "outputs").is_dir(), f"未找到仓库产物目录：{ZZ / 'outputs'}"
assert QM.is_dir(), f"未找到第三问产物：{QM}"

TAG, K, T = "0123", 30, 144
DT = 1.0 / 6.0
TARGETS = ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")


def w(name: str, header: list[str], rows: list[list]) -> None:
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as h:
        cw = csv.writer(h)
        cw.writerow(header)
        cw.writerows(rows)
    print(f"  [写出] {name}  ({len(rows)} 行)")


# ---------------- 读入 ----------------
det = np.load(QM / f"detail_stages{TAG}_K{K}.npz")
pay = json.loads((QM / f"payload_stages{TAG}_K{K}.json").read_text(encoding="utf-8"))
sm = json.loads((QM / f"summary_stages{TAG}_K{K}.json").read_text(encoding="utf-8"))
dates = [str(d) for d in det["dates"]]
D0 = dates.index("2025-02-01")
sl = slice(D0, len(dates))
days = pay["days"]
tot = sm["meta"]["totals"]

x, q = det["x"][sl], det["q"][sl]
nx, nq = det["natural_x"][sl], det["natural_q"][sl]
zz_ = det["z"][sl]; cc = det["c"][sl]; gg = det["g"][sl]; ww = det["w"][sl]
SS = det["S"][sl]                      # 145 列（含起点）
S0s = det["S0"][sl]

a1 = pd.read_excel(ZZ / "problem" / "data" / "附件1.xlsx", header=0)
a1.columns = ["t", "p", "L", "G"]
P = a1.p.to_numpy(float)
L1 = a1.L.to_numpy(float)
G1 = a1.G.to_numpy(float)
price_nat = np.r_[P[-1], P[:-1]]       # 自然日价格向量（首段取上一原始行末列）

print(f"交付期 {len(days)} 天，明细 {x.shape}；npz 覆盖 {len(dates)} 天")

# ---------------- 1) 日度明细（口径：自然日；与 meta.totals 完全一致） ----------------
# 注：payload 的 plan_cost_yuan / adjusted_cost_yuan 是【表1 模板行口径】，
#     而 total_cost_yuan 与三项之和是【自然日口径】。两者相差 57.62 元（一个午夜列）。
#     为避免混用，本文件的费用列一律采用**自然日口径**：
#       计划购电费 = natural_day_plan_cost_yuan
#       调整费     = natural_day_adjust_cost_yuan
#       紧急费     = emergency_cost_yuan（本就是自然日口径）
#     并额外保留表1 口径列，供论文核表1 使用。
rows = []
for d in days:
    rows.append([d["date"], repr(float(d['plan_total_kwh'])), repr(float(d['plan_cost_yuan'])),
                 repr(float(d['adjusted_total_kwh'])), repr(float(d['adjusted_cost_yuan'])),
                 repr(float(d['emergency_total_kwh'])), repr(float(d['emergency_cost_yuan'])),
                 repr(float(d['total_cost_yuan'])), repr(float(d['curtail_kwh'])),
                 repr(float(d['adjust_up_kwh'])), repr(float(d['adjust_down_kwh'])),
                 repr(float(d['soc_start_kwh'])), repr(float(d['soc_end_kwh'])),
                 repr(float(d['natural_day_plan_cost_yuan'])), repr(float(d['natural_day_adjust_cost_yuan']))])
w("q3_daily_metrics.csv",
  ["date", "plan_total_kwh", "plan_cost_yuan_template", "final_contract_total_kwh",
   "adjust_cost_yuan_template", "emergency_kwh", "emergency_cost_yuan", "total_cost_yuan",
   "curtail_kwh", "adjust_up_kwh", "adjust_down_kwh", "soc_start_kwh", "soc_end_kwh",
   "plan_cost_yuan_natural", "adjust_cost_yuan_natural"], rows)

# ---------------- 2) 小时分布 ----------------
he = defaultdict(float); hec = defaultdict(int)
hw = defaultdict(float); hwc = defaultdict(int)
hc = defaultdict(float); hg = defaultdict(float); hn = defaultdict(float)
for i in range(zz_.shape[0]):
    for t in range(T):
        h = t // 6
        if zz_[i, t] > 1e-9:
            he[h] += float(zz_[i, t]); hec[h] += 1
        if ww[i, t] > 1e-9:
            hw[h] += float(ww[i, t]); hwc[h] += 1
        hc[h] += float(cc[i, t]); hg[h] += float(gg[i, t])
        hn[h] += float(L1[t] * DT - G1[t] * DT)
# 净负荷同时给出 kWh/时段 与 kW（图3-1a 用 kW，避免 1e6 计数）
rows = [[h, hec[h], repr(float(he[h])), hwc[h], repr(float(hw[h])),
         repr(float(hc[h])), repr(float(hg[h])), f"{price_nat[h * 6]:.4f}",
         repr(float(hn[h])), repr(float(hn[h] / DT))] for h in range(24)]
w("q3_hourly_profile.csv",
  ["hour", "emergency_intervals", "emergency_kwh", "curtail_intervals", "curtail_kwh",
   "charge_kwh", "discharge_kwh", "price_yuan_per_kwh", "net_load_kwh", "net_load_kw"], rows)

# ---------------- 3) 电价档归因 ----------------
pr = np.tile(price_nat, (zz_.shape[0], 1))
rows = []
for lo, hi in ((0.0, 0.45), (0.45, 0.75), (0.75, 1.05), (1.05, 1.45)):
    m = (pr >= lo) & (pr < hi)
    e = zz_[m]
    n = int((e > 1e-9).sum())
    meanp = float(pr[m][e > 1e-9].mean()) if n else 0.0
    rows.append([f"{lo:.2f}", f"{hi:.2f}", n, repr(float(float(e.sum()))),
                 repr(float(float((5 * pr[m] * e).sum()))), f"{meanp:.4f}", repr(float(float(ww[m].sum())))])
w("q3_emergency_by_price_band.csv",
  ["price_low", "price_high", "emergency_intervals", "emergency_kwh",
   "emergency_cost_yuan", "mean_price", "curtail_kwh"], rows)

# ---------------- 4) 月度汇总（自然日口径） ----------------
mon = defaultdict(lambda: defaultdict(float))
for d in days:
    m = d["date"][:7]
    b = mon[m]
    for k, key in (("plan_kwh", "plan_total_kwh"), ("final_kwh", "adjusted_total_kwh"),
                   ("plan_fee", "natural_day_plan_cost_yuan"),
                   ("adj_fee", "natural_day_adjust_cost_yuan"),
                   ("emg_kwh", "emergency_total_kwh"), ("emg_fee", "emergency_cost_yuan"),
                   ("total", "total_cost_yuan"), ("curtail", "curtail_kwh"),
                   ("up", "adjust_up_kwh"), ("down", "adjust_down_kwh")):
        b[k] += d[key]
    b["days"] += 1
rows = [[m, int(b["days"]), repr(float(b['plan_kwh'])), repr(float(b['final_kwh'])), repr(float(b['plan_fee'])),
         repr(float(b['adj_fee'])), repr(float(b['emg_kwh'])), repr(float(b['emg_fee'])), repr(float(b['total'])),
         repr(float(b['curtail'])), repr(float(b['up'])), repr(float(b['down']))]
        for m, b in sorted(mon.items())]
w("q3_monthly_summary.csv",
  ["month", "days", "plan_kwh", "final_contract_kwh", "plan_cost_yuan", "adjust_cost_yuan",
   "emergency_kwh", "emergency_cost_yuan", "total_cost_yuan", "curtail_kwh",
   "adjust_up_kwh", "adjust_down_kwh"], rows)

# ---------------- 5) 四个指定日期的 144 段明细 ----------------
rows = []
for dt in TARGETS:
    i = dates.index(dt)
    for t in range(T):
        a, b = (t + 1) * 10, (t + 2) * 10
        rows.append([dt, t, f"{a // 60}:{a % 60:02d}", f"{P[t]:.4f}",
                     repr(float(det['x'][i, t])), repr(float(det['q'][i, t])),
                     repr(float(det['natural_x'][i, t])), repr(float(det['natural_q'][i, t])),
                     repr(float(det['z'][i, t])), repr(float(det['c'][i, t])), repr(float(det['g'][i, t])),
                     repr(float(det['w'][i, t])), repr(float(det['S'][i, t + 1]))])
w("q3_target_days_interval.csv",
  ["date", "t_template", "time_start", "price_yuan_per_kwh", "plan_kwh", "final_contract_kwh",
   "natural_plan_kwh", "natural_final_kwh", "emergency_kwh", "charge_kwh", "discharge_kwh",
   "curtail_kwh", "soc_end_kwh"], rows)

# ---------------- 6) SOC 触边与充放电分布（供直方图） ----------------
soc_all = SS[:, 1:].ravel()
rows = [[f"{v:.1f}"] for v in soc_all]
w("q3_soc_hist.csv", ["soc_end_kwh"], rows)
rows = []
for i in range(cc.shape[0]):
    for t in range(T):
        if cc[i, t] > 1e-9:
            rows.append(["charge", repr(float(cc[i, t]))])
        if gg[i, t] > 1e-9:
            rows.append(["discharge", repr(float(gg[i, t]))])
w("q3_charge_discharge_hist.csv", ["kind", "kwh_per_interval"], rows)
rows = [[dt, f"{s:.4f}"] for dt, s in zip([d["date"] for d in days], S0s)]
w("q3_soc_start_delivery_series.csv", ["date", "soc_start_kwh"], rows)

# ---------------- 7) 预报组合对照 ----------------
cmpj = json.loads((QM / "q3_stage_comparison.json").read_text(encoding="utf-8"))
rows = []
for r in sorted(cmpj["rows"], key=lambda v: v["rank"]):
    rows.append([r["policy"], "|".join(str(s) for s in r["stages"]), r["rank"],
                 repr(float(r['total_cost_yuan'])), repr(float(r['saving_vs_0_only_yuan'])),
                 repr(float(r['saving_vs_0_only_pct'])), repr(float(r['plan_cost_yuan'])),
                 repr(float(r['adjust_cost_yuan'])), repr(float(r['emergency_cost_yuan'])),
                 repr(float(r['emergency_kwh'])), repr(float(r['curtail_kwh']))])
w("q3_stage_comparison.csv",
  ["policy", "stages", "rank", "total_cost_yuan", "saving_vs_0_only_yuan", "saving_vs_0_only_pct",
   "plan_cost_yuan", "adjust_cost_yuan", "emergency_cost_yuan", "emergency_kwh", "curtail_kwh"], rows)
sh = cmpj["shapley_savings_vs_0_only_for_full_policy_yuan"]
saving = cmpj["full_policy_saving_vs_0_only_yuan"]
rows = [[k, repr(float(v)), f"{v / saving * 100:.4f}"] for k, v in sh.items()]
w("q3_shapley.csv", ["issue", "shapley_saving_yuan", "share_pct"], rows)
rows = []
for issue, items in cmpj["conditional_marginal_savings"].items():
    for it in items:
        rows.append([issue, "|".join(it["context"]) if it["context"] else "(baseline)",
                     repr(float(it['saving_yuan']))])
w("q3_conditional_marginal.csv", ["issue", "context", "saving_yuan"], rows)

# ---------------- 8) λ 敏感性 ----------------
lam = json.loads((QM / "lambda_sensitivity_K30.json").read_text(encoding="utf-8"))
rows = []
for r in lam["scan"]:
    rows.append([f"{r['lam']:.4f}", f"{r['lam_over_baseline']:.4f}", repr(float(r['total_cost_yuan'])),
                 repr(float(r['delta_vs_baseline_yuan'])), repr(float(r['delta_pct'])),
                 repr(float(r['emergency_kwh'])), repr(float(r['emergency_cost_yuan'])),
                 repr(float(r['curtail_kwh'])), repr(float(r['soc_start_delivery_kwh'])),
                 repr(float(r['soc_end_delivery_kwh'])), repr(float(r['soc_end_mean_daily_kwh'])),
                 repr(float(r['cost_net_of_storage_change_yuan']))])
w("q3_lambda_sensitivity.csv",
  ["lam", "lam_over_baseline", "total_cost_yuan", "delta_vs_baseline_yuan", "delta_pct",
   "emergency_kwh", "emergency_cost_yuan", "curtail_kwh", "soc_start_delivery_kwh",
   "soc_end_delivery_kwh", "soc_end_mean_daily_kwh", "cost_net_of_storage_change_yuan"], rows)
w("q3_lambda_range.csv",
  ["item", "value"],
  [["min_cost_lam", f"{lam['range']['min_cost']['lam']}"],
   ["min_cost_yuan", repr(float(lam['range']['min_cost']['total_cost_yuan']))],
   ["max_cost_lam", f"{lam['range']['max_cost']['lam']}"],
   ["max_cost_yuan", repr(float(lam['range']['max_cost']['total_cost_yuan']))],
   ["spread_yuan", repr(float(lam['range']['spread_yuan']))],
   ["spread_pct_of_baseline", repr(float(lam['range']['spread_pct_of_baseline']))],
   ["costs_monotone_in_lam", str(lam["range"]["costs_monotone_in_lam"])]])

# ---------------- 9) 求解器敏感性 ----------------
rows = []
for nm, label in (("solver_sensitivity_highs-ds.json", "highs-ds（对偶单纯形）"),
                  ("solver_sensitivity_highs-ipm.json", "highs-ipm（内点法）")):
    s = json.loads((QM / nm).read_text(encoding="utf-8"))
    rows.append([label, s["method"], repr(float(s['alt_total_cost_yuan'])), repr(float(s['total_gap_yuan'])),
                 f"{s['total_gap_pct']:.9f}", repr(float(s['max_abs_daily_gap_yuan'])),
                 s["worst_day"], s["days_with_gap_over_1yuan"], f"{s['elapsed_seconds']:.1f}"])
rows.insert(0, ["highs（主答案）", "highs", repr(float(tot['total_cost_yuan'])), "0.000000", "0.000000000",
                "0.000000", "—", 0, "369.1"])
w("q3_solver_sensitivity.csv",
  ["label", "method", "total_cost_yuan", "gap_yuan", "gap_pct", "max_daily_gap_yuan",
   "worst_day", "days_with_gap_over_1yuan", "elapsed_seconds"], rows)
cen = json.loads((QM / "solver_degeneracy_census.json").read_text(encoding="utf-8"))
ov = cen["overall"]
rows = [
    ["抽样天数", cen["sampled_days"]], ["LP 总数", cen["lps"]],
    ["跨算法最大相对目标偏差", f"{ov['max_rel_obj_gap_across_methods']:.6e}"],
    ["目标偏差 > 1e-9 的 LP 数", ov["n_lps_obj_gap_gt_1e-9"]],
    ["目标偏差 > 1e-6 的 LP 数", ov["n_lps_obj_gap_gt_1e-6"]],
    ["解向量不同的 (LP,算法) 对数", ov["n_lp_method_pairs_solution_differs"]],
    ["(LP,算法) 总对数", ov["n_lp_method_pairs"]],
    ["解向量不同占比", f"{ov['n_lp_method_pairs_solution_differs'] / ov['n_lp_method_pairs'] * 100:.4f}"],
    ["数值抖动最大相对目标差", f"{ov['jitter_max_rel_obj_gap']:.6e}"],
    ["抖动下解改变数", f"{ov['jitter_n_solution_differs']} / {ov['jitter_n']}"],
]
w("q3_solver_degeneracy_summary.csv", ["item", "value"], rows)

# ---------------- 10) 与第四问对照 ----------------
q4 = json.loads((ZZ / "outputs" / "q4" / "summary_q4-3_K30.json").read_text(encoding="utf-8"))
q4t = q4["meta"]["totals"]["total_cost_yuan"]
rows = [["第三问（确定性电价）", repr(float(tot['total_cost_yuan'])), "334", "—"],
        ["第四问 Q4-3（波动电价）", repr(float(q4t)), "334",
         repr(float((q4t - tot['total_cost_yuan'])))],
        ["差额占比", f"{(q4t / tot['total_cost_yuan'] - 1) * 100:.4f}", "", ""]]
w("q3_vs_q4.csv", ["item", "value", "days", "delta_yuan"], rows)

# ---------------- 11) 新旧模型对照（旧模型仅供审计） ----------------
old = json.loads((ZZ / "outputs" / "q3" / "summary.json").read_text(encoding="utf-8"))["totals_natural_day"]
rows = [
    ["总费用/元", f"{old['total_cost_yuan']:.4f}", f"{tot['total_cost_yuan']:.4f}",
     f"{(tot['total_cost_yuan'] - old['total_cost_yuan']):.4f}"],
    ["紧急购电量/kWh", f"{old['emergency_kwh']:.4f}", f"{tot['emergency_kwh']:.4f}",
     f"{(tot['emergency_kwh'] - old['emergency_kwh']):.4f}"],
    ["紧急购电费/元", f"{old['emergency_cost_yuan']:.4f}", f"{tot['emergency_cost_yuan']:.4f}",
     f"{(tot['emergency_cost_yuan'] - old['emergency_cost_yuan']):.4f}"],
]
w("q3_old_vs_new.csv", ["metric", "old_model_value", "current_model_value", "delta"],
  rows)

# ---------------- 12) 关键指标 meta ----------------
meta = {
    "model": sm["meta"]["model"],
    "commit": "3fc646f",
    "windows": {"plan_adjust": sm["meta"]["plan_adjust_time_frame"],
                "physical_reporting": sm["meta"]["physical_reporting_time_frame"]},
    "stage0_horizon_intervals": sm["meta"]["stage0_horizon_intervals"],
    "K": K, "stages": [0, 1, 2, 3],
    "delivery_period": sm["meta"]["delivery_period"],
    "interval_count": int(zz_.size),
    "totals": {k: float(v) for k, v in tot.items()},
    "solver_gap": {"highs_ds_yuan": 0.0,
                   "highs_ipm_yuan": json.loads((QM / "solver_sensitivity_highs-ipm.json")
                                                .read_text(encoding="utf-8"))["total_gap_yuan"]},
    "lambda_range": {"spread_yuan": lam["range"]["spread_yuan"],
                     "spread_pct": lam["range"]["spread_pct_of_baseline"],
                     "monotone": lam["range"]["costs_monotone_in_lam"]},
    "stage_comparison": {"best": cmpj["best_policy"],
                         "saving_vs_0_only_yuan": saving,
                         "shapley": sh},
}
(OUT / "q3_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print("  [写出] q3_meta.json")
print(f"\n全部数据已写入 {OUT}")
