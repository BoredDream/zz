"""校验封存操作只加了横幅、没有改动正文一字。

对每个被加横幅的文件，剥掉横幅后与 git HEAD 中的原始版本逐字节比较。
若正文有任何差异，以非零退出码报错。

用法： python scripts/_verify_seal.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEP = "\n---\n\n"
TARGETS = [
    ("reports/_archive/q3_report.md", "reports/q3_report.md"),
    ("reports/_archive/q3_paper_handoff.md", "reports/q3_paper_handoff.md"),
    ("reports/_archive/q3_strategy_recommendation.md", "reports/q3_strategy_recommendation.md"),
    ("reports/_archive/q3_uniqueness_check.md", "reports/q3_uniqueness_check.md"),
    ("reports/_archive/q3_refund_verification.md", "reports/q3_refund_verification.md"),
    ("reports/_archive/q3_session_handoff.md", "reports/q3_session_handoff.md"),
    ("reports/q3_review.md", "reports/q3_review.md"),
]


def head_blob(path: str) -> bytes:
    return subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT,
                          stdout=subprocess.PIPE, check=True).stdout


def main() -> int:
    bad = 0
    for current, original in TARGETS:
        text = (ROOT / current).read_text(encoding="utf-8")
        if SEP not in text:
            print(f"  [FAIL] {current}: 找不到横幅结束分隔符")
            bad += 1
            continue
        body = text.split(SEP, 1)[1].encode("utf-8")
        orig = head_blob(original)
        if body == orig:
            n_banner = text.split(SEP, 1)[0].count("\n") + 2
            print(f"  [OK  ] {current:48s} 正文逐字节一致（横幅 {n_banner} 行）")
        else:
            print(f"  [FAIL] {current}: 正文有改动")
            bad += 1
    print()
    print(f"-> {len(TARGETS) - bad}/{len(TARGETS)} 通过" if not bad else f"-> {bad} 个文件不合格")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
