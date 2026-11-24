#!/usr/bin/env python3
"""plant.py SIM_MAIN KIND: plant one disposable defect into one pass of the engine harness.

KIND fail-seedrun : the pass run from seedrun/ (pass 1) fails one extra named check.
KIND abort-sync   : the pass run from syncseedrun/ (pass 2) prints a line and aborts (SIGABRT).
"""
import sys
path, kind = sys.argv[1], sys.argv[2]
src = open(path, encoding="utf-8").read()
inc = "#include <cstdlib>\n"
assert src.count(inc) == 1
src = src.replace(inc, inc + "#include <cstring>\n#include <unistd.h>\n", 1)
def in_dir(name):
    return ('[] { char *c = getcwd(nullptr, 0); bool r = c && std::strlen(c) >= %d && '
            'std::strcmp(c + std::strlen(c) - %d, "/%s") == 0; std::free(c); return r; }()'
            % (len(name) + 1, len(name) + 1, name))
if kind == "fail-seedrun":
    anchor = '    printf("%d checks: %d PASS, %d FAIL\\n", checks, checks - fails, fails);\n'
    assert src.count(anchor) == 1
    src = src.replace(anchor, '    if (%s) expect("planted seedrun defect", 1, 0);\n' % in_dir("seedrun") + anchor, 1)
elif kind == "abort-sync":
    anchor = "  Verilated::commandArgs(argc, argv);\n"
    assert src.count(anchor) == 1
    src = src.replace(anchor, anchor + '  if (%s) { printf("planted abort in syncseedrun\\n"); std::fflush(stdout); std::abort(); }\n' % in_dir("syncseedrun"), 1)
else:
    sys.exit("unknown kind")
open(path, "w", encoding="utf-8").write(src)
