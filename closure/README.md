# closure_check: an independent closure check for capped AC components

`closure_check.cpp` reads a set S of presentation classes, as dumped by the search engine (`.keys`), and checks with its own code that S

1. contains the start class,
2. is closed under every move that stays within the cap L.

Then S contains the projection of the whole exact cap-L AC component of the start, whatever the engine did internally. Any target class outside S is therefore unreachable within the cap.

The checker was written from the definitions below, from the move semantics of the SAIR ACC reference verifier (`competition/tools/verifier/core.py` in github.com/SAIRcompetition/Andrews-Curtis, commit `a0fd6e6`), and from a description of the `.keys` format written by `acsearch --dump`. Its author did not read the source of `acsearch.cpp`, `acsearch_lean.cpp` or the other tools in this repository; the engine binary was only run to produce test dumps. After an adversarial review (Claude Fable 5.2), small fixes were made by the agent that wrote the engines: byte-order-independent key decoding, refusing dump classes with |D| != 1, a guard for empty dumps, and a clearer output label. They do not touch move generation, canonicalisation or the lookup.

```
c++ -O2 -std=c++17 -pthread -o closure_check closure_check.cpp
closure_check --keys F.keys --cap L --start 'u|v' [--target 'u|v']... [--threads N]
              [--selftest N] [--exact-bfs [--maxexact N]] [--bench N]
```

Exit status is 0 on PASS and 1 on FAIL. `run_tests.sh` reproduces the tests of section 5, and `test_log.txt` holds its output. `run_large.sh` reproduces the checks of the published components (section 5a, `results/`). Both scripts write dumps to a scratch directory (`$SCRATCH`, default `./closure-scratch`) and use the engine at `$ACSEARCH` (default `../acsearch`).

## 1. Definitions

- **Words.** Words are over x, X = x^-1, y, Y = y^-1. CR(w) is the cyclic reduction of w, and [w] is the conjugacy class (the cyclic word) of w. For a cyclically reduced u, the cyclically reduced members of [u] are exactly the rotations of u.
- **Exact graph.** States are ordered pairs (r0, r1) of freely reduced words. The edges are SAIR's 14 moves:
  - 0 and 1: invert r0 or r1.
  - 2 to 5: r0 <- r0 r1^±1 and r1 <- r1 r0^±1.
  - 6 to 13: r_i <- g r_i g^-1 for g in {x, X, y, Y}.

  Every move is followed by free reduction, and |state| = |r0| + |r1|. The cap-L component C of the start is everything reachable through states with |state| <= L.
- **Class.** A class is an unordered pair {u, v} of nonempty, cyclically reduced words, taken modulo:
  - rotating u or v,
  - inverting u or v separately,
  - swapping u and v,
  - applying one of the 8 signed letter permutations (x -> x^±1, y -> y^±1, optionally followed by x <-> y) to both words at once.

  The total of a class is |u| + |v|.
- **Projection.** proj(r0, r1) is the class of {CR(r0), CR(r1)}. Since |CR(r)| <= |r|, a state within the cap projects to a class within the cap.
- **Our canonical form.** For each of the 8 automorphisms φ, take the minimum over all rotations of φ(u) and φ(u)^-1, and likewise for v. Order the two words by (length, lexicographic). The canonical form is the minimum of the resulting 128-bit key over φ. It uses the same bit layout as the `.keys` format.

## 2. Empty relators

Let D(r0, r1) be the determinant of the 2x2 matrix of exponent sums (abelianisation).

- Inverting a relator negates its row.
- Conjugating a relator leaves its row unchanged.
- r_i <- r_i r_j^±1 adds ± the other row.

So |D| is invariant under every move. A state with an empty relator has a zero row and D = 0. The starts P1, P2, C3, C4 and AK(3) all have D = -1 (the checker computes and prints this, and refuses to PASS otherwise). So no state of C has an empty relator, and classes with an empty word never need to be considered. The checker also computes D for every dump class and refuses to PASS if any has |D| != 1 (there were none).

## 3. The move set M

Given a class K = {u, v}, consider each ordered choice (A, B) in {(u, v), (v, u)}, each s in {+1, -1} with w = B^s, and each rotation A' of A and w' of w. Write a = |A| and b = |B|. Let k be the length of the free cancellation in A'·w', so k <= min(a, b). Three families of moves result:

- **(E1) e empty, left-maximal.** Here w'_last is not A'_first^-1 and k < min(a, b). Emit {α γ, B}, where A' = α β, w' = β^-1 γ and |β| = k. The word α γ is cyclically reduced of length a + b - 2k (Lemma 4).
- **(E2) e empty, one factor fully absorbed.** Here k = min(a, b). Emit {CR(A' w'), B}.
- **(N) e nonempty.** Take any reduced e with 1 <= |e| <= floor((L - a - 2b) / 2), where:
  - e_first is not A'_last^-1,
  - e_first is not A'_first,
  - e_last is not w'_first^-1,
  - e_last is not w'_last.

  Emit {A' e w' e^-1, B}. This word is reduced and cyclically reduced as written, of length a + b + 2|e|.

Only results with total <= L are emitted. Each one is canonicalised and looked up in S.

Define F(K) = { {[A c B^s c^-1], B} : (A, B), s, every reduced c, nonempty, total <= L }.

**Theorem 0.** M(K) = F(K). In particular, M(K) does not depend on the representative chosen for K.

*Proof.* Every emitted word is of the form A' c w' c^-1 for some c, and rotating A or w is the same as changing c. That gives ⊆. Lemmas 3 and 4 give ⊇. F(K) is invariant under rotating A or B (absorbed into c) and under s -> -s. It is invariant under A -> A^-1 because (A^-1 c w c^-1)^-1 = c w^-1 c^-1 A, which is conjugate to A c w^-1 c^-1. It is invariant under swapping, since both orderings are included, and under automorphisms, which commute with everything. ∎

**Lemma 1.** Inversions and conjugations do not change the projection.

*Proof.* CR(r^-1) = CR(r)^-1. A cyclically reduced conjugate of r is a rotation of CR(r). ∎

**Lemma 2.** Let r0 = α u α^-1 and r1 = β v β^-1, each reduced as written, with u and v cyclically reduced. Then r0 r1^s = α (u c v^s c^-1) α^-1 with c = red(α^-1 β), so proj(r0 r1^s, r1) = {[u c v^s c^-1], v}. The same holds for r1 <- r1 r0^s with the roles swapped. ∎

**Lemma 3 (reducing c).** Let A and w be cyclically reduced and c any reduced word. Then [A c w c^-1] = [A' e w' e^-1], where A' and w' are rotations of A and w and |e| <= |c|. Moreover, either e is empty, or e satisfies the four (N) conditions, in which case A' e w' e^-1 is reduced and cyclically reduced as written.

*Proof.*

1. **Reduce c w c^-1.** Suppose c = c0 t.
   - If w = t^-1 w1, then c w c^-1 = c0 (w1 t^-1) c0^-1.
   - If w = w2 t, then c w c^-1 = c0 (t w2) c0^-1.

   In both cases the middle word is a rotation of w. Repeating this gives c w c^-1 = e w' e^-1, reduced as written: either e is empty, or e_last is neither w'_first^-1 nor w'_last.
2. **Reduce against the ends of A.** Suppose e = z e1.
   - If z = A_first (A = z A1), then [A e w' e^-1] = [A1 z · e1 w' e1^-1].
   - If z = A_last^-1 (A = A1 z^-1), then [A e w' e^-1] = [z^-1 A1 · e1 w' e1^-1].

   In both cases A is replaced by a rotation and e becomes shorter. The inner word e1 w' e1^-1 is still reduced as written. Repeat until e is empty or neither case applies.

The remaining junctions cannot cancel because of the four conditions. ∎

**Lemma 4 (alignments when e is empty).** Every class [A' w'] (any rotations) is emitted by some (E1) or (E2) alignment.

*Proof.* Suppose the alignment (A', w') has w'_last = A'_first^-1 and k < min(a, b). Write A' = z A1 and w' = w1 z^-1. The shifted alignment (A1 z, z^-1 w1) gives the same cyclic word, and its cancellation is >= 1 + min(k, a - 1, b - 1) = k + 1. Repeating, k strictly increases, so the process ends in an (E1) or an (E2) alignment.

In (E1), α and γ are nonempty. Their inner junction does not cancel because k is maximal. Their outer junction γ_last·α_first equals w'_last·A'_first, which does not cancel by assumption. So α γ is cyclically reduced. ∎

**The bound on |e| (and on c).** For exact states, |c| <= |α| + |β| <= (L - |u| - |v|) / 2, because the source total is 2|α| + |u| + 2|β| + |v| <= L. That bound is not needed, though. After Lemma 3 the result's length is exact, a + b + 2|e|, and the kept relator B still counts towards the total. So total <= L if and only if |e| <= (L - a - 2b) / 2. This bound is tighter, and since a, b >= 1 it is at most (L - 3) / 2. `--selftest N` verifies Theorem 0 empirically on N random dump classes (those with (L - a - b) / 2 <= 5). It compares the M-results with a brute force over all rotations, s, and all reduced c with |c| <= (L - a - b) / 2. All 300-class samples matched for every positive run with --selftest. For P1, P2 and AK(3) at caps 17-22 no (N) move fits within the cap (a + 2b is too large), and at cap 24 only |e| = 1 occurs, so those tests exercise only (E1)/(E2). The (N) branch, with |e| up to 5, is tested on the short start xxY|xyxYXY at cap 14 (section 5).

**Theorem 1 (coverage; no false PASS).** Let σ -> σ' be a SAIR edge with |σ|, |σ'| <= L. Then either proj(σ') = proj(σ), or proj(σ') ∈ M(proj(σ)).

*Proof.* Inversions and conjugations are covered by Lemma 1. For multiplications, Lemma 2 shows the result lies in F(K), with total <= |σ'| <= L, and F(K) = M(K) by Theorem 0. ∎

**Corollary (what PASS means).** Suppose the start class is in S and S is closed under M. Then, by induction along exact paths, S ⊇ proj(C). If a target class T is not in S, then no state of C projects to T. In particular, no AC path in SAIR's moves from the start to any presentation in the class T keeps every intermediate total <= L. This covers the trivial presentation (x, y) and all of its automorphic images.

Some common variants of AC moves project into the same M:

- left multiplication r0 <- r1^s r0 (conjugate to r0 r1^s),
- conjugation g^-1 r g,
- conjugation by longer words, realised letter by letter.

So the corollary also holds for those variants, provided every intermediate state is kept within the cap.

**Theorem 2 (realisability; no false FAIL).** proj(C) is closed under M. So a dump that equals proj(C) passes.

*Proof.* Let σ ∈ C with proj(σ) = K. Un-conjugate both relators letter by letter (each step shortens the state), rotate them by single-letter conjugations (same length), and invert as needed. By Theorem 0 we may then work with σ's own cyclically reduced words. Use moves 2/3 or 4/5 according to which relator is the target.

- **(N).** Conjugate r0 = A' to e^-1 A' e, one letter of e at a time (g = e_1^-1 first). By the first two (N) conditions every intermediate word e_{1..j}^-1 A' e_{1..j} is reduced as written, and the total stays <= a + b + 2|e| <= L - b. Then r0 <- r0 r1 with r1 = w' gives e^-1 A' e w', reduced by the third condition and cyclically reduced by the fourth; it is a rotation of the emitted word A' e w' e^-1, and its total is a + 2b + 2|e| <= L. (Conjugating r1 instead would pass through a total of a + 2b + 4|e|, which can exceed L.)
- **(E1).** Apply r0 <- r0 r1 to (A', w'). The product is α γ, already cyclically reduced, with total equal to the emitted result's total, which is <= L.
- **(E2), b <= a.** Here w' is absorbed into A' = α w'^-1. Applying the move to (A', w') gives (α, w'), with total a <= L. Then conjugate α down.
- **(E2), a < b.** Here A' is absorbed into w' = A'^-1 γ. The one-step realisation passes through (γ, w'), with total 2b - a. That can exceed L; the checker counts the (E2) emissions with a < b and 2b - a > L ("case-E2 with a < b and 2b - a > L" in its output). Take instead the in-cap path K -> K1 -> R:
  - r1 <- r1 r0 on (A', γ A'^-1) gives (A', γ), with total b <= L. Conjugating γ down to g = CR(γ) gives the class K1 = {A, g}, with total a + |g| <= b < a + b.
  - Write γ = z g z^-1. Then [w] = [A'^-1 z g z^-1], so the result R = {g, B} lies in F(K1) = M(K1), and its total |g| + b is <= L.

  By induction on the total of the source class, R is reachable from K1 within the cap. ∎

Such (E2) emissions (a < b, 2b - a > L) do occur: 80 at P1 caps 23-24, 160 at P2 caps 23-24, and 1024 at P2 cap 25. All of their results were in S, as Theorem 2 predicts. There were none at the caps where the exact BFS below was feasible, so this case rests on the proof plus the PASS and count agreement.

**Equality.** PASS proves only S ⊇ proj(C). As further evidence, `--exact-bfs` runs a breadth-first search over the exact SAIR graph within the cap, projects every state, and compares with S. For P1 at caps 20-22, P2 at caps 20-21, AK(3) at caps 17-19 and xxY|xyxYXY at cap 14, the projection equals S exactly (up to 37M exact states), and no state with an empty relator was hit.

## 4. Input checks

- The file size must be a multiple of 16.
- Every key is assembled byte by byte as a 16-byte little-endian integer (independent of the host byte order).
- Every key must satisfy na, nb >= 1 and na + nb <= L, and no bits may be set outside the letters.
- Both words must be cyclically reduced.
- Each key is re-canonicalised with our code, sorted and deduplicated. The number of distinct classes must equal the number of keys.
- Whether the input is sorted is reported for information only.

The checker also prints:

- counts by total length,
- membership of the start and of each target, computed from the CR of the given words,
- the number of (class, move) results with total <= L that are not in S, with up to 5 examples showing the source class, the move (ordering, s, rotations, e) and the result.

PASS requires: start ∈ S, no format errors, no duplicates, start |D| = 1, start total <= L, and 0 missing results.

## 5. Test results

All tests were run under `nice -n 19` with at most 2 threads. "Engine" is `states=` from the engine's RESULT line, and dumps used `--conj floor(cap/2)`. For targets, "+" means in S. "triv" is x|y.

| dump | cap | engine states | our classes | result | targets triv / AK3 / P1 / P2 | exact BFS = S |
|---|---|---|---|---|---|---|
| P1 | 20 | 473 | 473 | PASS | - / - / + / - | yes (1.2M states) |
| P1 | 21 | 1207 | 1207 | PASS | - / - / + / - | yes (15.1M) |
| P1 | 22 | 2738 | 2738 | PASS | - / - / + / - | yes (37.5M) |
| P1 | 23 | 7903 | 7903 | PASS | - / - / + / - | |
| P1 | 24 | 17718 | 17718 | PASS | - / - / + / - | |
| P2 | 20 | 521 | 521 | PASS | - / - / - / + | yes |
| P2 | 21 | 1413 | 1413 | PASS | - / - / - / + | yes |
| P2 | 22 | 3186 | 3186 | PASS | - / - / - / + | |
| P2 | 23 | 9866 | 9866 | PASS | - / - / - / + | |
| P2 | 24 | 21932 | 21932 | PASS | - / - / - / + | |
| P2 | 25 | 55033 | 55033 | PASS | (timing run) | |
| AK(3) | 17 | 257 | 257 | PASS | - / + / - / - | yes (0.86M) |
| AK(3) | 18 | 542 | 542 | PASS | - / + / - / - | yes (2.0M) |
| AK(3) | 19 | 2530 | 2530 | PASS | - / + / - / - | yes (23.6M) |
| AK(3) | 20 | 5020 | 5020 | PASS | - / + / - / - | |
| AK(3) | 21 | 18118 | 18118 | PASS | - / + / - / - | |
| xxY\|xyxYXY | 14 | 7374 | 7374 | PASS | - / - / - / - | yes (14.4M) |

Negative controls (all must FAIL):

| control | result | missing results (distinct classes) |
|---|---|---|
| P1 cap 24, `--conj 0` (17600 classes) | FAIL | 118 (118). This is exactly 17718 - 17600. |
| P2 cap 24, `--conj 0` (21814 classes) | FAIL | 118 (118). This is exactly 21932 - 21814. |
| P1 cap 22, random class removed, seeds 1, 2, 3 (totals 21, 20, 21) | FAIL x3 | 4 (1), 4 (1), 3 (1). In each case the missing class is the removed one. |
| P1 cap 22, a class of maximal total 22 removed | FAIL | 1 (1) |
| P2 cap 24, a class of maximal total 24 removed | FAIL | 2 (1) |
| AK(3) cap 21, random class removed | FAIL | 4 (1) |
| xxY\|xyxYXY cap 14, `--conj` 0 / 1 / 2 / 3 / 4 (6999 / 7366 / 7372 / 7372 / 7372 classes) | FAIL x5 | 1400 (375) / 24 (8) / 4 (2) / 4 (2) / 4 (2). The two classes missing at `--conj` 2-4 come from x\|xy by (N) moves with e = yyyyy or YYYYY. |
| P1 cap-22 dump checked with `--cap 23` | FAIL | 8260 (4022) |
| P2 cap-22 dump checked with `--cap 23` | FAIL | 9484 (4663) |

Reference dumps (read-only):

| dump | result | details |
|---|---|---|
| `runs/val_P1_c24.keys` | PASS | 17718 classes |
| `runs/val_P1_c24_k0.keys` | FAIL | 118 missing (118 distinct). The examples are (N) moves with a 1-letter conjugator e. |

The trivial class was outside S in every positive run. At these caps P1, P2 and AK(3) are pairwise in different capped components.

## 5a. The published components (caps 30 to 32)

`run_large.sh` dumps the components of result 2 and 3 of the top-level `README.md` with `acsearch` (same cap and conjugator bound as the published runs) and checks each dump against seven classes: the trivial presentation, AK(3), P1, P2, C3, C4 and C6. Outputs are in `results/` (`dump_*.log` from the engine, `*.txt` from the checker).

| start | cap | engine states (= published) | our classes | move results examined | of them (E2) with a < b, 2b - a > L | results outside S | result |
|---|---|---|---|---|---|---|---|
| C4 | 32 | 3,657,734 | 3,657,734 | 22,443,046 | 29,034 | 0 | PASS |
| C3 | 30 | 58,196,612 | 58,196,612 | 520,999,540 | 125,632 | 0 | PASS |
| C3 | 31 | 199,184,986 | 199,184,986 | 1,817,634,989 | 342,112 | 0 | PASS |
| P1 | 32 | 32,699,098 | 32,699,098 | 197,618,123 | 160,613 | 0 | PASS |
| P2 | 32 | 71,499,215 | 71,499,215 | 461,215,820 | 601,880 | 0 | PASS |

Membership of the seven classes: each set contains its own start; the P1 set also contains C6 (result 1 of the top-level `README.md`); no set contains the trivial presentation, AK(3), or another of P1, P2, C3, C4. By the corollary of section 3, no AC path in SAIR's moves from P1, P2 or C4 (C3) to any of the classes outside its set keeps every total relator length <= 32 (<= 31).

A cap-L component contains every smaller-cap component, so a PASS at the largest cap of a start covers the smaller caps too; the C3 check at cap 30 is kept as the run with the unmodified engine. The C3 component at cap 31 (199,184,986 classes, added 2026-11-13) was first enumerated with `acsearch_lean`, which does not write dumps (its usage line lists `--dump`, but the option is not implemented). `acsearch --dump` sorts a copy of the keys, which at this size needs about 9 GB at its peak, so `run_large.sh` builds a copy of `acsearch.cpp` with that one line changed: it frees the hash table and sorts the keys in place (about 6 GB at its peak). On the cap-14 test start of section 5 the two programs write byte-identical dumps, and at cap 31 the count and the distribution by total length equal those of the `acsearch_lean` run. The PASS does not depend on which program wrote the dump. Each results file ends with the sha256 of `closure_check.cpp` and of the dump it checked.

## 6. Timing and memory

Per-class cost (thread-seconds per class) on real dumps, single thread:

| run | per class |
|---|---|
| P1 cap 24 | 3.3 µs |
| P2 cap 24 | 3.3 µs |
| P2 cap 25 | 3.5-4.5 µs (two runs) |
| AK(3) cap 21 | 2.8 µs |

Real classes produce about 4 to 4.4 in-cap results each.

`--bench N` is a timing-only mode. It fills S with N random cyclically reduced pairs of total L-1 or L, and every lookup misses, so it pays for a full binary search each time. Results:

| bench run | per class |
|---|---|
| 2M classes, L = 24 | 5.1 µs |
| 2M classes, L = 32 | 8.1 µs |
| 10M classes, L = 32, 2 threads | 7.7-9.2 µs thread-seconds (220-260k classes/s wall), RSS 322 MB |

At L = 24 random classes cost about 1.5 times as much as real ones. On the published components (section 5a, one thread, on a machine shared with other jobs) the closure took 7.8-8.3 µs per class: 28 s for C4 cap 32, 262 s for P1 cap 32, 596 s for P2 cap 32, 476 s for C3 cap 30 and 1564 s for C3 cap 31, plus 3-81 s of decoding, canonicalisation and sorting (an earlier run on a less loaded machine took 3.7-7.0 µs per class). Memory is about 16 bytes per class (1.1 GB for 70M, 3.2 GB for 199M) plus small buffers. Up to 20M missing keys per thread are stored if the check fails.

## 7. Limitations and remarks

- **Cap.** L <= 32 is supported, because each word is packed into 64 bits. Words up to 31 letters are possible.
- **Superset only.** PASS proves S ⊇ proj(C), not equality. Equality was confirmed by exact BFS only at small caps.
- **Exact BFS memory.** The exact BFS uses about 60-80 bytes per exact state, so use it only at small caps (P1 cap 22 already has 37M states).
- **Trust base.** A PASS rests on the proofs above, this program, and the compiler. The engine contributes only the candidate set S.
- **Canonical form.** Our canonical representative turned out to coincide with the engine's for every key tested (the checker reports "N of N input keys are already in our canonical form"). This is not relied on: every key is decoded and re-canonicalised by our own code. Our canonicaliser is exercised independently by the exact-BFS comparisons, which project millions of exact states with it, and by the removal controls.
- **Move semantics.** The statements are about SAIR's 14 moves (plus the variants noted in Section 3) with the total-length cap applied to every intermediate state.
