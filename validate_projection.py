#!/usr/bin/env python3
"""Empirical check of the projection claim: random exact-word elementary AC walks from P1 with total length <= CAP
(moves: invert, mul, single-letter conj, all with free reduction; no cyclic reduction) must project
(cyclic reduction + canonical form mod rotation/inversion/swap/phi) into acsearch's component at the same cap."""
import random, struct, sys
import verify as V, make_cert as M
CAP = int(sys.argv[1]) if len(sys.argv) > 1 else 24
keys = open("runs/val_P1_c%d.keys" % CAP, "rb").read()
comp = set()
for off in range(0, len(keys), 16):
    lo, hi = struct.unpack_from("<QQ", keys, off)
    k = (hi << 64) | lo
    na, nb = k >> 122, (k >> 116) & 63
    L = k & ((1 << 116) - 1)
    letters = [(L >> (2 * (na + nb - 1 - t))) & 3 for t in range(na + nb)]
    w = [[1, -1, 2, -2][l] for l in letters]
    comp.add(M.canon([w[:na], w[na:]]))
print("component size", len(comp))
rnd = random.Random(7)
S0 = [M.parse("XyyxYYY"), M.parse("XXXYxxy")]
checked = 0
for walk in range(300):
    S = [list(r) for r in S0]
    for step in range(400):
        i = rnd.randrange(2); k = rnd.randrange(3)
        mv = ["invert", i] if k == 0 else ["mul", i, 1 - i, rnd.choice([1, -1])] if k == 1 else ["conj", i, rnd.choice([1, -1, 2, -2])]
        T = V.apply(S, mv, 2)
        if sum(map(len, T)) > CAP or not all(T):
            continue
        S = T
        c = M.canon([M.cyc_red(S[0]), M.cyc_red(S[1])])
        assert c in comp, ("projection escaped the component", S)
        checked += 1
print("OK: %d projected exact states, all inside the cap-%d component" % (checked, CAP))

# Targeted test: exact states (a u a^-1, b v b^-1) for component representatives {u,v}, random short a, b,
# within the cap; apply every multiplication move and check the projection stays in the component.
reps = []
for off in range(0, len(keys), 16):
    lo, hi = struct.unpack_from("<QQ", keys, off)
    k = (hi << 64) | lo
    na, nb = k >> 122, (k >> 116) & 63
    L = k & ((1 << 116) - 1)
    w = [[1, -1, 2, -2][(L >> (2 * (na + nb - 1 - t))) & 3] for t in range(na + nb)]
    reps.append([w[:na], w[na:]])
reps = [r for r in reps if CAP - len(r[0]) - len(r[1]) >= 4]
bad = tested = 0
for trial in range(100000):
    u, v = rnd.choice(reps)
    slack = CAP - len(u) - len(v)
    if slack < 2:
        continue
    def rw(n):
        out = []
        while len(out) < n:
            g = rnd.choice([1, -1, 2, -2])
            if not out or out[-1] != -g:
                out.append(g)
        return out
    a = rw(rnd.randint(0, slack // 2)); b = rw(rnd.randint(0, (slack - 2 * len(a)) // 2))
    S = [V.reduce_word(a + u + V.inverse(a)), V.reduce_word(b + v + V.inverse(b))]
    for i in (0, 1):
        for s in (1, -1):
            T = V.apply(S, ["mul", i, 1 - i, s], 2)
            if sum(map(len, T)) > CAP or not all(T):
                continue
            tested += 1
            if M.canon([M.cyc_red(T[0]), M.cyc_red(T[1])]) not in comp:
                bad += 1
print("targeted: %d multiplications from conjugated exact states tested, %d escaped the component" % (tested, bad))
