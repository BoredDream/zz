# -*- coding: utf-8 -*-
"""第二问图件 · 一键生成全部 9 张图
================================================================================
用法（在任意目录均可执行）：
    python run_all_figures.py              # 生成全部 9 张
    python run_all_figures.py 2a 5         # 只生成指定图（按模块名后缀匹配）

输出：
    handoff/q2/figures/  下每张图各 3 个文件（.svg / .pdf / .png 600dpi）

依赖：numpy、matplotlib；数据已固化在 handoff/q2/_figdata/，不需重跑求解器。
单独运行某一张图（调试用）：
    python q2_figures/fig2a.py
================================================================================
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

# 允许从任意工作目录运行：把本文件所在目录加入 sys.path
CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                        # noqa: BLE001
    pass

import q2_figures as pkg                                  # noqa: E402


def main(argv: list[str]) -> int:
    wanted = {a.lower() for a in argv}
    index = [row for row in pkg.FIGURE_INDEX
             if not wanted or row[3].lower() in wanted or row[0].lower() in wanted]
    if not index:
        print(f"未匹配到任何图；可选：{[r[3] for r in pkg.FIGURE_INDEX]}")
        return 1

    from q2_figures._common import FIGDIR, FONT, PNG_DPI

    print(f"中文字体 {FONT}   |   配色 低饱和蓝灰   |   PNG {PNG_DPI} dpi")
    print(f"输出目录 {FIGDIR}")
    print("-" * 78)

    ok = 0
    for no, title, stem, mod_name in index:
        try:
            mod = importlib.import_module(f"q2_figures.{mod_name}")
            res = getattr(mod, mod_name)()
            sizes = "  ".join(f"{k}:{Path(v).stat().st_size // 1024}KB"
                              for k, v in res["files"].items())
            print(f"  [OK]   {no:5s} {title:26s} {sizes}")
            ok += 1
        except Exception as exc:                          # noqa: BLE001
            print(f"  [FAIL] {no:5s} {title:26s} {type(exc).__name__}: {exc}")
    print("-" * 78)
    print(f"完成 {ok}/{len(index)} 张")
    return 0 if ok == len(index) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
