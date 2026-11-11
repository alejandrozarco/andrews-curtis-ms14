#!/bin/bash
# Reproduces the test tables in README.md (section 5).  Dumps are written to $D (scratch), never here.
# Usage: [ACSEARCH=path/to/acsearch] [SCRATCH=dir] closure/run_tests.sh > test_log.txt 2>&1
# (no set -u: bash 3.2 treats empty arrays as unbound)
HERE="$(cd "$(dirname "$0")" && pwd)"
D="${SCRATCH:-$PWD/closure-scratch}"
ENG="${ACSEARCH:-$HERE/../acsearch}"   # built from acsearch.cpp
CC=$D/closure_check
P1='XyyxYYY|XXXYxxy'; P2='XyyxYYY|XXXYxxY'; AK3='xxxYYYY|xyxYXY'
T=(--target 'x|y' --target "$AK3" --target "$P1" --target "$P2")
mkdir -p $D
c++ -O2 -std=c++17 -pthread -o $CC "$HERE/closure_check.cpp" || exit 1

dump() {  # name start cap conj
  [ -f $D/$1.keys ] || nice -n 19 $ENG --start "$2" --cap $3 --conj $4 --threads 1 --maxstates 50000000 --dump --out $D/$1 2> $D/$1.log
  echo "engine: $(grep RESULT $D/$1.log)"
}
check() {  # name start cap [extra args]
  local n=$1 s=$2 c=$3; shift 3
  echo "---- check $n  (--cap $c --start '$s' $*)"
  nice -n 19 $CC --keys $D/$n.keys --cap $c --start "$s" "${T[@]}" --threads 2 "$@" \
    | grep -v '^  total' | grep -v '^canonicalisation' | grep -v '^keys read'
}
drop() {  # src dst index|maxlen seed : write a copy of src without one key
  python3 -I -c '
import sys, random
src, dst, mode, seed = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
b = open(src, "rb").read(); n = len(b)//16
keys = [int.from_bytes(b[16*i:16*i+16], "little") for i in range(n)]
tot = [(k >> 122) + ((k >> 116) & 63) for k in keys]
L = "xXyY"
def dec(k):
    na, nb = k >> 122, (k >> 116) & 63
    a = "".join(L[(k >> (2*(nb+na-1-i))) & 3] for i in range(na))
    bb = "".join(L[(k >> (2*(nb-1-i))) & 3] for i in range(nb))
    return a + "|" + bb
rng = random.Random(seed)
cand = [i for i in range(n) if tot[i] > min(tot)]          # never the start (unique class of min total here)
if mode == "maxlen": cand = [i for i in cand if tot[i] == max(tot)]
i = rng.choice(cand)
open(dst, "wb").write(b[:16*i] + b[16*i+16:])
print("removed key #%d of %d: %s (total %d)" % (i, n, dec(keys[i]), tot[i]))
' "$@"
}

echo "=== 1. positive runs"
for c in 20 21 22 23 24; do dump P1_c$c "$P1" $c $((c/2)); X=(); [ $c -le 22 ] && X=(--exact-bfs --selftest 300); check P1_c$c "$P1" $c "${X[@]}"; done
for c in 20 21 22 23 24; do dump P2_c$c "$P2" $c $((c/2)); X=(); [ $c -le 21 ] && X=(--exact-bfs --selftest 300); check P2_c$c "$P2" $c "${X[@]}"; done
for c in 17 18 19 20 21; do dump AK3_c$c "$AK3" $c $((c/2)); X=(); [ $c -le 19 ] && X=(--exact-bfs --selftest 300); check AK3_c$c "$AK3" $c "${X[@]}"; done

echo "=== 1b. nonempty conjugators: short start xxY|xyxYXY (determinant 1) at cap 14, where (N) moves with |e| up to 5 occur"
S5='xxY|xyxYXY'
dump S5_c14 "$S5" 14 7; check S5_c14 "$S5" 14 --exact-bfs --selftest 300
echo "=== 1c. negative: the same start with the conjugator bound cut to 0..4 (each must FAIL)"
for k in 0 1 2 3 4; do dump S5_c14_k$k "$S5" 14 $k; check S5_c14_k$k "$S5" 14; done

echo "=== 2a. negative: --conj 0 at cap 24"
dump P1_c24_k0 "$P1" 24 0; check P1_c24_k0 "$P1" 24
dump P2_c24_k0 "$P2" 24 0; check P2_c24_k0 "$P2" 24

echo "=== 2b. negative: one class removed"
for seed in 1 2 3; do drop $D/P1_c22.keys $D/P1_c22_drop$seed.keys rand $seed; check P1_c22_drop$seed "$P1" 22; done
drop $D/P1_c22.keys $D/P1_c22_dropmax.keys maxlen 7; check P1_c22_dropmax "$P1" 22
drop $D/P2_c24.keys $D/P2_c24_dropmax.keys maxlen 11; check P2_c24_dropmax "$P2" 24
drop $D/AK3_c21.keys $D/AK3_c21_drop5.keys rand 5; check AK3_c21_drop5 "$AK3" 21

echo "=== 2c. negative: cap-22 dump checked at cap 23"
check P1_c22 "$P1" 23
check P2_c22 "$P2" 23

echo "=== 3. reference dumps (read-only)"
R="$HERE/../runs"
for f in val_P1_c24 val_P1_c24_k0; do
  echo "---- check $f"
  nice -n 19 $CC --keys $R/$f.keys --cap 24 --start "$P1" "${T[@]}" --threads 2 | grep -v '^  total' | grep -v '^canonicalisation' | grep -v '^keys read'
done

echo "=== 4. timing"
dump P2_c25 "$P2" 25 12
for t in 1 2; do check P2_c25 "$P2" 25 --threads $t | grep -E "^----|closure time|RESULT"; done
for L in 24 32; do
  echo "---- bench: 2M random classes of total L-1..L, L=$L, 1 thread (timing only; all lookups miss)"
  nice -n 19 $CC --bench 2000000 --cap $L --start "$P1" --threads 1 | grep -E "closure: [0-9]+ move|closure time"
done
echo "---- bench: 10M random classes, L=32, 2 threads"
nice -n 19 $CC --bench 10000000 --cap 32 --start "$P1" --threads 2 | grep -E "closure: [0-9]+ move|closure time|canonicalisation"
