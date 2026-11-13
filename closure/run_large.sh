#!/bin/bash
# Reproduces closure/results/: dumps the published components with acsearch and checks each with closure_check.
# Usage: [ACSEARCH=path/to/acsearch] [SCRATCH=dir] closure/run_large.sh
# Needs about 2 GB of memory and 1-2 GB of disk per run, except C3 at cap 31 (about 6 GB of memory, 3.2 GB of disk,
# about 3.5 hours); about 6 hours in total on one thread.
HERE="$(cd "$(dirname "$0")" && pwd)"
D="${SCRATCH:-$PWD/closure-scratch}"
ENG="${ACSEARCH:-$HERE/../acsearch}"   # built from acsearch.cpp
OUT="$HERE/results"
mkdir -p "$D" "$OUT"
c++ -O2 -std=c++17 -pthread -o "$D/closure_check" "$HERE/closure_check.cpp" || exit 1
# For C3 at cap 31: acsearch.cpp with one line changed so that --dump sorts the keys in place (after freeing the hash
# table) instead of sorting a copy; this lowers peak memory from about 9 GB to about 6 GB and does not change the dump.
sed 's|vector<u128> ks = T.keys; sort|vector<u32>().swap(T.slot); vector<u32>().swap(T.parent); vector<u128>\& ks = T.keys; sort|' \
  "$HERE/../acsearch.cpp" > "$D/acsearch_inplace.cpp"
c++ -O2 -std=c++17 -pthread -o "$D/acsearch_inplace" "$D/acsearch_inplace.cpp" || exit 1
T=(--target 'x|y' --target 'xxxYYYY|xyxYXY' --target 'XyyxYYY|XXXYxxy' --target 'XyyxYYY|XXXYxxY'
   --target 'xxyXy|xyyyyyxYY' --target 'xxxxyXy|xyyyxYY' --target 'xxyxxYY|xyXYYXy')
run() {  # name start cap conj [engine] [maxstates]
  nice -n 19 "${5:-$ENG}" --start "$2" --cap $3 --conj $4 --threads 1 --maxstates ${6:-100000000} --dump --out "$D/dump_$1" \
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
run C3_c31 'xxyXy|xyyyyyxYY' 31 8 "$D/acsearch_inplace" 200000000
