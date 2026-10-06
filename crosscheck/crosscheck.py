#!/usr/bin/env python3
"""Independent cross-check of acsearch's capped components (no code shared with acsearch.cpp or make_cert.py).

Words are tuples over {1, -1, 2, -2} (x, x^-1, y, y^-1).  A class is a pair of cyclic words up to rotation, inversion
of either word, swapping, and the 8 signed letter permutations (the quotient used by acsearch).

Test E (exact graph, SAIR move semantics): breadth-first search of the exact-word component of a presentation under
the 14 moves of verifier.core.apply_move (SAIR ACC repository, imported, not reimplemented), keeping states of total
exact length <= cap.  Every exact state is projected to its class.  Pass = every projected class lies in acsearch's
dumped component at the same cap (the projection claim that the lower bounds rest on).

Test Q (quotient graph, own move generation): breadth-first search over classes with neighbours
  CR(rot_i(u) c rot_j(v^s) c^-1)  for all rotations i, j, s = +-1 and ALL reduced c with |c| <= (cap - |u| - |v|) / 2
(no junction-free restriction), keeping classes of total length <= cap.  Pass = same class set as acsearch's dump.

States with an empty relator are legal in SAIR's move set but are not classes here; E reports any it meets as
a failure (for presentations with abelianisation determinant +-1, such as all those tested, they cannot occur).

usage: crosscheck.py E|Q <start u|v> <cap> <acsearch .keys dump>     (SAIR repo: ./sair-ac or $SAIR_REPO)
The dump must come from a complete acsearch run: <dump>.log (same stem) must contain "complete=1".
"""
import os, re, sys, struct, time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.environ.get("SAIR_REPO", os.path.join(HERE, "sair-ac")), "competition", "tools"))

LET = {"x": 1, "X": -1, "y": 2, "Y": -2}
CODE = {0: 1, 1: -1, 2: 2, 3: -2}  # acsearch letter codes


def reduce(w):
    out = []
    for a in w:
        if out and out[-1] == -a:
            out.pop()
        else:
            out.append(a)
    return tuple(out)


def cyc(w):
    w = reduce(w)
    i, j = 0, len(w)
    while j - i >= 2 and w[i] == -w[j - 1]:
        i += 1; j -= 1
    return w[i:j]


def inv(w):
    return tuple(-a for a in reversed(w))


PHIS = []
for sx in (1, -1):
    for sy in (1, -1):
        for sw in (False, True):
            m = {1: sx * (2 if sw else 1), 2: sy * (1 if sw else 2)}
            PHIS.append(lambda w, m=m: tuple(m[abs(a)] * (1 if a > 0 else -1) for a in w))


def cyc_canon(w):
    best = None
    for z in (w, inv(w)):
        for k in range(len(z)):
            t = z[k:] + z[:k]
            if best is None or t < best:
                best = t
    return (len(w), best)


def klass(u, v):
    u, v = cyc(u), cyc(v)
    best = None
    for f in PHIS:
        a, b = cyc_canon(f(u)), cyc_canon(f(v))
        k = (a, b) if a <= b else (b, a)
        if best is None or k < best:
            best = k
    return best


def parse(s):
    return tuple(LET[c] for c in s)


def load_keys(fn):
    """acsearch --dump: sorted 128-bit keys, little endian; layout from acsearch.cpp mkkey (lengths at bits 122/116,
    letters 2 bits each, first word above the second).  Only this decoding is taken from acsearch."""
    out = set()
    data = open(fn, "rb").read()
    assert len(data) % 16 == 0, "truncated dump"
    for off in range(0, len(data), 16):
        lo, hi = struct.unpack_from("<QQ", data, off)
        k = (hi << 64) | lo
        na, nb = k >> 122, (k >> 116) & 63
        b = [CODE[(k >> (2 * (nb - 1 - i))) & 3] for i in range(nb)]
        a = [CODE[(k >> (2 * (nb + na - 1 - i))) & 3] for i in range(na)]
        out.add(klass(tuple(a), tuple(b)))
    if len(out) != len(data) // 16:
        raise SystemExit(f"FAIL: {len(data) // 16} dump records decode to {len(out)} classes (duplicates)")
    return out


def test_exact(start, cap, comp):
    from verifier.core import apply_move
    s0 = tuple(reduce(parse(w)) for w in start.split("|"))
    seen = {s0}; dq = deque([s0]); empty = 0
    while dq:
        s = dq.popleft()
        for m in range(14):
            t = apply_move(s, m)
            if len(t[0]) + len(t[1]) > cap or t in seen:
                continue
            seen.add(t)
            if not t[0] or not t[1]:
                empty += 1  # legal SAIR state, not a class: counted as a failure, not expanded
            else:
                dq.append(t)
    proj = {klass(*s) for s in seen if s[0] and s[1]}
    missing = proj - comp
    print(f"E start={start} cap={cap}: exact states {len(seen)}, empty-relator states {empty}, projected classes "
          f"{len(proj)}, acsearch classes {len(comp)}, projected-not-in-acsearch {len(missing)}")
    for k in list(missing)[:5]:
        print("  missing", k)
    return not missing and not empty


_W = {}


def words_upto(n):
    if n not in _W:
        res = [()]; layer = [()]
        for _ in range(n):
            layer = [w + (a,) for w in layer for a in (1, -1, 2, -2) if not w or w[-1] != -a]
            res += layer
        _W[n] = res
    return _W[n]


def test_quotient(start, cap, comp):
    u0, v0 = (cyc(parse(w)) for w in start.split("|"))
    k0 = klass(u0, v0); rep = {k0: (u0, v0)}; dq = deque([k0])
    while dq:
        k = dq.popleft(); u, v = rep[k]
        cs = words_upto(max(0, (cap - len(u) - len(v)) // 2))
        for A, B in ((u, v), (v, u)):
            for Bs in (B, inv(B)):
                for i in range(len(A)):
                    Ar = A[i:] + A[:i]
                    for j in range(len(Bs)):
                        Br = Bs[j:] + Bs[:j]
                        for c in cs:
                            w = cyc(Ar + c + Br + inv(c))
                            if not w or len(w) + len(B) > cap:
                                continue
                            nk = klass(w, B)
                            if nk not in rep:
                                rep[nk] = (w, B); dq.append(nk)
    got = set(rep)
    print(f"Q start={start} cap={cap}: own classes {len(got)}, acsearch classes {len(comp)}, "
          f"own-not-acsearch {len(got - comp)}, acsearch-not-own {len(comp - got)}")
    return got == comp


if __name__ == "__main__":
    mode, start, cap, keys = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    if mode not in ("E", "Q"):
        raise SystemExit("mode must be E or Q")
    if sum(len(cyc(parse(w))) for w in start.split("|")) > cap:
        raise SystemExit("start is longer than the cap")
    log = keys[:-len(".keys")] + ".log"
    if not re.search(r"RESULT .*cap=%d .*complete=1 " % cap, open(log).read()):
        raise SystemExit(f"{log}: not a complete acsearch run at cap {cap}")
    t0 = time.time(); comp = load_keys(keys)
    ok = (test_exact if mode == "E" else test_quotient)(start, cap, comp)
    print("PASS" if ok else "FAIL", f"{time.time() - t0:.0f}s")
    sys.exit(0 if ok else 1)
