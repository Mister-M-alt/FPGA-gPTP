#!/bin/bash
# gates3.sh: the processor gates at the merged head 331e27d (gate worktree), the engine arm (its own worktree), as one
# receipt: rc lines, the engine tallies, the #100/#106/#107 INFO lines against round 2's, the other suites' tallies,
# then the arm's every verdict line and tally
S=$VALIDATION_STORAGE/gptp106-a831; L=$S/logs-331e27d; R2=<home-path>/milan-fpga-management/2026-09-23/gptp106-a831/round2/receipts
echo "# processor gates at 331e27d (gate worktree, detached; host $(verilator --version))"
echo "## leg4.sh: one rc line per gate"; cat $L/leg4.summary
echo; echo "## engine suite (make -C tb/verilator/engine run): tallies"
grep -E "^[0-9]+ checks:|^-- " $L/engine-run.log
echo; echo "## engine suite: every INFO and tally line of the four passes, against round 2's engine log at a728cc3"
diff <(grep "^INFO\|checks:" $S/logs-a728cc3/engine-run.log) <(grep "^INFO\|checks:" $L/engine-run.log) > /dev/null && echo "identical: $(grep -c '^INFO' $L/engine-run.log) INFO lines and the four tallies" || echo DIFFERENT
echo; echo "## the #100, #106 and #107 INFO lines of the shipping pass"
awk '/^-- /{exit} /^INFO #10[067]/' $L/engine-run.log
echo; echo "## engine suite: the renamed phase-59 check (#107 follow)"; grep -E "#107 follow: |B\.1\.1 range" $L/engine-run.log | sort | uniq -c
echo; echo "## the FAIL lines of the engine suite"; grep -c "^FAIL" $L/engine-run.log
echo; echo "## parser, ucpu, gaskets, tsngen, bench, lint, docs tallies"
for g in parser ucpu gaskets tsngen bench; do echo "$g: $(grep -E 'checks:|^PASS|mutant caught' $L/$g.log | tail -2 | tr '\n' ' ')"; done
echo "lint: $(tail -3 $L/lint.log | tr '\n' ' ')"
echo "docs: $(grep -E 'PASS|FAIL' $L/docs.log | tr '\n' ' ')"
echo; echo "# the engine mutation arm at 331e27d (arm worktree; make -C tb/verilator/engine mutants = python3 mutants.py, --jobs $(cd $S/arm-331e27d/tb/verilator/engine && python3 -c 'import mutants; print(mutants.default_jobs())'), ccache on PATH)"
echo "## Run in two halves of its table (tools/armslice3.py: the arm's own main() over MUTATIONS[a:b], unbuffered), each with"
echo "## the positive control: one run of the whole table at --jobs 8 takes about 122 min here, past a session task's 2 h."
echo "## A first whole-table run was stopped after 27 min, before printing (its output is block-buffered): $(cat $L/arm-stopped-buffered.summary)"
cat $L/arm.summary
for h in 0 84; do echo; echo "### $(head -1 $L/arm-$h.log)"; grep -E "^\[(PASS|FAIL)\]|checks:" $L/arm-$h.log; done
echo; echo "## verdict counts over both halves"
echo "controls: $(cat $L/arm-0.log $L/arm-84.log | grep -c '^\[PASS\] mutant caught') caught, $(cat $L/arm-0.log $L/arm-84.log | grep -c '^\[FAIL\]') FAIL lines; positive control: $(cat $L/arm-0.log $L/arm-84.log | grep -c '^\[PASS\] the unmutated engine still passes') of 2 passes"
echo "in table order: $(cd $S/arm-331e27d/tb/verilator/engine && python3 -c "
import sys, re; sys.argv=['x']; import mutants
names = [m[0] for m in mutants.MUTATIONS]
got = [re.match(r'\[PASS\] mutant caught: (.*?) - (breaks|fails all)', l).group(1) for f in ('$L/arm-0.log', '$L/arm-84.log') for l in open(f) if l.startswith('[PASS] mutant caught')]
print('the', len(got), 'caught verdicts name the table\'s', len(names), 'controls in order' if got == names else 'NOT the table in order')")"
echo "the #106 and #107 controls:"; cat $L/arm-0.log $L/arm-84.log | grep -E "^\[(PASS|FAIL)\].*(#106 |#107 )" | cut -c1-220
