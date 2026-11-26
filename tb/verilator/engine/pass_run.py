#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""#111: one engine pass in make's job slot, and its replay in the serial order.

usage: pass_run.py [--ignore-errors] run N [--mkdir DIR] [--gen COMMAND] (--shell COMMAND | -- SIMULATOR [ARG...])
       pass_run.py [--ignore-errors] replay-gen N
       pass_run.py [--ignore-errors] replay N [--banner LINE]

The Makefile's `run` makes each of the suite's four passes its own target, so
make schedules them within the caller's job budget: `make -j1 run` runs one
at a time, `make -j4 run` all four at once, and a parent make's jobserver
counts each pass as one job. `run` makes DIR and writes pass N's image with
the generator COMMAND (its standard output discarded), then runs the pass as
the serial recipe ran it: the simulator itself, as make ran a line with no
shell syntax, or the serial line's own `cd DIR && ...` through /bin/sh. It
keeps what each wrote to standard output and standard error and records how
the pass ended: its exit status, or the signal that killed it and whether it
dumped core. It always exits 0, so a failing pass never stops make before the
passes are printed.

`replay-gen N` and `replay N` then print pass N exactly where the serial
recipe printed it, each from its own recipe line of `run`, and end as the
serial line ended: with the generator's or the simulator's exit status, or by
the same signal, so make reports `Error 1`, `Aborted` or `Killed` just as it
did. A transcript that cannot be printed fails the line with a diagnostic.

Fail fast: unless make ignores errors (-i), the first failing pass in order
stops every later pass, whose output the serial recipe would never have
printed, and a replay after a failure prints nothing, since the serial recipe
had stopped there (make -k goes on to `run`'s next rule; the serial recipe
did not). With -i every pass runs and prints, as the serial recipe's did.

An INT, TERM, QUIT or HUP to a pass is passed to its simulator, and once the
simulator has ended the pass dies of the same signal, so make sees its job
killed as it saw the serial recipe's.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import resource
import selectors
import signal
import subprocess
import sys
from pathlib import Path

#: Everything one `make run` records, removed by `run`'s first rule.
STATE = Path("obj_dir/engine-passes")
PR_SET_DUMPABLE = 4  # the prctl(2) option number
FORWARDED = (signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, signal.SIGHUP)


def failed_before(n: int) -> bool:
    """True when the build or an earlier pass failed: the serial recipe stopped there."""
    return not (STATE / "build.ok").exists() or any((STATE / f"{k}.stop").exists() for k in range(n))


def descendants(pid: int) -> list[int]:
    """`pid` and every process below it, so a shell that did not exec its simulator is no shelter."""
    parents: dict[int, list[int]] = {}
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat.read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        parents.setdefault(int(fields[1]), []).append(int(stat.parent.name))
    found, todo = [], [pid]
    while todo:
        current = todo.pop()
        found.append(current)
        todo.extend(parents.get(current, []))
    return found


def signal_all(pid: int, signum: int) -> None:
    """Send `signum` to `pid` and everything below it."""
    for target in descendants(pid):
        try:
            os.kill(target, signum)
        except OSError:
            pass


def write_atomic(path: Path, data: str) -> None:
    """Write `path` whole or not at all."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(data)
    temporary.replace(path)


def run(n: int, directory: str | None, generate: str | None, argv: list[str], ignoring: bool) -> int:
    """Run pass N and record it; exit 0 unless a signal interrupted it."""
    STATE.mkdir(parents=True, exist_ok=True)
    log = (STATE / f"{n}.log").open("wb")
    record: dict = {}
    received: list[int] = []
    child: list[subprocess.Popen] = []

    def chunk(stream: int, data: bytes) -> None:
        """Keep `data` as one record of the transcript: the stream (1 or 2), its length, then the bytes."""
        log.write(bytes([stream]) + len(data).to_bytes(4, "big") + data)

    def forward(signum: int, _frame: object) -> None:
        """Pass an INT, TERM, QUIT or HUP on to the simulator and all below it, and remember it for the end."""
        received.append(signum)
        if child and child[0].returncode is None:
            signal_all(child[0].pid, signum)

    def stop(_signum: int, _frame: object) -> None:
        """An earlier pass's SIGUSR1: if that pass failed, mark this one stopped and end its simulator."""
        if failed_before(n):
            record["stopped"] = True
            if child and child[0].returncode is None:
                signal_all(child[0].pid, signal.SIGTERM)

    for signum in FORWARDED:
        if signal.getsignal(signum) is not signal.SIG_IGN:
            signal.signal(signum, forward)
    signal.signal(signal.SIGUSR1, stop)
    (STATE / f"{n}.pid").write_text(str(os.getpid()))
    if not ignoring and failed_before(n):
        record["stopped"] = True  # an earlier pass failed: the serial recipe never ran this one
    if directory is not None:
        Path(directory).mkdir(parents=True, exist_ok=True)
    if generate is not None and "stopped" not in record:
        # The serial line itself, its redirection included, through the same shell: a shell that forks reports a
        # signal death as 128+n, which is kept; a shell that execs dies of the signal itself, which is recorded and
        # re-raised at replay, as for the simulator.
        gen = subprocess.Popen(["/bin/sh", "-c", generate + " >/dev/null"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE)
        err = gen.stderr.read()
        gen.stderr.close()
        _, status = os.waitpid(gen.pid, 0)
        gen.returncode = os.waitstatus_to_exitcode(status)
        if err:
            record["gen_stderr"] = err.decode(errors="surrogateescape")
        if os.WIFSIGNALED(status):
            record.update(gen_signal=os.WTERMSIG(status), gen_core=os.WCOREDUMP(status))
        record["gen"] = os.WEXITSTATUS(status) if os.WIFEXITED(status) else 0
        if gen.returncode and not ignoring:
            stop_later(n)
            record["stopped"] = True
    if "stopped" not in record and not received:
        try:
            child.append(subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            if record.get("stopped"):
                signal_all(child[0].pid, signal.SIGTERM)  # an earlier pass failed as this one started
            if received:
                signal_all(child[0].pid, received[0])  # a signal that came before the child was known
        except OSError as exc:
            chunk(2, f"make: {argv[0]}: {exc.strerror}\n".encode())
            record["exit"] = 127
        else:
            proc = child[0]
            selector = selectors.DefaultSelector()
            selector.register(proc.stdout, selectors.EVENT_READ, 1)
            selector.register(proc.stderr, selectors.EVENT_READ, 2)
            while selector.get_map():
                for key, _ in selector.select():
                    data = os.read(key.fd, 65536)
                    if data:
                        chunk(key.data, data)
                    else:
                        selector.unregister(key.fileobj)
            _, status = os.waitpid(proc.pid, 0)
            proc.returncode = os.waitstatus_to_exitcode(status)
            if os.WIFSIGNALED(status):
                record.update(signal=os.WTERMSIG(status), core=os.WCOREDUMP(status))
            else:
                record["exit"] = os.WEXITSTATUS(status)
            if not record.get("stopped") and (record.get("signal") or record.get("exit")) and not ignoring:
                stop_later(n)
    # This pass is over: a later stop must not find it exiting, when Python's shutdown restores the default action.
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    (STATE / f"{n}.pid").unlink(missing_ok=True)  # no later stop reaches a recycled pid
    log.close()
    if received:
        (STATE / f"{n}.json").unlink(missing_ok=True)
        signal.signal(received[0], signal.SIG_DFL)
        os.kill(os.getpid(), received[0])
    write_atomic(STATE / f"{n}.json", json.dumps(record))
    return 0


def stop_later(n: int) -> None:
    """Pass N failed: mark it, then stop every later pass still running."""
    (STATE / f"{n}.stop").touch()
    for later in range(n + 1, 4):
        try:
            os.kill(int((STATE / f"{later}.pid").read_text()), signal.SIGUSR1)
        except (OSError, ValueError):
            pass  # not started (it will see the mark) or already finished


def emit(fd: int, data: bytes) -> None:
    """Write all of `data` to `fd`."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def load(n: int) -> dict:
    """Pass N's record, or exit 1 with the reason it cannot be replayed."""
    try:
        return json.loads((STATE / f"{n}.json").read_text())
    except (OSError, ValueError) as exc:
        print(f"engine pass {n}: no record to print ({exc})", file=sys.stderr)
        raise SystemExit(1) from None


def replay_gen(n: int, ignoring: bool) -> int:
    """Pass N's image generator: its standard error, then its status."""
    if not ignoring and failed_before(n):
        return 0
    record = load(n)
    try:
        emit(2, record.get("gen_stderr", "").encode(errors="surrogateescape"))
    except OSError as exc:
        print(f"engine pass {n}: its image generator's output could not be printed ({exc})", file=sys.stderr)
        return 1
    if record.get("gen") or record.get("gen_signal"):
        (STATE / f"{n}.stop").touch()
    if record.get("gen_signal"):
        reraise(record["gen_signal"], record.get("gen_core", False))
    return record.get("gen", 0)


def replay(n: int, banner: str | None, ignoring: bool) -> int:
    """Pass N's banner, what it printed, then its own ending."""
    if not ignoring and failed_before(n):
        return 0
    record = load(n)
    try:
        if banner is not None:
            emit(1, (banner + "\n").encode())
        with (STATE / f"{n}.log").open("rb") as log:
            while header := log.read(5):
                emit(header[0], log.read(int.from_bytes(header[1:], "big")))
    except OSError as exc:
        print(f"engine pass {n}: its transcript could not be printed ({exc})", file=sys.stderr)
        (STATE / f"{n}.stop").touch()
        return 1
    if record.get("exit") or record.get("signal"):
        (STATE / f"{n}.stop").touch()
    if record.get("signal"):
        reraise(record["signal"], record.get("core", False))
    return record.get("exit", 0)


def reraise(signum: int, core: bool) -> None:
    """End as the recorded process ended: by its signal, dumping core only if it did. A death that did not dump is
    re-raised non-dumpable (prctl PR_SET_DUMPABLE 0), which suppresses the dump whatever the core limits and the
    core_pattern, piped or file."""
    if not core:
        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
    if signum != signal.SIGKILL:
        signal.signal(signum, signal.SIG_DFL)
    os.chdir(STATE)  # a relative file core_pattern writes this process's core here, never over the simulator's
    os.kill(os.getpid(), signum)


def main() -> int:
    """Run or replay one pass, as the command line names it."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--ignore-errors", action="store_true", help="make runs with -i")
    sub = parser.add_subparsers(dest="what", required=True)
    one = sub.add_parser("run")
    one.add_argument("n", type=int, choices=range(4))
    one.add_argument("--mkdir")
    one.add_argument("--gen")
    one.add_argument("--shell", help="the serial recipe's own line, run through /bin/sh")
    one.add_argument("argv", nargs="*")
    gen = sub.add_parser("replay-gen")
    gen.add_argument("n", type=int, choices=range(4))
    show = sub.add_parser("replay")
    show.add_argument("n", type=int, choices=range(4))
    show.add_argument("--banner")
    args = parser.parse_args()
    if args.what == "run":
        if bool(args.shell) == bool(args.argv):
            parser.error("run takes either --shell COMMAND or -- SIMULATOR [ARG...]")
        argv = ["/bin/sh", "-c", args.shell] if args.shell else args.argv
        return run(args.n, args.mkdir, args.gen, argv, args.ignore_errors)
    if args.what == "replay-gen":
        return replay_gen(args.n, args.ignore_errors)
    return replay(args.n, args.banner, args.ignore_errors)


if __name__ == "__main__":
    sys.exit(main())
