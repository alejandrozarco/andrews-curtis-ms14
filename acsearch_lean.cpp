// acsearch_lean.cpp — memory-lean variant of acsearch.cpp (12-byte keys, no parent array; paths are
// recovered by backward level scans).  Same state space, canonical form and move set as acsearch.cpp.
// Original header of acsearch.cpp follows.
//
// acsearch.cpp — capped connected-component search on cyclic 2-relator presentations.
//
// States: pairs {u, v} of nonempty cyclically reduced words over x, X=x^-1, y, Y=y^-1, taken modulo
//   rotation of either relator, inversion of either relator, swapping the relators    (AC-realizable)
//   and, unless --nosym, the 8 signed letter permutations phi (x<->y, x->x^-1, y->y^-1)  (see JOURNAL.md)
//
// Moves (all AC-realizable):  replace u by the cyclic reduction of
//        rot_i(u) * c * rot_j(v^s) * c^-1      (s = +-1, c a reduced word, |c| <= --conj K)
//   (or symmetrically replace v).  For c = 1 all i, j are used (cancelling or not).  For |c| >= 1 only
//   junction-free c is used (every other c reduces to a shorter c with other i, j), so the result has
//   length |u| + |v| + 2|c|.  Only states with total length <= cap are kept.
//   With K >= (cap - |u| - |v|)/2 this graph contains the image of the exact-word elementary AC graph
//   with total-length cap `cap` (inverse / mul / single-letter conj moves), because every exact state
//   (a u a^-1, b v b^-1) projects to {u, v} and a multiplication projects to the move above with
//   c = a^-1 b, |c| <= |a| + |b| <= (cap - |u| - |v|)/2.
//
// BFS from --start; stops when a --target class is met (reports the path of canonical states),
// or the component is exhausted, or --maxstates is reached.
//
// Usage: acsearch --start "XyyxYYY|XXXYxxy" --target "xxxYYYY|xyxYXY" [--target ...] --cap 28
//                 [--conj K] [--threads 4] [--maxstates N] [--nosym] [--out runs/name] [--dump]
//                 [--all-hits]  (continue after hits, record every target reached)
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
using namespace std;
typedef unsigned __int128 u128;
typedef uint64_t u64;
typedef uint32_t u32;

static const int MAXW = 58;  // max total letters (key has 116 letter bits + 2x6 length bits)
static int CAP = 28, CONJ = 0, THREADS = 4, MAXSHORT = 99;  // MAXSHORT: keep only states with min(|u|,|v|) <= MAXSHORT
static bool NOSYM = false;

struct Wd { int n; uint8_t c[64]; };  // letters 0=x 1=X 2=y 3=Y ; inverse = l^1

static inline u128 maskn(int n) { return n >= 64 ? ~(u128)0 : (((u128)1) << (2 * n)) - 1; }
static const u128 M1 = (((u128)0x5555555555555555ULL) << 64) | (u128)0x5555555555555555ULL;

static inline u128 pack(const uint8_t* c, int n) { u128 w = 0; for (int i = 0; i < n; i++) w = (w << 2) | c[i]; return w; }
static inline u64 rev2_64(u64 x) {
    x = ((x >> 2) & 0x3333333333333333ULL) | ((x & 0x3333333333333333ULL) << 2);
    x = ((x >> 4) & 0x0F0F0F0F0F0F0F0FULL) | ((x & 0x0F0F0F0F0F0F0F0FULL) << 4);
    return __builtin_bswap64(x);
}
// inverse word: reverse letters, flip bit0 of each letter
static inline u128 invw(u128 w, int n) {
    u128 r = (((u128)rev2_64((u64)w)) << 64) | (u128)rev2_64((u64)(w >> 64));
    r >>= (128 - 2 * n);
    return r ^ (M1 & maskn(n));
}
static inline u128 phiw(u128 w, int n, int p) {  // p bit0: invert x, bit1: invert y, bit2: swap x<->y
    u128 m = maskn(n);
    u128 g = (w >> 1) & M1 & m;  // 1 at letters that are y/Y
    u128 r = w;
    if (p & 1) r ^= (~g) & M1 & m;
    if (p & 2) r ^= g;
    if (p & 4) r ^= (M1 << 1) & m;
    return r;
}
static inline u128 canon_rot(u128 w, int n) {  // min over rotations of w and w^-1
    u128 m = maskn(n), best = w, iw = invw(w, n);
    if (iw < best) best = iw;
    for (int k = 1; k < n; k++) {
        u128 a = ((w << (2 * k)) | (w >> (2 * (n - k)))) & m;
        if (a < best) best = a;
        u128 b = ((iw << (2 * k)) | (iw >> (2 * (n - k)))) & m;
        if (b < best) best = b;
    }
    return best;
}
static inline u128 mkkey(u128 a, int na, u128 b, int nb) {
    if (nb < na || (nb == na && b < a)) { swap(a, b); swap(na, nb); }
    return (((u128)na) << 122) | (((u128)nb) << 116) | (a << (2 * nb)) | b;
}
static inline void unkey(u128 k, Wd& a, Wd& b) {
    a.n = (int)(k >> 122); b.n = (int)((k >> 116) & 63);
    for (int i = b.n - 1; i >= 0; i--) { b.c[i] = (uint8_t)(k & 3); k >>= 2; }
    for (int i = a.n - 1; i >= 0; i--) { a.c[i] = (uint8_t)(k & 3); k >>= 2; }
}
// canonical key of {u (packed wu, len nu), v}, with v's per-phi canonical forms precomputed
struct Pre { u128 cv[8]; int nv; };
static inline void precompute(u128 wv, int nv, Pre& P) {
    P.nv = nv;
    for (int p = 0; p < 8; p++) P.cv[p] = (NOSYM && p) ? 0 : canon_rot(phiw(wv, nv, p), nv);
}
static inline u128 canon_pair(u128 wu, int nu, const Pre& P) {
    u128 best = ~(u128)0;
    int np = NOSYM ? 1 : 8;
    for (int p = 0; p < np; p++) {
        u128 k = mkkey(canon_rot(phiw(wu, nu, p), nu), nu, P.cv[p], P.nv);
        if (k < best) best = k;
    }
    return best;
}
static bool parse(const string& s, Wd& w) {
    w.n = 0;
    for (char ch : s) {
        int l = ch == 'x' ? 0 : ch == 'X' ? 1 : ch == 'y' ? 2 : ch == 'Y' ? 3 : -1;
        if (l < 0) return false;
        if (w.n && (w.c[w.n - 1] ^ 1) == l) w.n--; else w.c[w.n++] = (uint8_t)l;
    }
    int lo = 0, hi = w.n - 1;
    while (lo < hi && (w.c[lo] ^ 1) == w.c[hi]) lo++, hi--;
    int m = hi - lo + 1; memmove(w.c, w.c + lo, m); w.n = m;
    return m > 0;
}
static string str(const Wd& w) { string s; for (int i = 0; i < w.n; i++) s += "xXyY"[w.c[i]]; return s; }
static u128 key_of(const string& spec) {
    size_t bar = spec.find('|');
    Wd a, b;
    if (bar == string::npos || !parse(spec.substr(0, bar), a) || !parse(spec.substr(bar + 1), b)) {
        fprintf(stderr, "bad presentation %s\n", spec.c_str()); exit(2);
    }
    Pre P; precompute(pack(b.c, b.n), b.n, P);
    return canon_pair(pack(a.c, a.n), a.n, P);
}
static string keystr(u128 k) { Wd a, b; unkey(k, a, b); return str(a) + "|" + str(b); }

// ---- neighbours -------------------------------------------------------------------------------
template <class F>
static void neighbours(const Wd& u, const Wd& v, F&& emit) {
    for (int which = 0; which < 2; which++) {
        const Wd& A = which ? v : u;
        const Wd& B0 = which ? u : v;
        Pre P; precompute(pack(B0.c, B0.n), B0.n, P);
        int budget = CAP - B0.n;  // max length of the new relator
        if (budget <= 0) continue;
        for (int s = 0; s < 2; s++) {
            Wd B; B.n = B0.n;
            for (int t = 0; t < B.n; t++) B.c[t] = s ? (B0.c[B0.n - 1 - t] ^ 1) : B0.c[t];
            for (int i = 0; i < A.n; i++) {
                uint8_t Afirst = A.c[i], Alast = A.c[(i + A.n - 1) % A.n];
                for (int j = 0; j < B.n; j++) {
                    // c = 1
                    uint8_t buf[160]; int n = 0;
                    for (int t = 0; t < A.n; t++) buf[n++] = A.c[(i + t) % A.n];
                    for (int t = 0; t < B.n; t++) {
                        uint8_t l = B.c[(j + t) % B.n];
                        if (n && (buf[n - 1] ^ 1) == l) n--; else buf[n++] = l;
                    }
                    int lo = 0, hi = n - 1;
                    while (lo < hi && (buf[lo] ^ 1) == buf[hi]) lo++, hi--;
                    int m = n ? hi - lo + 1 : 0;
                    if (m > 0 && m <= budget && min(m, B0.n) <= MAXSHORT) emit(canon_pair(pack(buf + lo, m), m, P));
                    // junction-free conjugators c, 1 <= |c| <= CONJ
                    if (CONJ > 0) {
                        uint8_t Bfirst = B.c[j], Blast = B.c[(j + B.n - 1) % B.n];
                        int maxc = min(CONJ, (budget - A.n - B.n) / 2);
                        if (maxc < 1) continue;
                        // enumerate reduced c of length k with c[0] != Alast^1, c[0] != Afirst,
                        // c[k-1] != Bfirst^1, c[k-1] != Blast
                        uint8_t c[32];
                        for (int k = 1; k <= maxc; k++) {
                            // iterative enumeration over 4^k with reducedness filter
                            int idx[32]; for (int t = 0; t < k; t++) idx[t] = 0;
                            while (true) {
                                bool ok = true;
                                for (int t = 0; t < k && ok; t++) { c[t] = (uint8_t)idx[t]; if (t && (c[t - 1] ^ 1) == c[t]) ok = false; }
                                if (ok && (c[0] == (Alast ^ 1) || c[0] == Afirst)) ok = false;
                                if (ok && (c[k - 1] == (Bfirst ^ 1) || c[k - 1] == Blast)) ok = false;
                                if (ok && min(A.n + B.n + 2 * k, B0.n) <= MAXSHORT) {
                                    uint8_t w[160]; int L = 0;
                                    for (int t = 0; t < A.n; t++) w[L++] = A.c[(i + t) % A.n];
                                    for (int t = 0; t < k; t++) w[L++] = c[t];
                                    for (int t = 0; t < B.n; t++) w[L++] = B.c[(j + t) % B.n];
                                    for (int t = k - 1; t >= 0; t--) w[L++] = c[t] ^ 1;
                                    emit(canon_pair(pack(w, L), L, P));
                                }
                                int t = k - 1;
                                while (t >= 0 && idx[t] == 3) idx[t--] = 0;
                                if (t < 0) break;
                                idx[t]++;
                            }
                        }
                    }
                }
            }
        }
    }
}


// ---- 96-bit compressed keys ------------------------------------------------------------------
// c = 1 << (2T+6) | letters << 6 | na   (T = na + nb <= 44)
static inline void compress(u128 k, u64& lo, u32& hi) {
    int na = (int)(k >> 122), nb = (int)((k >> 116) & 63), T = na + nb;
    u128 letters = k & maskn(T);
    u128 c = (((u128)1) << (2 * T + 6)) | (letters << 6) | (u128)na;
    lo = (u64)c; hi = (u32)(c >> 64);
}
static inline u128 decompress(u64 lo, u32 hi) {
    u128 c = (((u128)hi) << 64) | lo;
    int p = 127 - (hi ? __builtin_clzll((u64)hi) : 64 + __builtin_clzll(lo));
    int T = (p - 6) / 2, na = (int)(c & 63), nb = T - na;
    u128 letters = (c >> 6) & maskn(T);
    return (((u128)na) << 122) | (((u128)nb) << 116) | letters;
}
struct LTable {
    vector<u64> lo; vector<u32> hi; vector<u32> slot; u64 nslots = 0;
    void init(u64 maxstates) {
        nslots = maxstates * 5 / 4 + 1024;
        slot.assign(nslots, 0); lo.reserve(maxstates); hi.reserve(maxstates);
    }
    size_t size() const { return lo.size(); }
    static inline u64 h(u64 a, u32 b) { u64 x = a ^ ((u64)b * 0x9E3779B97F4A7C15ULL); x ^= x >> 31; x *= 0xBF58476D1CE4E5B9ULL; x ^= x >> 29; x *= 0x94D049BB133111EBULL; x ^= x >> 32; return x; }
    inline u64 start(u64 a, u32 b) const { return (u64)(((unsigned __int128)h(a, b) * nslots) >> 64); }
    inline bool contains(u64 a, u32 b) const {
        for (u64 i = start(a, b);; i = (i + 1 == nslots ? 0 : i + 1)) { u32 s = slot[i]; if (!s) return false; if (lo[s - 1] == a && hi[s - 1] == b) return true; }
    }
    inline bool insert(u64 a, u32 b) {
        for (u64 i = start(a, b);; i = (i + 1 == nslots ? 0 : i + 1)) {
            u32 s = slot[i];
            if (!s) { lo.push_back(a); hi.push_back(b); slot[i] = (u32)lo.size(); return true; }
            if (lo[s - 1] == a && hi[s - 1] == b) return false;
        }
    }
    u128 key(u64 x) const { return decompress(lo[x], hi[x]); }
};

int main(int argc, char** argv) {
    string start, out; vector<string> targets; u64 maxstates = 200000000; bool allhits = false;
    for (int i = 1; i < argc; i++) {
        string a = argv[i];
        auto nx = [&]() { if (i + 1 >= argc) { fprintf(stderr, "missing arg\n"); exit(2); } return string(argv[++i]); };
        if (a == "--start") start = nx();
        else if (a == "--target") targets.push_back(nx());
        else if (a == "--cap") CAP = stoi(nx());
        else if (a == "--conj") CONJ = stoi(nx());
        else if (a == "--maxshort") MAXSHORT = stoi(nx());
        else if (a == "--threads") THREADS = stoi(nx());
        else if (a == "--maxstates") maxstates = stoull(nx());
        else if (a == "--nosym") NOSYM = true;
        else if (a == "--out") out = nx();
        else if (a == "--all-hits") allhits = true;
        else { fprintf(stderr, "unknown arg %s\n", a.c_str()); return 2; }
    }
    if (CAP > 44) { fprintf(stderr, "cap too large for 96-bit keys\n"); return 2; }
    vector<u128> tk; for (auto& t : targets) tk.push_back(key_of(t));
    LTable T; T.init(maxstates);
    u128 k0 = key_of(start);
    { u64 a; u32 b; compress(k0, a, b); if (decompress(a, b) != k0) { fprintf(stderr, "compress self-test failed\n"); return 3; } T.insert(a, b); }
    fprintf(stderr, "LEAN start %s cap=%d conj=%d nosym=%d threads=%d maxstates=%llu\n", keystr(k0).c_str(), CAP, CONJ, NOSYM, THREADS, (unsigned long long)maxstates);
    for (size_t t = 0; t < tk.size(); t++) fprintf(stderr, "target %zu: %s\n", t, keystr(tk[t]).c_str());
    auto t0 = chrono::steady_clock::now();
    vector<u64> lvstart{0, 1};  // level d occupies [lvstart[d], lvstart[d+1])
    bool complete = false, hit = false, overflow = false;
    vector<pair<int, u64>> hits;
    const u64 BATCH = 1 << 16;
    int level = 0;
    while (true) {
        u64 lo = lvstart[level], hi = lvstart[level + 1];
        if (lo == hi) { complete = true; break; }
        u64 lvl_new = 0; vector<u64> bylen(MAXW + 2, 0);
        for (u64 b0 = lo; b0 < hi && !overflow; b0 += BATCH) {
            u64 b1 = min(hi, b0 + BATCH);
            vector<vector<pair<u64, u32>>> bufs(THREADS);
            atomic<u64> next(b0);
            vector<thread> th;
            for (int t = 0; t < THREADS; t++) th.emplace_back([&, t]() {
                auto& buf = bufs[t];
                while (true) {
                    u64 s = next.fetch_add(64);
                    if (s >= b1) break;
                    u64 e = min(b1, s + 64);
                    for (u64 x = s; x < e; x++) {
                        Wd a, b; unkey(T.key(x), a, b);
                        neighbours(a, b, [&](u128 k) { u64 p; u32 q; compress(k, p, q); if (!T.contains(p, q)) buf.push_back({p, q}); });
                    }
                }
            });
            for (auto& t : th) t.join();
            for (auto& buf : bufs) {
                for (auto& kp : buf) {
                    if (!T.insert(kp.first, kp.second)) continue;
                    lvl_new++;
                    u128 k = decompress(kp.first, kp.second);
                    bylen[(int)(k >> 122) + (int)((k >> 116) & 63)]++;
                    for (size_t ti = 0; ti < tk.size(); ti++) if (tk[ti] == k) { hit = true; hits.push_back({(int)ti, T.size() - 1}); fprintf(stderr, "HIT target %zu (%s) at level %d\n", ti, targets[ti].c_str(), level + 1); }
                    if (T.size() >= maxstates) { overflow = true; break; }
                }
                vector<pair<u64, u32>>().swap(buf);
                if (overflow) break;
            }
            if (hit && !allhits) break;
        }
        lvstart.push_back(T.size());
        double el = chrono::duration<double>(chrono::steady_clock::now() - t0).count();
        fprintf(stderr, "level %d: +%llu new (total %zu) %.0fs  bylen:", level + 1, (unsigned long long)lvl_new, T.size(), el);
        for (int L = 0; L <= CAP; L++) if (bylen[L]) fprintf(stderr, " %d:%llu", L, (unsigned long long)bylen[L]);
        fprintf(stderr, "\n");
        level++;
        if ((hit && !allhits) || overflow) break;
    }
    double el = chrono::duration<double>(chrono::steady_clock::now() - t0).count();
    vector<u64> hist(MAXW + 2, 0);
    for (u64 x = 0; x < T.size(); x++) { u128 k = T.key(x); hist[(int)(k >> 122) + (int)((k >> 116) & 63)]++; }
    fprintf(stderr, "RESULT start=%s cap=%d conj=%d nosym=%d states=%zu levels=%d complete=%d hit=%d overflow=%d time=%.0fs\n",
            start.c_str(), CAP, CONJ, NOSYM, T.size(), level, complete, hit, overflow, el);
    fprintf(stderr, "states by total length:");
    for (int L = 0; L <= CAP; L++) if (hist[L]) fprintf(stderr, " %d:%llu", L, (unsigned long long)hist[L]);
    fprintf(stderr, "\n");
    // path reconstruction by backward level scans
    FILE* pf = out.empty() ? nullptr : fopen((out + ".paths").c_str(), "w");
    for (auto& hp : hits) {
        u64 x = hp.second;
        int d = (int)(upper_bound(lvstart.begin(), lvstart.end(), x) - lvstart.begin()) - 1;
        vector<u128> path{T.key(x)};
        u128 cur = T.key(x);
        for (int lv = d - 1; lv >= 0; lv--) {
            atomic<u64> found(UINT64_MAX); atomic<u64> next(lvstart[lv]); u64 e0 = lvstart[lv + 1];
            vector<thread> th;
            for (int t = 0; t < THREADS; t++) th.emplace_back([&]() {
                while (found.load() == UINT64_MAX) {
                    u64 s = next.fetch_add(256); if (s >= e0) break;
                    for (u64 y = s; y < min(e0, s + 256) && found.load() == UINT64_MAX; y++) {
                        Wd a, b; unkey(T.key(y), a, b); bool f = false;
                        neighbours(a, b, [&](u128 k) { if (k == cur) f = true; });
                        if (f) { u64 exp = UINT64_MAX; found.compare_exchange_strong(exp, y); }
                    }
                }
            });
            for (auto& t : th) t.join();
            if (found.load() == UINT64_MAX) { fprintf(stderr, "path reconstruction failed at level %d\n", lv); return 4; }
            cur = T.key(found.load()); path.push_back(cur);
        }
        reverse(path.begin(), path.end());
        u64 peak = 0; for (auto k : path) peak = max<u64>(peak, (u64)(k >> 122) + (u64)((k >> 116) & 63));
        fprintf(stderr, "PATH target %d: %zu steps, peak %llu\n", hp.first, path.size() - 1, (unsigned long long)peak);
        if (pf) {
            fprintf(pf, "# target %d %s cap %d conj %d nosym %d peak %llu steps %zu\n", hp.first, targets[hp.first].c_str(), CAP, CONJ, NOSYM, (unsigned long long)peak, path.size() - 1);
            for (auto k : path) fprintf(pf, "%s\n", keystr(k).c_str());
            fprintf(pf, "# end\n"); fflush(pf);
        }
    }
    if (pf) fclose(pf);
    return 0;
}
