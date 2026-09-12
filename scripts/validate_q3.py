from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"outputs"/"q3"
def read_csv(name):
    with (OUT/name).open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))
def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));p=json.loads((OUT/"solver_payload.json").read_text(encoding="utf-8"));releases=json.loads((OUT/"release_log.json").read_text(encoding="utf-8"))
    assert len(p["days"])==334 and s["strict_multistage_optimal"] is False
    assert abs(s["mapping_audit"]["feb1_midnight_net_kwh"]-423.96)<1e-9 and s["mapping_audit"]["actual_midnight_max_error_kw"]<1e-10
    labels={"none","6","12","18","6+12","6+18","12+18","6+12+18","6+12+18_frozen0","6+12+18_refund"}
    assert set(s["policy_comparison"])==labels
    comp=read_csv("policy_comparison_daily.csv"); assert len(comp)==334*10 and {r["policy"] for r in comp}==labels
    assert len(releases)==365*(1+2+2+2+3+3+3+4+4+4)
    assert all(len(r["contract_kwh"]) in range(36,145) for r in releases)
    assert all(len(r["common_charge_kwh"])==len(r["contract_kwh"])+(1 if r["issue"]=="0:00" else 0) for r in releases)
    assert all(len(r["common_discharge_kwh"])==len(r["common_charge_kwh"]) for r in releases)
    rows=read_csv("interval_detail.csv"); assert len(rows)==334*144
    settlement=sum(float(r["price_yuan_per_kwh"])*float(r["initial_plan_kwh"])+float(r["adjustment_fee_yuan"]) for r in rows)
    emergency=sum(5*float(r["price_yuan_per_kwh"])*float(r["emergency_kwh"]) for r in rows)
    t=s["totals_natural_day"]; assert abs(settlement-t["settlement_cost_yuan"])<1e-5; assert abs(emergency-t["emergency_cost_yuan"])<1e-5
    c=s["checks"]; assert c["max_energy_balance_residual_kwh"]<1e-7 and c["max_soc_residual_kwh"]<1e-7 and c["simultaneous_charge_discharge_intervals"]==0 and c["cross_day_soc_continuity"] is True
    wb=load_workbook(OUT/"result3.xlsx",data_only=True)
    for sheet,key,total,cost in (("计划购电量","plan_kwh","plan_total_kwh","plan_cost_yuan"),("调整购电量","adjusted_kwh","adjusted_total_kwh","adjusted_settlement_yuan")):
        vals=list(wb[sheet].iter_rows(min_row=2,max_row=335,min_col=2,max_col=147,values_only=True))
        for row,day in zip(vals,p["days"]): assert np.allclose(np.array(row,float),np.array(day[key]+[day[total],day[cost]]),atol=1e-8,rtol=0)
    storage=wb["充放电量"]; wc=sum(float(storage.cell(i,3).value or 0) for i in range(2,2006));wd=sum(float(storage.cell(i,4).value or 0) for i in range(2,2006))
    assert abs(wc-sum(b["charge_kwh"] for d in p["days"] for b in d["storage_blocks"]))<1e-6; assert abs(wd-sum(b["discharge_kwh"] for d in p["days"] for b in d["storage_blocks"]))<1e-6
    er=wb["紧急购电量"];n=1+sum(max(1,len(d["emergency_segments"])) for d in p["days"]);we=sum(float(er.cell(i,3).value or 0) for i in range(2,n+1));assert abs(we-t["emergency_kwh"])<1e-6
    assert len(read_csv("baseline_none_interval_detail.csv"))==334*144 and len(read_csv("baseline_frozen0_interval_detail.csv"))==334*144
    print("Q3 validation passed: 10 policies, 48,096 primary intervals, release accounting, physical constraints, workbook reconciliation.")
if __name__=="__main__": main()
