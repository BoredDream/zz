"""并排对比旧模型（q3_solver，主口径/退款口径）与新模型（q3_multistage）的交付期费用。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
old = json.loads((ROOT / "outputs" / "q3" / "summary.json").read_text(encoding="utf-8"))
new = json.loads((ROOT / "outputs" / "q3_multistage" / "summary_stages0123_K30.json").read_text(encoding="utf-8"))

print("旧模型 period:", json.dumps(old["period"], ensure_ascii=False))
print()
print("旧模型 totals_natural_day:")
for k, v in old["totals_natural_day"].items():
    print(f"   {k:<44} {v if not isinstance(v, (int, float)) else format(v, ',.2f')}")
print()
print("旧模型 policy_comparison（策略 -> 总费用）:")
for k, v in old["policy_comparison"].items():
    if isinstance(v, dict):
        print(f"   {k:<16} {json.dumps({kk: (round(vv, 2) if isinstance(vv, (int, float)) else vv) for kk, vv in v.items()}, ensure_ascii=False)[:220]}")
    else:
        print(f"   {k:<16} {v}")
print()
print("=" * 78)
print("新模型（多阶段随机规划，母线侧充放电口径），交付期 2025-02-01..12-31：")
for k, v in new["totals"].items():
    print(f"   {k:<28} {v:>18,.2f}")
