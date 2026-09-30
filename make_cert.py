#!/usr/bin/env python3
"""
make_cert.py -- turn a chain of canonical states (from acsearch --out X -> X.paths) into an explicit
elementary AC ledger (moves: invert / mul / conj only) and check it with verify.py.

  python3 make_cert.py --paths runs/X.paths [--which 0] --start "XyyxYYY|XXXYxxy" \
        --target "xxxYYYY|xyxYXY" [--conj K] [--prefix-cert A.json] [--suffix-cert B.json] --out certs/NAME.json

The chain may be canonical modulo the 8 signed letter permutations; the ledger starts at the exact
--start presentation and ends at a state in the rotation/inversion/swap orbit of phi(target) for some phi.
If phi != id, a --suffix-cert must be supplied: a verified ledger from phi(target)-orbit to target
(it is appended after an explicit orbit bridge).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify as V  # noqa: E402

LET = {"x": 1, "X": -1, "y": 2, "Y": -2}


def parse(s):
    return V.reduce_word([LET[ch] for ch in s])


def cyc_red(w):
    w = V.reduce_word(w)
    while len(w) > 1 and w[0] == -w[-1]:
        w = w[1:-1]
    return w


def phi(w, p):
    out = []
    for a in w:
        g = abs(a)
        sgn = 1 if a > 0 else -1
        if (p & 1 and g == 1) or (p & 2 and g == 2):
            sgn = -sgn
        if p & 4:
            g = 3 - g
        out.append(sgn * g)
    return out


def canon_word(w):
    best = None
    for u in (w, V.inverse(w)):
        for k in range(len(u)):
            t = tuple(u[k:] + u[:k])
            if best is None or t < best:
                best = t
    return (len(w), best)


def canon(state, sym=True):
    best = None
    for p in (range(8) if sym else [0]):
        a, b = canon_word(phi(state[0], p)), canon_word(phi(state[1], p))
        k = (min(a, b), max(a, b))
        if best is None or k < best:
            best = k
    return best


def rot_moves(S, i, k, moves):
    """rotate S[i] (cyclically reduced) left by k using single-letter conjugations."""
    n = len(S[i])
    k %= n
    if k <= n - k:
        for _ in range(k):
            mv = ["conj", i, -S[i][0]]
            S[:] = V.apply(S, mv, 2)
            moves.append(mv)
    else:
        for _ in range(n - k):
            mv = ["conj", i, S[i][-1]]
            S[:] = V.apply(S, mv, 2)
            moves.append(mv)


def candidates(S, cap, K):
    """yield (which, s, i, j, c, predicted new relator) exactly as acsearch enumerates."""
    for which in (0, 1):
        A, B0 = S[which], S[1 - which]
        budget = cap - len(B0)
        for s in (1, -1):
            B = B0 if s == 1 else V.inverse(B0)
            for i in range(len(A)):
                Ai = A[i:] + A[:i]
                for j in range(len(B)):
                    Bj = B[j:] + B[:j]
                    w = cyc_red(Ai + Bj)
                    if 0 < len(w) <= budget:
                        yield which, s, i, j, [], w
                    maxc = min(K, (budget - len(A) - len(B)) // 2)
                    for k in range(1, maxc + 1):
                        for c in words(k):
                            if c[0] == -Ai[-1] or c[0] == Ai[0] or c[-1] == -Bj[0] or c[-1] == Bj[-1]:
                                continue
                            yield which, s, i, j, c, Ai + c + Bj + V.inverse(c)


def words(k):
    if k == 0:
        yield []
        return
    for w in words(k - 1):
        for a in (1, -1, 2, -2):
            if w and w[-1] == -a:
                continue
            yield w + [a]


def emit(S, which, s, i, j, c):
    """Apply the move via elementary moves; returns list of moves (S updated in place)."""
    moves = []
    ia, ib = which, 1 - which
    rot_moves(S, ia, i, moves)
    if s == -1:
        mv = ["invert", ib]
        S[:] = V.apply(S, mv, 2)
        moves.append(mv)
    rot_moves(S, ib, j, moves)
    for g in reversed(c):
        mv = ["conj", ib, g]
        S[:] = V.apply(S, mv, 2)
        moves.append(mv)
    mv = ["mul", ia, ib, 1]
    S[:] = V.apply(S, mv, 2)
    moves.append(mv)
    while len(S[ia]) > 1 and S[ia][0] == -S[ia][-1]:
        mv = ["conj", ia, -S[ia][0]]
        S[:] = V.apply(S, mv, 2)
        moves.append(mv)
    for g in c:
        mv = ["conj", ib, -g]
        S[:] = V.apply(S, mv, 2)
        moves.append(mv)
    return moves


def read_paths(fn):
    paths, cur = [], None
    for line in open(fn):
        line = line.strip()
        if line.startswith("# target"):
            cur = {"hdr": line, "states": []}
        elif line == "# end":
            paths.append(cur)
            cur = None
        elif cur is not None and line:
            a, b = line.split("|")
            cur["states"].append([parse(a), parse(b)])
    return paths


def orbit_bridge(S, T):
    """moves (inversions, rotations, swap) taking cyclically-reduced S to exactly T, where T is in the
    swap/inversion/rotation orbit of S.  Returns moves; S updated."""
    moves = []

    def do(mv):
        S[:] = V.apply(S, mv, 2)
        moves.append(mv)
    # decide whether a swap is needed
    def match(w, t):
        for inv in (False, True):
            u = V.inverse(w) if inv else w
            for k in range(len(u)):
                if u[k:] + u[:k] == t:
                    return inv, k
        return None
    if match(S[0], T[0]) is None or match(S[1], T[1]) is None:
        # swap: (a,b)->(ab,b)->(ab,a^-1)->(b',a^-1) [b' conj of b] -> cyclically reduce -> (.., a)
        do(["mul", 0, 1, 1])
        do(["mul", 1, 0, -1])       # b (ab)^-1 = a^-1
        do(["mul", 0, 1, 1])        # ab a^-1
        while len(S[0]) > 1 and S[0][0] == -S[0][-1]:
            do(["conj", 0, -S[0][0]])
        do(["invert", 1])
    for r in (0, 1):
        m = match(S[r], T[r])
        assert m is not None, (S, T)
        inv, k = m
        if inv:
            do(["invert", r])
        m = match(S[r], T[r])
        rot_moves(S, r, m[1], moves)
        assert S[r] == T[r]
    return moves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", required=True)
    ap.add_argument("--which", type=int, default=0)
    ap.add_argument("--start", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--cap", type=int, default=60)
    ap.add_argument("--conj", type=int, default=3)
    ap.add_argument("--nosym", action="store_true")
    ap.add_argument("--suffix-cert", help="ledger from (an orbit member of) phi(target) to target")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sym = not a.nosym
    P = read_paths(a.paths)[a.which]
    chain = P["states"]
    S = [cyc_red(w) for w in map(parse, a.start.split("|"))]
    start = [list(r) for r in S]
    assert canon(S, sym) == canon(chain[0], sym), "start does not match chain[0]"
    moves = []
    for step in range(1, len(chain)):
        want = canon(chain[step], sym)
        found = None
        for (which, s, i, j, c, w) in candidates(S, a.cap, a.conj):
            new = [None, None]
            new[which] = w
            new[1 - which] = S[1 - which] if s == 1 else V.inverse(S[1 - which])
            if canon(new, sym) == want:
                found = (which, s, i, j, c)
                break
        assert found, "no move realizes step %d" % step
        moves += emit(S, *found)
        assert canon(S, sym) == want, "emitted moves do not reach step %d" % step
    T = [cyc_red(w) for w in map(parse, a.target.split("|"))]
    tail = []
    if tuple(tuple(r) for r in S) not in V.orbit(T):
        p = [q for q in range(8) if tuple(tuple(r) for r in S) in V.orbit([phi(T[0], q), phi(T[1], q)])]
        assert p, "endpoint not in any phi-orbit of target"
        print("endpoint is in the orbit of phi_%d(target)" % p[0])
        if not a.suffix_cert:
            sys.exit("need --suffix-cert from phi_%d(target) to target" % p[0])
        suf = json.load(open(a.suffix_cert))
        moves += orbit_bridge(S, [V.reduce_word(r) for r in suf["initial"]])
        for mv in suf["moves"]:
            S = V.apply(S, mv, 2)
            moves.append(mv)
        assert tuple(tuple(r) for r in S) in V.orbit(T)
    cert = {"generators": 2, "claim": "AC_equivalence", "initial": start, "target": T,
            "reached": S, "moves": moves,
            "provenance": "acsearch chain %s (%s), expanded by make_cert.py" % (a.paths, P["hdr"])}
    ok, msg, st = V.verify(cert)
    print(msg, st and {k: st[k] for k in ("moves", "classical", "peak_total", "peak_single")})
    assert ok
    with open(a.out, "w") as f:
        json.dump(cert, f)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
