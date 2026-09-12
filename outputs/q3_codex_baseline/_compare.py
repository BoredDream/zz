"""对照 398270c 版与当前 HEAD 版的第三问结果。仅读文件，不写任何产物。"""
import json
from pathlib import Path

head = json.loads(Path("outputs/q3/summary.json").read_text(encoding="utf-8"))
codex = json.loads(Path("outputs/q3_codex_baseline/summary.json").read_text(encoding="utf-8"))


def table(summary):
    return summary.get("policy_comparison", {})


h, c = table(head), table(codex)
labels = sorted(set(h) | set(c))

print("== 政策口径总费用对照（2025-02-01 至 2025-12-31）==")
print("%-20s %18s %18s %18s" % ("策略", "HEAD/元", "398270c/元", "差额(HEAD-codex)"))
for k in labels:
    hv = h.get(k, {}).get("total_cost_yuan")
    cv = c.get(k, {}).get("total_cost_yuan")
    if hv is None or cv is None:
        print("%-20s %18s %18s" % (k, f"{hv:.4f}" if hv else "-", f"{cv:.4f}" if cv else "-"))
    else:
        print("%-20s %18.4f %18.4f %+18.4f" % (k, hv, cv, hv - cv))

print()
print("== 关键量 ==")
for name, s in (("HEAD", head), ("398270c", codex)):
    t = s.get("totals_natural_day", {})
    print(
        "%-8s model=%-52s totals=%s"
        % (name, s.get("model", "?"), json.dumps({k: round(v, 4) for k, v in t.items()}, ensure_ascii=False))
    )

print()
print("== 校验量 ==")
for name, s in (("HEAD", head), ("398270c", codex)):
    print(name, json.dumps(s.get("checks", {}), ensure_ascii=False))

print()
print("== 输入哈希是否一致 ==")
print("一致" if head.get("input_hashes_sha256") == codex.get("input_hashes_sha256") else "不一致")
print(json.dumps(codex.get("input_hashes_sha256", {}), ensure_ascii=False))
