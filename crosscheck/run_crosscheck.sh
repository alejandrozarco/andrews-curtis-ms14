#!/bin/bash
# Standalone cross-check driver (nice 19, <= 2 jobs). Writes results.txt, then DONE (all outcomes as expected) or FAIL.
# usage: [SAIR_REPO=<SAIR ACC repo>] run_crosscheck.sh <acsearch binary> <workdir>
AC=$(cd "$(dirname "$1")" && pwd)/$(basename "$1"); WD=$2; X="$(cd "$(dirname "$0")" && pwd)/crosscheck.py"
[ -n "$SAIR_REPO" ] && export SAIR_REPO=$(cd "$SAIR_REPO" && pwd)   # absolute, since we cd into the workdir
mkdir -p $WD; cd $WD
dump() { nice -n 19 $AC --start "$4" --target "x|y" --cap $2 --conj $3 --threads 1 --out $1_c$2_k$3 --dump > $1_c$2_k$3.log 2>&1; }
job() { # name start cap mode K expected
  dump $1 $3 $5 "$2"; r=$(nice -n 19 python3 $X $4 "$2" $3 $1_c$3_k$5.keys 2>&1 | tr '\n' ' ')
  echo "[$1 K=$5 expect $6] $r"; }
export AC WD X; export -f dump job
cat <<'L' | xargs -P 2 -L 1 bash -c 'job "$@"' _ > results.txt 2>&1
P1 XyyxYYY|XXXYxxy 24 Q 8 PASS
P2 XyyxYYY|XXXYxxY 24 Q 8 PASS
C3 xxyXy|xyyyyyxYY 22 Q 8 PASS
C4 xxxxyXy|xyyyxYY 24 Q 8 PASS
C6 xxyxxYY|xyXYYXy 24 Q 8 PASS
AK3 xxxYYYY|xyxYXY 21 Q 8 PASS
P1 XyyxYYY|XXXYxxy 24 Q 0 FAIL
P2 XyyxYYY|XXXYxxY 24 Q 0 FAIL
P1 XyyxYYY|XXXYxxy 20 E 8 PASS
P2 XyyxYYY|XXXYxxY 20 E 8 PASS
C4 xxxxyXy|xyyyxYY 20 E 8 PASS
C6 xxyxxYY|xyXYYXy 20 E 8 PASS
AK3 xxxYYYY|xyxYXY 17 E 8 PASS
L
ok=$(awk '{e=$4; sub(/]/,"",e); if (index($0, " " e " ") || $0 ~ (e " [0-9]+s")) n++} END{print n+0}' results.txt)
if [ "$ok" -eq 13 ]; then echo "DONE $(date)" > DONE; else echo "FAIL $(date) ($ok of 13 as expected)" > FAIL; fi
