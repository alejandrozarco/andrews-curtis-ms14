# AI disclosure

AI models produced the content of this repository: the search programs, certificates, checkers, figures and text.
The repository owner chose the problem, directed the work and decided on scope and publication. The owner did not check
the code or the certificates line by line.

**Models**
- Claude Opus 5.5 (Anthropic, via Claude Code) did most of the work, as several coordinated agents: the search engines,
  the certificate pipeline, `verify.py`, the SAIR replay in `sair_check/`, the figures and the text.
- Claude Sonnet 5 (Anthropic) agents ran the C3/C4 enumerations (result 3) and an adversarial read-only review of the
  search claim.
- A separate Claude Opus 5.5 agent wrote the closure checker in `closure/` (2026-11-10) from the definitions, SAIR's
  move semantics and a description of the dump format, without reading the source of the search engines.
- gpt-6-astra (OpenAI, via the Codex CLI) reviewed the cross-check in `crosscheck/` (read-only).
- Claude Fable 5.2 (Anthropic) wrote an adversarial review of the closure checker in `closure/`, including its own
  mutation tests and an exact-word enumeration with SAIR's `verifier.core.apply_move`. The fixes after that review
  (listed below) were made by Claude Opus 5.5, the agent that also wrote the search engines.
- The commits carry a `Co-Authored-By: Claude Opus 5.5` trailer.

**Reviews.** The AI review process found a real error, which was fixed:
- the completeness of the capped enumeration needs a conjugator bound $`K \ge \lfloor (L - m)/2 \rfloor`$; the first
  version used $`K = 8`$ at cap $`L = 32`$, where $`K = 9`$ is needed. The cap-32 runs were repeated with $`K = 9`$ and
  gave the same components (correction note in `README.md`, commit 7808a9e).

Later reviews found:
- inputs needed to rerun parts of the pipeline (`.paths`, `.keys`) missing from the repository (added; see `README.md`,
  Inputs in `runs/`);
- that the enumeration rested on unchecked C++ (the cross-check in `crosscheck/` was added);
- in that cross-check, that states with an empty relator were skipped rather than reported, missing input checks, and
  that its cap-20 exact-graph tests cannot detect missing conjugator moves (fixed or stated in `crosscheck/README.md`).

- in the closure checker (review verdict: sound with gaps, no route to a false PASS found), that the shipped tests did
  not exercise moves with a nonempty conjugator (a test on a short start with conjugators up to length 5 and five
  cut-short controls was added), a wrong step in the proof of Theorem 2 (realisation of (N) moves; corrected, Theorem 1
  and the PASS criterion unaffected), an overstated memory figure and an unqualified C3 bound in the text, a
  host-byte-order assumption in key decoding, dump classes with |D| != 1 only noted instead of refused, a division by
  zero on an empty dump, and results not tied to the checker source (sha256 of source and dump now recorded). The
  four large checks and the test suite were rerun after these fixes.

The reviews also recorded gaps that remain open:
- the claim that junction-free conjugators of bounded length suffice (see `acsearch.cpp`) is argued and tested, not
  proved (the closure check in `closure/` does not depend on it, but does not cover C3 at cap 31);
- `acsearch_lean.cpp` shares its move generation and canonicalisation with `acsearch.cpp`, so the two engines are not
  independent checks of each other.

AI reviews are not peer review, and no human expert has checked this work. The certificate is a *warrant*, not a
human-readable proof (see the note at the top of `README.md`).

**What is checked by software**
- `verify.py` (standard-library Python, written independently of the search code) replays every certificate in
  `certs/` move by move and checks that it ends in the stated orbit of the target.
- `crosscheck/crosscheck.py` (Python, written independently of `acsearch.cpp`) recomputes capped components at smaller
  caps, in the quotient graph with all conjugators, and as the full exact-word component under the SAIR moves, and
  compares them with `acsearch`'s output.
- `closure/closure_check.cpp` (C++, written independently of `acsearch.cpp`) checks that the dumped components of
  results 2 and 3 at their largest caps (P1, P2, C4 at 32; C3 at 30) contain the start and are closed under every
  in-cap move, which by the proof in `closure/README.md` implies that they contain the whole exact capped component;
  all four pass with the published counts.
- `sair_check/` replays the same certificates with `verifier.core.apply_move` of the SAIR ACC repository
  (github.com/SAIRcompetition/Andrews-Curtis); the end states agree with `verify.py`.

What remains to be trusted:
- the enumeration code (`acsearch.cpp`, `acsearch_lean.cpp`): move generation, canonicalisation and the hash table.
  It is tested (it reproduces published component sizes at cap 28, `validate_projection.py` with a negative control,
  the independent cross-check at caps up to 24), not formally verified. For P1, P2 and C4 at cap 32 and C3 at cap 30
  the engine contributes only the candidate set, and what remains to be trusted is `closure_check.cpp`, its proof
  and the compiler; the C3 result at cap 31 rests on the engine alone;
- the projection argument from exact-word AC moves to the cyclic quotient graph (`README.md`, Search model);
- `verify.py` itself (the AC paths from AK(3) to its letter-permuted images in `certs/phi/`, used for the quotient by
  letter permutations, are checked by it).
