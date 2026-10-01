# AI disclosure

AI models produced the content of this repository: the search programs, certificates, checkers, figures and text.
The repository owner chose the problem, directed the work and decided on scope and publication. The owner did not check
the code or the certificates line by line.

**Models**
- Claude Opus 5.5 (Anthropic, via Claude Code) did most of the work, as several coordinated agents: the search engines,
  the certificate pipeline, `verify.py`, the SAIR replay in `sair_check/`, the figures and the text.
- Claude Sonnet 5 (Anthropic) agents ran the C3/C4 enumerations (result 3) and an adversarial read-only review of the
  search claim.
- The commits carry a `Co-Authored-By: Claude Opus 5.5` trailer.

**Reviews.** The AI review process found a real error, which was fixed:
- the completeness of the capped enumeration needs a conjugator bound $`K \ge \lfloor (L - m)/2 \rfloor`$; the first
  version used $`K = 8`$ at cap $`L = 32`$, where $`K = 9`$ is needed. The cap-32 runs were repeated with $`K = 9`$ and
  gave the same components (correction note in `README.md`, commit 7808a9e).

The review also recorded gaps that remain open:
- the claim that junction-free conjugators of bounded length suffice (see `acsearch.cpp`) is argued and tested, not
  proved;
- `acsearch_lean.cpp` shares its move generation and canonicalisation with `acsearch.cpp`, so the two engines are not
  independent checks of each other.

AI reviews are not peer review, and no human expert has checked this work. The certificate is a *warrant*, not a
human-readable proof (see the note at the top of `README.md`).

**What is checked by software**
- `verify.py` (standard-library Python, written independently of the search code) replays every certificate in
  `certs/` move by move and checks that it ends in the stated orbit of the target.
- `sair_check/` replays the same certificates with `verifier.core.apply_move` of the SAIR ACC repository
  (github.com/SAIRcompetition/Andrews-Curtis); the end states agree with `verify.py`.

What remains to be trusted:
- the enumeration code (`acsearch.cpp`, `acsearch_lean.cpp`): move generation, canonicalisation and the hash table.
  It is tested (it reproduces published component sizes at cap 28, `validate_projection.py` with a negative control,
  an independent canonicalisation comparison in the review), not formally verified;
- the projection argument from exact-word AC moves to the cyclic quotient graph (`README.md`, Search model);
- `verify.py` itself (the AC paths from AK(3) to its letter-permuted images in `certs/phi/`, used for the quotient by
  letter permutations, are checked by it).
