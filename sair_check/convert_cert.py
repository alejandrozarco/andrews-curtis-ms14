#!/usr/bin/env python3
"""
convert_cert.py -- run our Andrews-Curtis certificates through the SAIR ACC
competition's OWN verifier implementation (competition/tools/verifier/core.py),
not just our independent verify.py.

Background
----------
Our certificates (certs/P1_equiv_C6.json and certs/carreras/*.json) are
"AC-equivalence" ledgers in verify.py's own JSON format: a list of elementary
moves ["invert", i] / ["mul", i, j, s] / ["conj", i, g] / ["cycle", i, k] over
TWO relators, taking a declared "initial" presentation to a state that lies in
the swap x inversion x rotation orbit of a declared "target" presentation.
Neither "initial" nor "target" is generally the trivial pair (x, y).

The SAIR competition's Discovery-Track AC verifier (move_spec_version
"ac-r2-v1") replays a different, purely numeric object: a submission is
`challenge_id: [move_id, ...]` where move_id in 0..13 indexes the FROZEN
14-row table in competition/tools/verifier/core.MOVE_TABLE, and a path is
"ok" **only** if it ends at the *exact* ordered pair [[1],[2]] (their fixed
target -- see competition/rules/discovery.md and
competition/tools/verifier/README.md). There is no "check equivalence to an
arbitrary target" mode in their CLI/manifest replay: `core.verify()` hard-
codes `target = tuple(tuple(r) for r in challenge["target_relators"])`, which
for every ac-* challenge is [[1],[2]].

So: our certificates (P1 ~AC C6, MS(3,*) ~AC AK(3), etc.) can never come back
"ok: true" from their official CLI, because none of our targets is (x, y) --
that is expected, not a bug in either tool (see RESULTS.md).  What we CAN and
do check here, per the task, is that our own move sequence, converted move-
for-move into their numeric ac-r2-v1 IDs, replayed with THEIR OWN
`core.apply_move` starting from THEIR OWN official `initial_relators` for the
matching challenge (when the certificate's start is one of the 10,115 official
presentations), is legal at every step and lands -- up to the same swap /
inversion / rotation orbit verify.py already uses -- on the declared target.

Move-semantics mapping (our verify.py op -> their ac-r2-v1 numeric id)
-----------------------------------------------------------------------
Their frozen table (competition/tools/verifier/core.py, MOVE_TABLE), at rank 2
with r0, r1 the two relators and GENS = (1, -1, 2, -2) = (x, x^-1, y, y^-1):

    id  effect                      id  effect
    --  --------------------------  --  --------------------------
     0  r0 <- r0^-1                  7  r0 <- x^-1 r0 x
     1  r1 <- r1^-1                  8  r0 <- y   r0 y^-1
     2  r0 <- r0 r1                  9  r0 <- y^-1 r0 y
     3  r0 <- r0 r1^-1              10  r1 <- x   r1 x^-1
     4  r1 <- r1 r0                 11  r1 <- x^-1 r1 x
     5  r1 <- r1 r0^-1              12  r1 <- y   r1 y^-1
     6  r0 <- x   r0 x^-1           13  r1 <- y^-1 r1 y

Our verify.py ops map onto this table exactly, one-for-one, at rank 2:

  ["invert", i]      -> id 0 if i == 0, else id 1.
      (r_i <- r_i^-1; identical definition on both sides.)

  ["mul", i, j, s]    -> id 2/3 (i=0,j=1,s=+-1) or id 4/5 (i=1,j=0,s=+-1).
      (r_i <- r_i * r_j^s; identical definition, i != j forced at rank 2.)

  ["conj", i, g]      -> id 6..9 (i=0) or 10..13 (i=1), selected by g in
      {1,-1,2,2} via GENS.  (r_i <- g r_i g^-1; identical definition.)

  ["cycle", i, k]      -> NOT a primitive in their table (nor in ours: verify.py
      documents 'cycle' as "a composite of single-letter conjugations" and its
      own selftest #6 proves `apply(["cycle", i, k]) == k-fold repetition of
      apply(["conj", i, g])` with g recomputed as -(current first letter of
      r_i) at each step -- i.e. k iterated *left* single-letter rotations).
      We expand every 'cycle' move into exactly that sequence of k elementary
      ["conj", i, g] moves (function `expand_cycle` below), each of which then
      maps via the conj rule above to one official id 6-13.  This is the same
      decomposition andrews-curtis/make_cert.py's own `rot_moves` helper uses
      to build certificates in the first place (it only ever emits invert/mul/
      conj), so nothing here invents new semantics -- it only flattens moves
      the certificate-generation pipeline already treats as elementary.

  Certificates whose declared "initial" is a *rotation/inversion/swap* of the
  official challenge's exact `initial_relators` (rather than character-for-
  character identical) are aligned first, via andrews-curtis/make_cert.py's
  own `orbit_bridge` (restricted to invert/mul/conj, i.e. moves 0-13 again;
  "swap" is realized as the 3-move + conjugate-reduction + invert identity
  documented in verify.py's docstring and selftest #3: (a,b) -> (ab,b) ->
  (ab,a^-1) -> (b,a^-1) [conjugated to reduce] -> (b,a)). The resulting
  alignment prefix is itself only official moves 0-13.

Nothing here is a new move type: every id emitted is one of the 14 frozen
ac-r2-v1 rows, so a sequence built by this script is exactly a legal Discovery
Track AC submission path in their sense (whether or not it happens to end at
their required (x, y) target).
"""
import argparse
import json
import os
import sys

AC_PROJECT = os.environ.get("AC_PROJECT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAIR_REPO = os.environ.get("SAIR_REPO", "sair-ac")  # clone of github.com/SAIRcompetition/Andrews-Curtis

sys.path.insert(0, AC_PROJECT)
import verify as V  # noqa: E402  (our independent replay checker)
import make_cert as MC  # noqa: E402  (orbit_bridge / rot_moves: invert/mul/conj only)

sys.path.insert(0, os.path.join(SAIR_REPO, "competition", "tools"))
from verifier import core as sair_core  # noqa: E402  (official ac-r2-v1 implementation)


# --------------------------------------------------------------------------
# our elementary-move op  ->  official ac-r2-v1 numeric id (see module docstring)
# --------------------------------------------------------------------------

_CONJ_TABLE = {
    (0, 1): 6, (0, -1): 7, (0, 2): 8, (0, -2): 9,
    (1, 1): 10, (1, -1): 11, (1, 2): 12, (1, -2): 13,
}
_MUL_TABLE = {
    (0, 1, 1): 2, (0, 1, -1): 3,
    (1, 0, 1): 4, (1, 0, -1): 5,
}


def to_official_id(mv):
    """['invert'|'mul'|'conj', ...] (rank 2) -> official ac-r2-v1 id 0..13."""
    op = mv[0]
    if op == "invert":
        i = mv[1]
        return 0 if i == 0 else 1
    if op == "mul":
        i, j, s = mv[1], mv[2], mv[3]
        return _MUL_TABLE[(i, j, s)]
    if op == "conj":
        i, g = mv[1], mv[2]
        return _CONJ_TABLE[(i, g)]
    raise ValueError("not an elementary (rank-2) move: %r" % (mv,))


def expand_cycle(state, i, k):
    """Expand verify.py's ['cycle', i, k] into k elementary ['conj', i, g]
    moves (state updated in place with our own V.apply, so this is exercised
    against our own implementation as it goes). Matches verify.py's selftest
    #6 ('cycle == iterated conjugation') exactly: g is recomputed each step as
    -(current first letter)."""
    elem = []
    r = state[i]
    if not r:
        return elem
    k %= len(r)
    for _ in range(k):
        g = -state[i][0]
        mv = ["conj", i, g]
        state[:] = V.apply(state, mv, 2)
        elem.append(mv)
    return elem


def flatten_to_elementary(cert_moves, initial):
    """Expand a verify.py ledger (possibly containing 'cycle') into a flat
    list of elementary ('invert'|'mul'|'conj') moves only, replaying on a copy
    of `initial` with our own V.apply throughout.  Returns (elementary_moves,
    final_state)."""
    state = [list(r) for r in initial]
    out = []
    for mv in cert_moves:
        if mv[0] == "cycle":
            out.extend(expand_cycle(state, mv[1], mv[2]))
        else:
            state[:] = V.apply(state, mv, 2)
            out.append(mv)
    return out, state


# --------------------------------------------------------------------------
# locate the official SAIR challenge (if any) matching a presentation, up to
# verify.py's own swap x inversion x rotation orbit
# --------------------------------------------------------------------------

def load_manifest():
    path = os.path.join(SAIR_REPO,
                         "competition/tools/verifier/data/manifest.json")
    with open(path) as f:
        return json.load(f)


_CANON_CACHE = {}


def canon_key(relators):
    """A canonical representative of `relators` under verify.py's own
    swap x inversion x rotation orbit -- used purely to *find* which official
    challenge (if any) matches a certificate's declared presentation."""
    return min(V.orbit(relators))


def build_ac_index(manifest):
    """challenge_id (ac-*) -> initial_relators, plus a canon-key -> challenge_id
    lookup for exact-orbit matching."""
    by_id = {}
    by_canon = {}
    for c in manifest["challenges"]:
        if not c["challenge_id"].startswith("ac-"):
            continue
        by_id[c["challenge_id"]] = c["initial_relators"]
        by_canon[canon_key(c["initial_relators"])] = c["challenge_id"]
    return by_id, by_canon


def find_official_challenge(by_canon, by_id, relators):
    key = canon_key(relators)
    cid = by_canon.get(key)
    if cid is None:
        return None
    return cid, by_id[cid]


# --------------------------------------------------------------------------
# alignment: official initial_relators (o0, o1) -> cert-declared "initial"
# (c0, c1), via andrews-curtis/make_cert.py's orbit_bridge (invert/mul/conj
# only)
# --------------------------------------------------------------------------

def alignment_moves(official_initial, cert_initial):
    S = [list(r) for r in official_initial]
    T = [V.reduce_word(list(r)) for r in cert_initial]
    moves = MC.orbit_bridge(S, T)
    assert S == T, "orbit_bridge failed to align %r -> %r (got %r)" % (
        official_initial, cert_initial, S)
    return moves, S


# --------------------------------------------------------------------------
# replay official ids through THEIR OWN core.apply_move
# --------------------------------------------------------------------------

def replay_official(initial_relators, ids):
    state = (tuple(initial_relators[0]), tuple(initial_relators[1]))
    for k, mid in enumerate(ids):
        if not (isinstance(mid, int) and 0 <= mid < sair_core.NUM_MOVES):
            raise ValueError("step %d: id %r out of range 0..%d" %
                              (k, mid, sair_core.NUM_MOVES - 1))
        state = sair_core.apply_move(state, mid)
    return [list(state[0]), list(state[1])]


def in_target_orbit(state, target):
    if not all(V.is_cyclically_reduced(r) for r in state):
        return False
    tgt = [V.reduce_word(list(r)) for r in target]
    return tuple(tuple(r) for r in state) in V.orbit(tgt)
