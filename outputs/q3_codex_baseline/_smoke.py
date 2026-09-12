"""一次性冒烟测试：确认 398270c 版 q3_solver 可导入、可读数据、可解一次 LP。"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("q3c", "docs/q3_solver_codex_398270c.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["q3c"] = mod  # dataclass 需要 cls.__module__ 可在 sys.modules 中查到
spec.loader.exec_module(mod)

cfg = mod.Q3Config()
inputs = mod.load_q3_inputs(Path("problem/data"), cfg)
print("IMPORT_OK")
print("mapping:", json.dumps(inputs["mapping_audit"], ensure_ascii=False))
print("hashes:", inputs["input_hashes"])

scenarios, center, window = mod.make_scenarios(inputs, 40, 0, 0, 0.5, cfg)
prices = np.r_[inputs["price_natural"], inputs["price_natural"][0]]
sol = mod.solve_common(scenarios, prices, cfg.initial_soc_kwh, 0.1, cfg, fixed_first=100.0)
print("LP_OK", "scenarios=", scenarios.shape, "window=", window, "grid_sum=%.4f" % float(sol["grid"].sum()))
print("SMOKE_DONE")
