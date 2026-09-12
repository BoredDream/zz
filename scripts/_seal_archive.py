"""给 reports/_archive/ 下的旧模型报告加封存横幅（幂等）。

这些文件描述的是已被取代的第三问模型 src/q3_solver.py。加横幅而不删正文，
是为了保留审计轨迹，同时防止其中的数字被误引用。

用法： python scripts/_seal_archive.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "reports" / "_archive"
MARK = "🔒 **已封存（2026-09-12）**"

COMMON = """> 🔒 **已封存（2026-09-12）** —— 本文件描述的是**已被取代**的第三问模型
> `src/q3_solver.py`，其全部数字与结论**均已失效，不得再被引用**。
>
> **失效原因**：第三问在阶段B 之后整体更换为 `src/q3_multistage.py`
> （模板行框、0:00/6:00/12:00/18:00 四阶段、题面结算口径）。
> 新旧模型的时间口径与结算口径都不同，**两边的数字不可相减、不可混引**。
>
> **现行权威来源**：`docs/q3_multistage_model.md`、`reports/q3_report.md`、
> `reports/q3_paper_handoff.md`。
>
> 本文件仅作**审计轨迹**保留，不再更新。

**本文件承载的已失效内容**：{what}

---

"""

# 每个文件的"具体失效了什么"
WHAT = {
    "q3_report.md": "旧模型的交付期总费用 14,743,406.7685 元、"
                    "`none/6/12/18/6+12/6+18/12+18/6+12+18` 八套预报组合比较、"
                    "退款口径敏感性；以及第 4—6 节的指定日期表（自然日口径 + 跨行映射）。",
    "q3_paper_handoff.md": "整套论文引用契约，含「一句话结论：14,743,406.7685 元、"
                           "`6+12+18` 领先 `6+12` 共 6,282.6614 元」等结论。"
                           "**这些结论在当前模型上从未被复现。**",
    "q3_strategy_recommendation.md": "在旧模型上得出的 `6+12+18` 策略推荐决策表。"
                                     "当前模型的结构本身即 0/6/12/18，不存在该组合择优问题。",
    "q3_uniqueness_check.md": "对旧模型 `6+12+18` 主口径最优解唯一性的检验"
                              "（退化时刻 611/1460、年度费用随求解器配置浮动约 0.226%）。"
                              "**当前模型未做同等检验。**",
    "q3_refund_verification.md": "对旧模型退款口径 8 组合总费用的两条独立路径复算。"
                                 "**当前模型未做同等复算。**",
    "q3_session_handoff.md": "旧 `src/q3_solver.py` 的断点续跑改造与 10 套策略回测交接记录。",
}


# 用户自己的审查文件：只在原位加横幅，不搬进 _archive/、不改动正文一字。
# q2_review.md 审的是第二问，其「跨行映射」结论对第二问仍然成立，故不动。
INPLACE = ROOT / "reports" / "q3_review.md"
INPLACE_BANNER = """> 🔒 **审查对象已失效（2026-09-12）** —— 本文件审查的是 `src/q3_solver.py`，
> 该模型已被 `src/q3_multistage.py` 整体取代。
>
> **本审查记录对当前模型不作数**：其中的模型描述、数字与结论均针对旧模型，
> 不得作为现行第三问模型的证据引用。现行权威来源见
> `docs/q3_multistage_model.md` 与 `reports/q3_report.md`。
>
> 按既定约定，**审查正文一字未改**，仅加此横幅。本文件作者为用户，
> 不属于项目产物，保留原样仅作历史记录。

---

"""


def main() -> int:
    n = 0
    for path in sorted(ARCHIVE.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if MARK in text:
            print(f"  [skip] {path.name} 已有横幅")
            continue
        what = WHAT.get(path.name)
        if what is None:
            print(f"  [warn] {path.name} 未定义失效内容，跳过")
            continue
        # newline="\n"：保留原有 LF 行尾，否则 Windows 上会整篇变成 CRLF
        path.write_text(COMMON.format(what=what) + text, encoding="utf-8", newline="\n")
        print(f"  [ok  ] {path.name}")
        n += 1

    if INPLACE.exists():
        text = INPLACE.read_text(encoding="utf-8")
        if MARK in text:
            print(f"  [skip] {INPLACE.name} 已有横幅")
        else:
            INPLACE.write_text(INPLACE_BANNER + text, encoding="utf-8", newline="\n")
            print(f"  [ok  ] {INPLACE.name}（原位，正文未改）")
            n += 1

    print(f"-> 共加横幅 {n} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
