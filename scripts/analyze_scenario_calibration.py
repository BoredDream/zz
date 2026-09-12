"""Out-of-sample calibration diagnostics for the rolling Q4 scenario generator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import q4_solver as M

OUT = ROOT / "outputs" / "paper_analysis" / "calibration"
REPORT = ROOT / "reports" / "scenario_calibration.md"
QUANTILES = (0.1, 0.5, 0.9)
COVERAGES = (0.5, 0.8, 0.9)


def energy_score(ensemble: np.ndarray, actual: np.ndarray) -> float:
    a = np.mean(np.linalg.norm(ensemble - actual, axis=1))
    pair = np.mean(np.linalg.norm(ensemble[:, None] - ensemble[None, :], axis=2))
    return float(a - 0.5 * pair)


def crps(ensemble: np.ndarray, actual: np.ndarray) -> float:
    first = np.mean(np.abs(ensemble - actual[None, :]), axis=0)
    pair = np.mean(np.abs(ensemble[:, None, :] - ensemble[None, :, :]), axis=(0, 1))
    return float(np.mean(first - 0.5 * pair))


def update(acc: dict, ensemble: np.ndarray, actual: np.ndarray) -> None:
    acc["n_vectors"] += 1
    acc["n_points"] += actual.size
    acc["crps"].append(crps(ensemble, actual))
    acc["energy_score"].append(energy_score(ensemble, actual))
    for q in QUANTILES:
        acc["quantile"][str(q)].append(float(np.mean(actual <= np.quantile(ensemble, q, axis=0))))
    for c in COVERAGES:
        lo, hi = (1-c)/2, 1-(1-c)/2
        inside = (actual >= np.quantile(ensemble, lo, axis=0)) & (actual <= np.quantile(ensemble, hi, axis=0))
        acc["coverage"][str(c)].append(float(np.mean(inside)))


def blank() -> dict:
    return {"n_vectors": 0, "n_points": 0, "crps": [], "energy_score": [],
            "quantile": {str(q): [] for q in QUANTILES},
            "coverage": {str(c): [] for c in COVERAGES}}


def finish(acc: dict) -> dict:
    return {"n_vectors": acc["n_vectors"], "n_points": acc["n_points"],
            "mean_crps": float(np.mean(acc["crps"])),
            "mean_energy_score": float(np.mean(acc["energy_score"])),
            "quantile_calibration": {q: float(np.mean(v)) for q, v in acc["quantile"].items()},
            "central_interval_coverage": {q: float(np.mean(v)) for q, v in acc["coverage"].items()}}


def emergency_tail(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))["daily"]
    x = np.asarray([r.get("emergency_total_kwh", r.get("emergency_kwh", 0.0)) for r in raw])
    ordered = np.sort(x)[::-1]
    top_n = max(1, int(np.ceil(0.05 * len(x))))
    return {"days": len(x), "positive_days": int(np.sum(x > 1e-9)),
            "p90_kwh": float(np.quantile(x, .90)), "p95_kwh": float(np.quantile(x, .95)),
            "p99_kwh": float(np.quantile(x, .99)), "max_kwh": float(x.max()),
            "top5pct_share": float(ordered[:top_n].sum() / x.sum()) if x.sum() else 0.0}


def main() -> None:
    start = M.DSTR.index("2025-02-01")
    net_by_stage, price_by_stage = {m: blank() for m in range(4)}, {m: blank() for m in range(4)}
    extreme = []
    for d in range(start, M.ND):
        actual_net = M.L[d] - M.G[d]
        actual_price = M.PMAT[d]
        stage0_peak_ensemble = None
        for m in range(4):
            tm = M.TSTAGE[m]
            if m == 0:
                sl, sg, sp = M.scenarios4_145(d, 30)
                ens_net = (np.asarray(sl)-np.asarray(sg))[:, 1:]
                ens_price = np.asarray(sp)[:, 1:]
                y_net, y_price = actual_net, actual_price
                stage0_peak_ensemble = ens_net.max(1)
            else:
                sl, sg, sp = M.scenarios4(d, m, 30)
                ens_net = (np.asarray(sl)-np.asarray(sg))[:, tm:]
                ens_price = np.asarray(sp)[:, tm:]
                y_net, y_price = actual_net[tm:], actual_price[tm:]
            update(net_by_stage[m], ens_net, y_net)
            update(price_by_stage[m], ens_price, y_price)
        extreme.append({"date": M.DSTR[d], "actual_peak_net_kwh": float(actual_net.max()),
                        "stage0_peak_inside_90": bool(actual_net.max() >= np.quantile(stage0_peak_ensemble, .05) and actual_net.max() <= np.quantile(stage0_peak_ensemble, .95))})
    cutoff = np.quantile([x["actual_peak_net_kwh"] for x in extreme], .9)
    extreme_days = [x for x in extreme if x["actual_peak_net_kwh"] >= cutoff]
    result = {"scope": "Q4 rolling out-of-sample, 2025-02-01 to 2025-12-31, K<=30",
              "net_load": {str(m): finish(v) for m, v in net_by_stage.items()},
              "price": {str(m): finish(v) for m, v in price_by_stage.items()},
              "extreme_day_stage0": {"definition": "top 10% actual daily peak net load",
                                     "days": len(extreme_days),
                                     "peak_90pct_coverage": float(np.mean([x["stage0_peak_inside_90"] for x in extreme_days]))},
              "emergency_tail": {
                  "Q4-2": emergency_tail(ROOT/"outputs/q4/summary_q4-2_K30.json"),
                  "Q4-3": emergency_tail(ROOT/"outputs/q4/summary_q4-3_K30.json")}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"q4_calibration.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Q4滚动样本外情景校准", "", result["scope"], "",
             "## 净负荷校准", "", "|更新阶段|CRPS (kWh)|能量分数|50%覆盖|80%覆盖|90%覆盖|", "|---:|---:|---:|---:|---:|---:|"]
    for m in range(4):
        z=result["net_load"][str(m)]; c=z["central_interval_coverage"]
        lines.append(f"|{m}|{z['mean_crps']:.3f}|{z['mean_energy_score']:.3f}|{c['0.5']:.3f}|{c['0.8']:.3f}|{c['0.9']:.3f}|")
    lines += ["", "## 价格校准", "", "|更新阶段|CRPS (元/kWh)|能量分数|50%覆盖|80%覆盖|90%覆盖|", "|---:|---:|---:|---:|---:|---:|"]
    for m in range(4):
        z=result["price"][str(m)]; c=z["central_interval_coverage"]
        lines.append(f"|{m}|{z['mean_crps']:.4f}|{z['mean_energy_score']:.3f}|{c['0.5']:.3f}|{c['0.8']:.3f}|{c['0.9']:.3f}|")
    lines += ["", "## 分位数校准", "", "下表为实际值不超过预测分位数的经验频率；理想值分别为0.1、0.5、0.9。", "",
              "|变量|阶段|q10|q50|q90|", "|---|---:|---:|---:|---:|"]
    for variable in ("net_load", "price"):
        for m in range(4):
            q=result[variable][str(m)]["quantile_calibration"]
            lines.append(f"|{'净负荷' if variable=='net_load' else '价格'}|{m}|{q['0.1']:.3f}|{q['0.5']:.3f}|{q['0.9']:.3f}|")
    e=result["extreme_day_stage0"]
    lines += ["", "## 极端日与紧急购电尾部", "", f"阶段0在净负荷峰值最高10%的{e['days']}天中，90%情景区间覆盖率为{e['peak_90pct_coverage']:.1%}。", "",
              "|策略|正紧急购电日|P95(kWh)|P99(kWh)|最大值(kWh)|最坏5%占比|", "|---|---:|---:|---:|---:|---:|"]
    for name,z in result["emergency_tail"].items():
        lines.append(f"|{name}|{z['positive_days']}|{z['p95_kwh']:.1f}|{z['p99_kwh']:.1f}|{z['max_kwh']:.1f}|{z['top5pct_share']:.1%}|")
    lines += ["", "注：覆盖率是逐时段边际覆盖；能量分数衡量整条路径。场景数在年初由可用历史决定，随后上限为30。"]
    REPORT.write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
