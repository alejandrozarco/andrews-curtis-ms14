# Independent cross-check of `acsearch`

Status: computational test records, not peer reviewed, produced by AI models (see `../AI_DISCLOSURE.md`). These tests
check the enumeration program at small caps; they do not verify it in general.

`crosscheck.py` shares no code with `acsearch.cpp` except the decoding of the `--dump` key format. It needs the SAIR
ACC repository (github.com/SAIRcompetition/Andrews-Curtis, commit `a0fd6e6`) for test E.

```sh
git clone https://github.com/SAIRcompetition/Andrews-Curtis sair-ac && git -C sair-ac checkout a0fd6e6
c++ -O2 -std=c++17 -o acsearch ../acsearch.cpp
./acsearch --start "XyyxYYY|XXXYxxy" --target "x|y" --cap 24 --conj 8 --threads 1 --out P1_c24_k8 --dump
SAIR_REPO=sair-ac python3 crosscheck.py Q "XyyxYYY|XXXYxxy" 24 P1_c24_k8.keys    # own quotient search, same class set?
SAIR_REPO=sair-ac python3 crosscheck.py E "XyyxYYY|XXXYxxy" 20 P1_c20_k8.keys    # exact component projects inside?
```

`run_crosscheck.sh <acsearch binary> <workdir>` makes the dumps and runs all tests (2 jobs, `nice 19`); it writes
`DONE` when every outcome is as expected. `results.txt` lists every run (start, cap, conjugator bound of the `acsearch` dump, counts, PASS/FAIL, seconds).
The negative control compares test Q with an `acsearch` dump made without conjugator moves (`--conj 0`) at cap 24,
where conjugator moves add classes; Q must report a difference there (it reports 118 classes for P1 and for P2).
Up to cap 22 conjugator moves add no classes for P1 and P2, so the cap-20 E tests check the inclusion but cannot
detect missing conjugator moves. E counts states with an empty relator (legal SAIR states, not classes) as failures;
none occur here (all tested presentations have abelianisation determinant $`\pm 1`$). Q and E share the canonical
form `klass()`. Each test checks that the dump comes from a complete `acsearch` run.
