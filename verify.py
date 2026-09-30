#!/usr/bin/env python3
"""
verify.py -- independent replay checker for Andrews-Curtis move ledgers (rank 2 or higher).

Standard library only. Written independently of any search code in this repo.

Words: lists of nonzero ints; generator k is k, its inverse is -k (1 = x, 2 = y).
A state is the list of relators (r_1, ..., r_n), each kept freely reduced.

Elementary moves accepted (all are AC moves or finite compositions of AC moves):
  ["invert", i]        r_i <- r_i^{-1}
  ["mul", i, j, s]     r_i <- r_i r_j^s          (i != j, s = +1 / -1)
  ["conj", i, g]       r_i <- g r_i g^{-1}        (g a single signed generator)
  ["cycle", i, k]      r_i <- u^{-1} r_i u, where u is the length-(k mod |r_i|) prefix of r_i
                       (i.e. left rotation by k; a composite of single-letter conjugations)
Every result is freely reduced.  Indices i, j are 0-based.

Certificate JSON fields:
  "initial": list of relators
  "moves":   list of moves
  "claim":   "AC_equivalence" (default) or "trivialization"
  "target":  (equivalence) list of relators; the terminal state must lie in the orbit of the target
             under  relator permutation x relator inversion x cyclic rotation  -- each of which is an
             AC-realizable operation (rotation = conjugation, inversion = move, a swap is the
             composite  (a,b)->(ab,b)->(ab,a^-1)->(b,a^-1)->(b,a)  of elementary moves).
             The terminal relators must be cyclically reduced for this orbit comparison.
  "reached": optional; if present the terminal state must equal it exactly.

Usage:
  python3 verify.py CERT.json [CERT2.json ...]
  python3 verify.py --selftest
Exit status 0 iff every certificate passes.
"""
import itertools
import json
import sys


def reduce_word(w):
    out = []
    for a in w:
        if out and out[-1] == -a:
            out.pop()
        else:
            out.append(a)
    return out


def inverse(w):
    return [-a for a in reversed(w)]


def is_cyclically_reduced(w):
    return len(w) == 0 or (w == reduce_word(w) and (len(w) == 1 or w[0] != -w[-1]))


def apply(state, mv, ngen):
    """Return the new state, or raise ValueError on an illegal / malformed move."""
    if not isinstance(mv, list) or not mv or not isinstance(mv[0], str):
        raise ValueError("malformed move %r" % (mv,))
    op, args = mv[0], mv[1:]
    if not all(type(a) is int for a in args):
        raise ValueError("non-integer argument in %r" % (mv,))
    n = len(state)
    S = [list(r) for r in state]

    def idx(i):
        if not (0 <= i < n):
            raise ValueError("relator index out of range in %r" % (mv,))
        return i

    if op == "invert" and len(args) == 1:
        i = idx(args[0])
        S[i] = inverse(S[i])
    elif op == "mul" and len(args) == 3:
        i, j, s = idx(args[0]), idx(args[1]), args[2]
        if i == j or s not in (1, -1):
            raise ValueError("illegal mul %r" % (mv,))
        S[i] = reduce_word(S[i] + (S[j] if s == 1 else inverse(S[j])))
    elif op == "conj" and len(args) == 2:
        i, g = idx(args[0]), args[1]
        if g == 0 or abs(g) > ngen:
            raise ValueError("illegal conjugator in %r" % (mv,))
        S[i] = reduce_word([g] + S[i] + [-g])
    elif op == "cycle" and len(args) == 2:
        i, k = idx(args[0]), args[1]
        r = S[i]
        if r:
            k %= len(r)
            u = r[:k]
            S[i] = reduce_word(inverse(u) + r + u)
    else:
        raise ValueError("unknown move %r" % (mv,))
    return S


def classical_cost(state, mv):
    if mv[0] == "cycle":
        L = max(len(state[mv[1]]), 1)
        k = mv[2] % L
        return min(k, L - k)
    return 1


def orbit(target):
    """All states obtained from target by permuting relators, inverting any, rotating any."""
    per = []
    for r in target:
        r = list(r)
        opts = set()
        for w in (r, inverse(r)):
            for k in range(max(len(w), 1)):
                opts.add(tuple(w[k:] + w[:k]))
        per.append(opts)
    out = set()
    for perm in itertools.permutations(range(len(target))):
        for combo in itertools.product(*[per[p] for p in perm]):
            out.add(combo)
    return out


def check_words(ws, ngen, name):
    if not isinstance(ws, list):
        raise ValueError("%s must be a list" % name)
    for w in ws:
        if not isinstance(w, list):
            raise ValueError("%s: relator is not a list" % name)
        for a in w:
            if type(a) is not int or a == 0 or abs(a) > ngen:
                raise ValueError("%s: illegal letter %r" % (name, a))


def verify(cert):
    """Returns (ok, message, stats)."""
    try:
        init = cert["initial"]
        ngen = cert.get("generators", len(init))
        if type(ngen) is not int or ngen < 1:
            raise ValueError("bad generators field")
        check_words(init, ngen, "initial")
        if len(init) != ngen:
            raise ValueError("presentation is not balanced")
        moves = cert["moves"]
        if not isinstance(moves, list):
            raise ValueError("moves must be a list")
        claim = cert.get("claim", "AC_equivalence")
        S = [reduce_word(list(r)) for r in init]
        peak = sum(map(len, S))
        peak_single = max(map(len, S))
        classical = 0
        for step, mv in enumerate(moves):
            try:
                c = classical_cost(S, mv) if isinstance(mv, list) and mv and mv[0] == "cycle" \
                    and len(mv) == 3 and type(mv[1]) is int and 0 <= mv[1] < len(S) else 1
                S = apply(S, mv, ngen)
            except ValueError as e:
                return False, "step %d: %s" % (step, e), None
            classical += c
            peak = max(peak, sum(map(len, S)))
            peak_single = max(peak_single, max(map(len, S)))
        stats = dict(moves=len(moves), classical=classical, peak_total=peak,
                     peak_single=peak_single, terminal=S)
        if "reached" in cert:
            check_words(cert["reached"], ngen, "reached")
            if [list(r) for r in cert["reached"]] != S:
                return False, "terminal %r != declared reached %r" % (S, cert["reached"]), stats
        if claim == "trivialization":
            ok = all(len(r) == 1 for r in S) and sorted(abs(r[0]) for r in S) == list(range(1, ngen + 1))
            return ok, ("PASS trivialization" if ok else "terminal %r is not trivial" % (S,)), stats
        if claim != "AC_equivalence":
            raise ValueError("unknown claim %r" % (claim,))
        tgt = cert["target"]
        check_words(tgt, ngen, "target")
        if len(tgt) != ngen:
            raise ValueError("target is not balanced")
        tgt = [reduce_word(list(r)) for r in tgt]
        if not all(is_cyclically_reduced(r) for r in S):
            return False, "terminal relators not cyclically reduced: %r" % (S,), stats
        if not all(is_cyclically_reduced(r) for r in tgt):
            return False, "target relators not cyclically reduced", stats
        if tuple(tuple(r) for r in S) not in orbit(tgt):
            return False, "terminal %r not in swap/inversion/rotation orbit of target %r" % (S, tgt), stats
        return True, "PASS AC-equivalence", stats
    except (KeyError, ValueError, TypeError) as e:
        return False, "malformed certificate: %s" % (e,), None


def selftest():
    import random
    rnd = random.Random(1)
    AK3 = [[1, 1, 1, -2, -2, -2, -2], [1, 2, 1, -2, -1, -2]]
    # 1. empty ledger: AK3 equivalent to a rotated/inverted/swapped copy of itself
    t = [inverse(AK3[1])[2:] + inverse(AK3[1])[:2], AK3[0][3:] + AK3[0][:3]]
    ok, msg, _ = verify({"initial": AK3, "target": t, "moves": []})
    assert ok, msg
    # 2. random scramble then exact inverse ledger returns to start
    for trial in range(200):
        S = [list(r) for r in AK3]
        led = []
        for _ in range(30):
            k = rnd.randrange(4)
            i = rnd.randrange(2)
            if k == 0:
                mv = ["invert", i]
            elif k == 1:
                mv = ["mul", i, 1 - i, rnd.choice([1, -1])]
            else:
                mv = ["conj", i, rnd.choice([1, -1, 2, -2])]
            S = apply(S, mv, 2)
            led.append(mv)
        back = []
        for mv in reversed(led):
            if mv[0] == "invert":
                back.append(mv)
            elif mv[0] == "mul":
                back.append(["mul", mv[1], mv[2], -mv[3]])
            else:
                back.append(["conj", mv[1], -mv[2]])
        ok, msg, _ = verify({"initial": AK3, "target": AK3, "moves": led + back, "reached": AK3})
        assert ok, msg
        # corrupting one move must (almost always) break the exact 'reached' check
        bad = led + back
        j = rnd.randrange(len(bad))
        bad = bad[:j] + [["invert", bad[j][1]]] + bad[j + 1:] if bad[j][0] != "invert" else bad[:j] + bad[j + 1:]
        ok2, _, st = verify({"initial": AK3, "target": AK3, "moves": bad, "reached": AK3})
        # (not asserted false: a corrupted ledger can coincidentally still land on AK3)
    # 3. swap via the 4-move identity + inversion
    a, b = AK3
    led = [["mul", 0, 1, 1], ["mul", 1, 0, -1]]  # (ab, b(ab)^-1 = a^-1)
    S = AK3
    for mv in led:
        S = apply(S, mv, 2)
    assert S[1] == inverse(a)
    # 4. rejections
    for bad in (["mul", 0, 0, 1], ["conj", 0, 3], ["conj", 0, 0], ["mul", 0, 1, 2], ["foo", 0], ["invert", 5],
                ["invert", True]):
        ok, _, _ = verify({"initial": AK3, "target": AK3, "moves": [bad]})
        assert not ok, bad
    ok, _, _ = verify({"initial": [[1, 3], [2]], "target": AK3, "moves": []})
    assert not ok
    ok, _, _ = verify({"initial": AK3, "target": [[1, 1, 1, -2, -2, -2, -2], [1, 2, 1, -2, -1, -1]], "moves": []})
    assert not ok
    # 5. trivialization: <x,y | x y, y> -> <x,y | x, y>
    ok, msg, _ = verify({"initial": [[1, 2], [2]], "moves": [["mul", 0, 1, -1]], "claim": "trivialization"})
    assert ok, msg
    ok, msg, _ = verify({"initial": [[1, 2], [2]], "moves": [], "claim": "trivialization"})
    assert not ok
    # 6. cycle == iterated conjugation
    r = [1, 2, -1, -1, 2, 2]
    s1 = apply([r, [1]], ["cycle", 0, 2], 2)[0]
    s2 = apply(apply([r, [1]], ["conj", 0, -1], 2), ["conj", 0, -2], 2)[0]
    assert s1 == s2 == [-1, -1, 2, 2, 1, 2], (s1, s2)
    print("selftest OK")


def main(argv):
    if len(argv) == 2 and argv[1] == "--selftest":
        selftest()
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    allok = True
    for f in argv[1:]:
        with open(f) as fh:
            cert = json.load(fh)
        ok, msg, st = verify(cert)
        allok &= ok
        extra = ""
        if st:
            extra = " | %d moves (%d classical), peak total %d, peak single %d" % (
                st["moves"], st["classical"], st["peak_total"], st["peak_single"])
        print("%s: %s%s" % (f, msg if ok else "FAIL " + msg, extra))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
