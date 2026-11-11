#!/bin/bash
# Reproduces closure/results/: dumps the published components with acsearch and checks each with closure_check.
# Usage: [ACSEARCH=path/to/acsearch] [SCRATCH=dir] closure/run_large.sh
# Needs about 2 GB of memory per run and 1-2 GB of disk per dump; about 2 hours in total on one thread.
HERE="$(cd "$(dirname "$0")" && pwd)"
D="${SCRATCH:-$PWD/closure-scratch}"
ENG="${ACSEARCH:-$HERE/../acsearch}"   # built from acsearch.cpp
OUT="$HERE/results"
mkdir -p "$D" "$OUT"
c++ -O2 -std=c++17 -pthread -o "$D/closure_check" "$HERE/closure_check.cpp" || exit 1
T=(--target 'x|y' --target 'xxxYYYY|xyxYXY' --target 'XyyxYYY|XXXYxxy' --target 'XyyxYYY|XXXYxxY'
   --target 'xxyXy|xyyyyyxYY' --target 'xxxxyXy|xyyyxYY' --target 'xxyxxYY|xyXYYXy')
run() {  # name start cap conj
  nice -n 19 "$ENG" --start "$2" --cap $3 --conj $4 --threads 1 --maxstates 100000000 --dump --out "$D/dump_$1" \
    > "$OUT/dump_$1.log" 2>&1
  nice -n 19 "$D/closure_check" --keys "$D/dump_$1.keys" --cap $3 --start "$2" "${T[@]}" --threads 1 > "$OUT/$1.txt" 2>&1
  (cd "$HERE" && shasum -a 256 closure_check.cpp) >> "$OUT/$1.txt"
  (cd "$D" && shasum -a 256 "dump_$1.keys") >> "$OUT/$1.txt"
  echo "$1 $(grep '^RESULT' "$OUT/$1.txt")"
}
run C4_c32 'xxxxyXy|xyyyxYY' 32 9
run C3_c30 'xxyXy|xyyyyyxYY' 30 8
run P1_c32 'XyyxYYY|XXXYxxy' 32 9
run P2_c32 'XyyxYYY|XXXYxxY' 32 9
