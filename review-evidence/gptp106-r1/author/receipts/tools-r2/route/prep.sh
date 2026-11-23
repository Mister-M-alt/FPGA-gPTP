#!/usr/bin/env bash
# prep.sh <name> <1x1|8x8>: the split boot (its provisional image and runtime archives), then the shipping split
# image exported for the integrated route by the 810route lane's route_image.sh recipe, placement directive
# ExtraTimingOpt (the route-1x1 record's selected directive). No Vivado. Writes $W/prep.rc.
set -uo pipefail
B=/data-2/milan/tmp/gptp106-a831; n=$1; shape=$2; L=$B/$n; W=$B/route-$n-$shape; BT=$B/tmp/boot-$n-$shape
case $shape in 1x1) CFG=configs/endstation_ax7101_1x1_tdm8.yaml; STEM=endstation_ax7101_1x1_tdm8;;
               8x8) CFG=configs/endstation_ax7101_8x8.yaml; STEM=endstation_ax7101_8x8;; esac
export PATH=<home-path>/br-milan-rv32/host/bin:$VALIDATION_TOOLS/pinned-verilator-5.050:$VALIDATION_TOOLS/sv2v-v0.0.12:$VALIDATION_STORAGE/scratch/a662/make43/bin:/usr/local/bin:/usr/bin:/bin
export VERILATOR=$VALIDATION_TOOLS/pinned-verilator-5.050/verilator COURSIER_MODE=offline SBT_OPTS=-Dsbt.offline=true
export PYTHONHASHSEED=0 LITEX_ENV_CC_TRIPLE=riscv32-linux TMPDIR=$B/tmp MAKEFLAGS="-j8 --no-print-directory"
PY=<home-path>/litex-milan/venv/bin/python3
FLOW=(--synth-directive AreaOptimized_high --opt-directive ExploreArea --place-directive ExtraTimingOpt --vivado-max-threads 32)
mkdir -p "$W"; cd "$L" || exit 3
echo "head $(git rev-parse HEAD) gptp-processor $(git -C gptp-processor rev-parse HEAD) tree: $(git status --porcelain | tr '\n' ' ')"
date -Iseconds
"$PY" -B tb/verilator/ctrl_split_boot/run.py --build-dir "$BT" --shape "$STEM" > "$W/boot.log" 2>&1
rc=$?; tail -3 "$W/boot.log"; [ $rc -eq 0 ] || { echo "boot rc=$rc"; echo 4 > "$W/prep.rc"; exit 4; }
date -Iseconds
set -e
/usr/bin/python3 sw/builder/endstation_builder.py "$CFG" --placement split > "$W/builder.log" 2>&1
mapfile -t ARGV < <(/usr/bin/python3 -c "import json,sys; print('\n'.join(json.load(open(sys.argv[1]))['argv']))" sw/builder/out/$STEM/soc_params.json)
FW=$(printf '%s\n' "${ARGV[@]}" | grep -A1 -x -- --ctrl-firmware | tail -1)
echo "recipe argv names --ctrl-firmware $FW"
STANDIN=$BT/image-provisional/ctrl_app.elf
STAND_ARGV=("${ARGV[@]}"); for i in "${!STAND_ARGV[@]}"; do [ "${STAND_ARGV[$i]}" = "$FW" ] && STAND_ARGV[$i]=$STANDIN; done
rm -rf "$W/standin" "$W/flash-map" "$W/image" "$W/split"
(cd sw/litex && "$PY" milan_soc.py "${STAND_ARGV[@]}" --entity-gen-dir "$L/configs/generated/$STEM" "${FLOW[@]}" --no-compile-software --output-dir "$W/standin" > "$W/standin.log" 2>&1)
"$PY" -B sw/firmware/ctrl_nvm/plat/gen_flash_port.py --csr-csv "$W/standin/csr.csv" --csr-h "$W/standin/software/include/generated/csr.h" --out "$W/flash-map"
"$PY" -B sw/firmware/ctrl/test/ctrl_plat_image.py --config "$CFG" --interfaces 1 --csr-csv "$W/standin/csr.csv" --flash-map "$W/flash-map" --output "$W/image" --libc "$BT/runtime/libc.a" --compiler-runtime "$BT/runtime/libcompiler_rt.a"
cp "$W/image/ctrl_app.elf" "$FW"
(cd sw/litex && "$PY" milan_soc.py "${ARGV[@]}" --entity-gen-dir "$L/configs/generated/$STEM" "${FLOW[@]}" --no-compile-software --output-dir "$W/split" > "$W/split.log" 2>&1)
tail -2 "$W/split.log"
diff <(grep -E '^(csr_base|csr_register|constant|memory_region),' "$W/standin/csr.csv" | grep -v -E '^memory_region,(rom|sram),') \
     <(grep -E '^(csr_base|csr_register|constant|memory_region),' "$W/split/csr.csv" | grep -v -E '^memory_region,(rom|sram),') && echo "csr map: the image's equals the stand-in's"
"$PY" sw/litex/check_image_identity.py "$W/split"
/usr/bin/python3 syn/ooc/pp_baseline.py "$W/split/gateware" --placement full-split --single-thread-synthesis
grep -c "place_design -directive ExtraTimingOpt" "$W/split/gateware/baseline_integrated.tcl"
echo "gptp ucode image: $(sha256sum sw/builder/out/$STEM/gptp_ucode.hex | cut -c1-16)"
date -Iseconds; echo 0 > "$W/prep.rc"; echo done
