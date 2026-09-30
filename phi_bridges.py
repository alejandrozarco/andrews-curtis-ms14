#!/usr/bin/env python3
"""Build explicit ledgers  phi_p(AK3) -> AK3  for the 8 signed letter permutations phi_p
(p bit0: x->x^-1, bit1: y->y^-1, bit2: then swap x<->y), from acsearch --nosym chains
(runs/ak3_phi_c20.paths).  Output: certs/phi/phi{p}_ak3_to_ak3.json, each verified by verify.py.
This makes the phi-quotient used by acsearch fully explicit (cf. Panteleev-Ushakov)."""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify as V
import make_cert as M

AK3 = "xxxYYYY|xyxYXY"
os.makedirs("certs/phi", exist_ok=True)
paths = M.read_paths("runs/ak3_phi_c20.paths")
T = [M.parse(w) for w in AK3.split("|")]
for p in range(8):
    tgt = [M.phi(T[0], p), M.phi(T[1], p)]
    out = "certs/phi/phi%d_ak3_to_ak3.json" % p
    if tuple(tuple(r) for r in tgt) in V.orbit(T):
        cert = {"generators": 2, "claim": "AC_equivalence", "initial": tgt, "target": T, "moves": []}
    else:
        idx = [k for k, P in enumerate(paths) if M.canon(P["states"][-1], False) == M.canon(tgt, False)][0]
        tmp = "runs/_phi%d_fwd.json" % p
        subprocess.check_call([sys.executable, "make_cert.py", "--paths", "runs/ak3_phi_c20.paths",
                               "--which", str(idx), "--start", AK3, "--target",
                               "%s|%s" % tuple("".join("xXyY"[{1: 0, -1: 1, 2: 2, -2: 3}[a]] for a in w) for w in tgt),
                               "--nosym", "--cap", "20", "--conj", "0", "--out", tmp], stdout=subprocess.DEVNULL)
        fwd = json.load(open(tmp))
        back = []
        for mv in reversed(fwd["moves"]):
            back.append(mv if mv[0] == "invert" else ["mul", mv[1], mv[2], -mv[3]] if mv[0] == "mul" else ["conj", mv[1], -mv[2]])
        cert = {"generators": 2, "claim": "AC_equivalence", "initial": fwd["reached"], "target": T,
                "reached": fwd["initial"], "moves": back}
        os.remove(tmp)
    ok, msg, st = V.verify(cert)
    assert ok, msg
    json.dump(cert, open(out, "w"))
    print(out, msg, st["moves"], "moves, peak", st["peak_total"])
