# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Pin the engine PHC boundary after removal of the unused ns input."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = {
    "hdl/top/KL_gptp_engine.sv": ("phc_ns_i", "disp_ts1_r", ".disp_ts1_i"),
    "hdl/ucpu/KL_gptp_ucpu.sv": ("disp_ts1_i", "S_PRE0"),
    "hdl/ucode/gen_gptp_ucode.py": ("RTS1",),
    "bench/arty/bench_arty_top.sv": (".phc_ns_i",),
    "tb/verilator/engine/sim_main.cpp": ("phc_ns_i",),
    "tb/verilator/ucpu/sim_main.cpp": ("disp_ts1_i",),
}

REQUIRED = {
    "hdl/top/KL_gptp_engine.sv": (
        "rx_ts_i",
        "txts_ns_i",
        "phc_addend_we_o",
        "phc_step_we_o",
        "gx_data_r <= {32'd0, ms_now_w};",
    ),
    "bench/arty/bench_arty_top.sv": (
        "rxts_r <= phc_ns_w;",
        "txts_r <= phc_ns_w;",
        ".rx_ts_i",
        ".txts_ns_i",
        ".phc_addend_we_o",
        ".phc_step_we_o",
    ),
}


def main() -> int:
    """The gate: 0 when no removed token has come back and every surviving
    path is still wired, 1 with the file and the token named."""
    failures = []
    for relpath, needles in FORBIDDEN.items():
        text = (ROOT / relpath).read_text(encoding="utf-8")
        failures.extend(
            f"{relpath}: removed token is present: {needle}"
            for needle in needles
            if needle in text
        )

    for relpath, needles in REQUIRED.items():
        text = (ROOT / relpath).read_text(encoding="utf-8")
        failures.extend(
            f"{relpath}: required surviving path is missing: {needle}"
            for needle in needles
            if needle not in text
        )

    if failures:
        print("PHC interface contract: FAIL")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("PHC interface contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
