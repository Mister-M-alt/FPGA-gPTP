#!/usr/bin/env python3
"""Run passes_test.py's check 8 alone (no_core_replay) under the caller's current core limits.
usage: check8_only.py ENGINE_DIR SCRATCH"""
import importlib.util, resource, sys
from pathlib import Path
eng, scratch = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("passes_test", eng / "passes_test.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print("caller RLIMIT_CORE:", resource.getrlimit(resource.RLIMIT_CORE))
scratch.mkdir(parents=True, exist_ok=True)
sys.exit(1 if m.no_core_replay({}, scratch) else 0)
