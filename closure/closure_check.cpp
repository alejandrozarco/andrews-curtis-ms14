// closure_check.cpp -- independent closure checker for capped Andrews-Curtis
// components of balanced 2-generator presentations.
//
// Written from the definitions only (see README.md in this directory for the
// definitions, the proof that the move set M covers every projected AC move
// within the cap, and what PASS implies).  C++17, standard library only.
//
// Build:  c++ -O2 -std=c++17 -pthread -o closure_check closure_check.cpp
//
// Usage:
//   closure_check --keys F.keys --cap L --start 'u|v' [--target 'u|v']...
//                 [--threads N] [--selftest N] [--exact-bfs] [--maxexact N]
//
// Letters: x, X = x^-1, y, Y = y^-1; internal codes 0=x 1=X 2=y 3=Y,
// so the inverse letter of c is c^1.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <random>
#include <set>
#include <string>
#include <thread>
#include <unordered_set>
#include <vector>

typedef unsigned __int128 u128;
typedef uint64_t u64;

static const u64 M55 = 0x5555555555555555ULL;
static const u64 MAA = 0xAAAAAAAAAAAAAAAAULL;
static const int MAXW = 32;  // max letters of a single packed word

static inline u64 maskn(int n) { return n >= 32 ? ~0ULL : ((1ULL << (2 * n)) - 1); }

// ---------------------------------------------------------------- words
static const char LET[4] = {'x', 'X', 'y', 'Y'};

static std::string wstr(const uint8_t* w, int n) {
    std::string s;
    for (int i = 0; i < n; i++) s += LET[w[i]];
    return s;
}

// letter 0 in the most significant used position => integer order of
// equal-length packed words is lexicographic order.
static inline u64 pack(const uint8_t* w, int n) {
    u64 p = 0;
    for (int i = 0; i < n; i++) p = (p << 2) | w[i];
    return p;
}

static inline u64 revgroups(u64 x) {  // reverse the 32 2-bit groups
    x = ((x >> 2) & 0x3333333333333333ULL) | ((x & 0x3333333333333333ULL) << 2);
    x = ((x >> 4) & 0x0F0F0F0F0F0F0F0FULL) | ((x & 0x0F0F0F0F0F0F0F0FULL) << 4);
    return __builtin_bswap64(x);
}
// formal inverse of a packed word: reverse and invert every letter
static inline u64 invpacked(u64 p, int n) {
    return (revgroups(p) >> (64 - 2 * n)) ^ (M55 & maskn(n));
}
// minimum over all cyclic rotations of p and of p^-1
static inline u64 mincyc(u64 p, int n) {
    const u64 m = maskn(n);
    u64 best = p, r = p;
    for (int k = 1; k < n; k++) {
        r = ((r << 2) | (r >> (2 * n - 2))) & m;
        if (r < best) best = r;
    }
    r = invpacked(p, n);
    if (r < best) best = r;
    for (int k = 1; k < n; k++) {
        r = ((r << 2) | (r >> (2 * n - 2))) & m;
        if (r < best) best = r;
    }
    return best;
}
// the 8 signed letter permutations: bit0 x->X, bit1 y->Y, bit2 x<->y
static inline u64 autom(u64 p, int n, int a) {
    const u64 m = maskn(n);
    if (a & 1) p ^= (~p >> 1) & M55 & m;  // letters with high bit 0 (x,X)
    if (a & 2) p ^= (p >> 1) & M55 & m;   // letters with high bit 1 (y,Y)
    if (a & 4) p ^= MAA & m;              // x<->y, X<->Y
    return p;
}

// key layout (same layout as the input format, but OUR canonical choice):
// na<<122 | nb<<116 | letters(a)<<2nb | letters(b)
static inline u128 mkkey(int na, u64 pa, int nb, u64 pb) {
    return ((u128)na << 122) | ((u128)nb << 116) | ((u128)pa << (2 * nb)) | (u128)pb;
}
static inline void deckey(u128 k, int& na, int& nb, uint8_t* a, uint8_t* b) {
    na = (int)(k >> 122);
    nb = (int)((k >> 116) & 63);
    for (int i = 0; i < nb; i++) b[i] = (uint8_t)((k >> (2 * (nb - 1 - i))) & 3);
    for (int i = 0; i < na; i++) a[i] = (uint8_t)((k >> (2 * (nb + na - 1 - i))) & 3);
}

// Our canonical form of the class of {u, v} (both nonempty, cyclically
// reduced, |u|,|v| <= 32): minimum over the 8 automorphisms phi of the key
// of the ordered pair (min-rotation-or-inverse of phi(u), same of phi(v)),
// the pair ordered by (length, packed value).
static inline u128 canon(u64 pu, int nu, u64 pv, int nv) {
    u128 best = ~(u128)0;
    for (int a = 0; a < 8; a++) {
        u64 A = mincyc(autom(pu, nu, a), nu);
        u64 B = mincyc(autom(pv, nv, a), nv);
        u128 k;
        if (nu < nv || (nu == nv && A <= B))
            k = mkkey(nu, A, nv, B);
        else
            k = mkkey(nv, B, nu, A);
        if (k < best) best = k;
    }
    return best;
}
static inline u128 canonw(const uint8_t* u, int nu, const uint8_t* v, int nv) {
    return canon(pack(u, nu), nu, pack(v, nv), nv);
}

static bool is_reduced(const uint8_t* w, int n) {
    for (int i = 0; i + 1 < n; i++)
        if (w[i + 1] == (w[i] ^ 1)) return false;
    return true;
}
static bool is_cyc_reduced(const uint8_t* w, int n) {
    return is_reduced(w, n) && (n < 2 || w[n - 1] != (w[0] ^ 1));
}
// free reduction in place (stack); returns new length
static int free_reduce(uint8_t* w, int n) {
    int t = 0;
    for (int i = 0; i < n; i++) {
        if (t > 0 && w[t - 1] == (w[i] ^ 1))
            t--;
        else
            w[t++] = w[i];
    }
    return t;
}
// cyclic reduction of a freely reduced word: returns offset & length
static void cyc_reduce(const uint8_t* w, int n, int& off, int& len) {
    int i = 0, j = n - 1;
    while (i < j && w[j] == (w[i] ^ 1)) { i++; j--; }
    off = i;
    len = (n == 0) ? 0 : j - i + 1;
}
static void ex_ey(const uint8_t* w, int n, int& ex, int& ey) {
    ex = ey = 0;
    for (int i = 0; i < n; i++) {
        switch (w[i]) {
            case 0: ex++; break;
            case 1: ex--; break;
            case 2: ey++; break;
            case 3: ey--; break;
        }
    }
}
static long det2(const uint8_t* u, int nu, const uint8_t* v, int nv) {
    int a, b, c, d;
    ex_ey(u, nu, a, b);
    ex_ey(v, nv, c, d);
    return (long)a * d - (long)b * c;
}

static bool parse_word(const std::string& s, std::vector<uint8_t>& w) {
    w.clear();
    for (char ch : s) {
        switch (ch) {
            case 'x': w.push_back(0); break;
            case 'X': w.push_back(1); break;
            case 'y': w.push_back(2); break;
            case 'Y': w.push_back(3); break;
            case ' ': break;
            default: return false;
        }
    }
    return true;
}
static bool parse_pair(const std::string& s, std::vector<uint8_t>& u, std::vector<uint8_t>& v) {
    size_t bar = s.find('|');
    if (bar == std::string::npos) return false;
    if (!parse_word(s.substr(0, bar), u) || !parse_word(s.substr(bar + 1), v)) return false;
    u.resize(free_reduce(u.data(), (int)u.size()));
    v.resize(free_reduce(v.data(), (int)v.size()));
    return true;
}
static std::string keystr(u128 k) {
    int na, nb;
    uint8_t a[64], b[64];
    deckey(k, na, nb, a, b);
    return wstr(a, na) + "|" + wstr(b, nb);
}

// ---------------------------------------------------------------- the move set M
// For the class {u,v}: for each ordered choice (A,B) in {(u,v),(v,u)}, each
// s = +-1, w = B^s, each rotation A' of A and w' of w:
//   (E) e empty: the cyclic reduction of A'w', but only for alignments that
//       are "left-maximal" (w'_last does not cancel A'_first) or where one
//       factor cancels completely (k = min(|A|,|w|)); see README, Lemma 3.
//   (N) e nonempty, reduced, |e| <= (L-|A|-2|B|)/2, with e_1 != A'_last^-1,
//       e_1 != A'_first, e_last != w'_first^-1, e_last != w'_last, giving the
//       (reduced and cyclically reduced) word A' e w' e^-1.
// Result class {result, B}; only results with total <= L are emitted.
struct MoveDesc {
    int ord, s, i, j, ne;
    uint8_t e[32];
};

struct GenStats {
    u64 degenerate = 0;  // A'w' reduced to the empty word (impossible for det +-1)
    u64 indirect = 0;    // (E) emissions with A' absorbed by w', |A|<|w|, 2|w|-|A| > L:
                         // realisable only by a 2-step path (README, Theorem 2, case E2)
};

template <class F>
static void gen_moves(const uint8_t* u, int nu, const uint8_t* v, int nv, int L, GenStats& st, F&& emit) {
    uint8_t AA[2 * MAXW], WW[2 * MAXW], buf[4 * MAXW + 8], e[MAXW];
    MoveDesc d;
    for (int ord = 0; ord < 2; ord++) {
        const uint8_t* A = ord ? v : u;
        const uint8_t* B = ord ? u : v;
        const int a = ord ? nv : nu, b = ord ? nu : nv;
        for (int t = 0; t < a; t++) AA[t] = AA[t + a] = A[t];
        const int minab = std::min(a, b);
        const int need = a + 2 * b - L;  // (E) result fits iff 2k >= need
        const int E = (L - a - 2 * b) >= 2 ? (L - a - 2 * b) / 2 : 0;
        for (int s = 0; s < 2; s++) {
            for (int t = 0; t < b; t++) {
                uint8_t c = s == 0 ? B[t] : (uint8_t)(B[b - 1 - t] ^ 1);
                WW[t] = WW[t + b] = c;
            }
            d.ord = ord;
            d.s = s ? -1 : 1;
            for (int i = 0; i < a; i++) {
                const uint8_t* Ap = AA + i;
                for (int j = 0; j < b; j++) {
                    const uint8_t* Wp = WW + j;
                    d.i = i;
                    d.j = j;
                    // ---- (E): e empty
                    const bool c0 = (Wp[b - 1] == (Ap[0] ^ 1));
                    int k = 0;
                    while (k < minab && Ap[a - 1 - k] == (Wp[k] ^ 1)) k++;
                    if (k == minab) {
                        int n = 0;
                        for (int t = 0; t < a; t++) buf[n++] = Ap[t];
                        for (int t = 0; t < b; t++) buf[n++] = Wp[t];
                        n = free_reduce(buf, n);
                        int off, len;
                        cyc_reduce(buf, n, off, len);
                        if (len == 0) {
                            st.degenerate++;
                        } else if (len + b <= L) {
                            if (a < b && 2 * b - a > L) st.indirect++;
                            d.ne = 0;
                            emit(buf + off, len, B, b, d);
                        }
                    } else if (!c0 && 2 * k >= need) {
                        int n = 0;
                        for (int t = 0; t < a - k; t++) buf[n++] = Ap[t];
                        for (int t = k; t < b; t++) buf[n++] = Wp[t];
                        d.ne = 0;
                        emit(buf, n, B, b, d);
                    }
                    // ---- (N): e nonempty, no cancellation anywhere
                    if (E >= 1) {
                        const int f1 = Ap[a - 1] ^ 1, f2 = Ap[0];
                        const int g1 = Wp[0] ^ 1, g2 = Wp[b - 1];
                        // iterative DFS over reduced e, 1 <= |e| <= E
                        int len = 1;
                        e[0] = 0;
                        while (true) {
                            // validity of e[len-1]
                            bool ok = true;
                            const int c = e[len - 1];
                            if (len == 1) ok = (c != f1 && c != f2);
                            else ok = (c != (e[len - 2] ^ 1));
                            if (ok) {
                                if (c != g1 && c != g2) {
                                    int n = 0;
                                    for (int t = 0; t < a; t++) buf[n++] = Ap[t];
                                    for (int t = 0; t < len; t++) buf[n++] = e[t];
                                    for (int t = 0; t < b; t++) buf[n++] = Wp[t];
                                    for (int t = len - 1; t >= 0; t--) buf[n++] = e[t] ^ 1;
                                    d.ne = len;
                                    memcpy(d.e, e, len);
                                    emit(buf, n, B, b, d);
                                }
                                if (len < E) {  // descend
                                    e[len++] = 0;
                                    continue;
                                }
                            }
                            // advance
                            while (len > 0 && e[len - 1] == 3) len--;
                            if (len == 0) break;
                            e[len - 1]++;
                        }
                    }
                }
            }
        }
    }
}

static std::string desc_str(const MoveDesc& d, const uint8_t* u, int nu, const uint8_t* v, int nv) {
    char tmp[256];
    snprintf(tmp, sizeof tmp, "replace %s by CR(rot_%d(%s) e rot_%d(%s^%+d) e^-1), e='%s'",
             d.ord ? "v" : "u", d.i, d.ord ? "v" : "u", d.j, d.ord ? "u" : "v", d.s,
             wstr(d.e, d.ne).c_str());
    (void)u; (void)nu; (void)v; (void)nv;
    return tmp;
}

// ---------------------------------------------------------------- brute force (self-test)
// All results CR(A' c w' c^-1) for all rotations, s, and ALL reduced c with
// |c| <= cb, filtered to total <= L.  Must equal the M-results (README Thm 1).
static void brute_moves(const uint8_t* u, int nu, const uint8_t* v, int nv, int L, int cb, std::set<u128>& out) {
    uint8_t AA[2 * MAXW], WW[2 * MAXW], buf[8 * MAXW], c[MAXW];
    for (int ord = 0; ord < 2; ord++) {
        const uint8_t* A = ord ? v : u;
        const uint8_t* B = ord ? u : v;
        const int a = ord ? nv : nu, b = ord ? nu : nv;
        for (int t = 0; t < a; t++) AA[t] = AA[t + a] = A[t];
        for (int s = 0; s < 2; s++) {
            for (int t = 0; t < b; t++) {
                uint8_t ch = s == 0 ? B[t] : (uint8_t)(B[b - 1 - t] ^ 1);
                WW[t] = WW[t + b] = ch;
            }
            for (int i = 0; i < a; i++)
                for (int j = 0; j < b; j++) {
                    // enumerate all reduced c of length 0..cb
                    for (int len = 0; len <= cb; len++) {
                        // odometer over 4^len, skip unreduced
                        std::vector<int> idx(len, 0);
                        while (true) {
                            bool red = true;
                            for (int t = 0; t + 1 < len; t++)
                                if (idx[t + 1] == (idx[t] ^ 1)) { red = false; break; }
                            if (red) {
                                for (int t = 0; t < len; t++) c[t] = (uint8_t)idx[t];
                                int n = 0;
                                for (int t = 0; t < a; t++) buf[n++] = AA[i + t];
                                for (int t = 0; t < len; t++) buf[n++] = c[t];
                                for (int t = 0; t < b; t++) buf[n++] = WW[j + t];
                                for (int t = len - 1; t >= 0; t--) buf[n++] = c[t] ^ 1;
                                n = free_reduce(buf, n);
                                int off, l2;
                                cyc_reduce(buf, n, off, l2);
                                if (l2 > 0 && l2 + b <= L) out.insert(canonw(buf + off, l2, B, b));
                            }
                            int p = len - 1;
                            while (p >= 0 && idx[p] == 3) { idx[p] = 0; p--; }
                            if (p < 0) break;
                            idx[p]++;
                        }
                    }
                }
        }
    }
}

// ---------------------------------------------------------------- exact BFS (cross-check)
// Breadth-first search over ordered pairs of freely reduced words with the 14
// SAIR moves (refs/sair/.../core.py semantics), total length <= L.
struct H128 {
    size_t operator()(const u128& k) const {
        u64 x = (u64)k * 0x9E3779B97F4A7C15ULL ^ (u64)(k >> 64) * 0xC2B2AE3D27D4EB4FULL;
        x ^= x >> 29;
        return (size_t)x;
    }
};
static inline u128 exkey(const uint8_t* r0, int n0, const uint8_t* r1, int n1) {
    return mkkey(n0, pack(r0, n0), n1, pack(r1, n1));
}
static long exact_bfs(const std::vector<uint8_t>& s0, const std::vector<uint8_t>& s1, int L, long maxstates,
                      std::vector<u128>& projOut, bool& truncated, long& emptySeen) {
    std::unordered_set<u128, H128> seen;
    std::vector<u128> q;
    q.push_back(exkey(s0.data(), (int)s0.size(), s1.data(), (int)s1.size()));
    seen.insert(q[0]);
    truncated = false;
    emptySeen = 0;
    const uint8_t G[4] = {0, 1, 2, 3};  // conjugators x, X, y, Y (g r g^-1)
    size_t head = 0;
    uint8_t r0[64], r1[64], n0buf[160], n1buf[160];
    while (head < q.size()) {
        int n0, n1;
        deckey(q[head++], n0, n1, r0, r1);
        for (int m = 0; m < 14; m++) {
            int a = 0, b = 0;
            const uint8_t *p0 = r0, *p1 = r1;
            int l0 = n0, l1 = n1;
            uint8_t* w = nullptr;
            int wl = 0, which = -1;
            if (m == 0) {  // invert r0
                for (int t = 0; t < n0; t++) n0buf[t] = r0[n0 - 1 - t] ^ 1;
                p0 = n0buf;
            } else if (m == 1) {
                for (int t = 0; t < n1; t++) n1buf[t] = r1[n1 - 1 - t] ^ 1;
                p1 = n1buf;
            } else if (m >= 2 && m <= 5) {
                const bool tgt0 = (m <= 3), invo = (m == 3 || m == 5);
                const uint8_t* T = tgt0 ? r0 : r1;
                const uint8_t* O = tgt0 ? r1 : r0;
                const int nt = tgt0 ? n0 : n1, no = tgt0 ? n1 : n0;
                w = tgt0 ? n0buf : n1buf;
                wl = 0;
                for (int t = 0; t < nt; t++) w[wl++] = T[t];
                for (int t = 0; t < no; t++) w[wl++] = invo ? (O[no - 1 - t] ^ 1) : O[t];
                which = tgt0 ? 0 : 1;
            } else {
                const bool tgt0 = (m <= 9);
                const uint8_t g = G[tgt0 ? m - 6 : m - 10];
                const uint8_t* T = tgt0 ? r0 : r1;
                const int nt = tgt0 ? n0 : n1;
                w = tgt0 ? n0buf : n1buf;
                wl = 0;
                w[wl++] = g;
                for (int t = 0; t < nt; t++) w[wl++] = T[t];
                w[wl++] = g ^ 1;
                which = tgt0 ? 0 : 1;
            }
            if (which >= 0) {
                wl = free_reduce(w, wl);
                if (which == 0) { p0 = w; l0 = wl; }
                else { p1 = w; l1 = wl; }
            }
            (void)a; (void)b;
            if (l0 + l1 > L) continue;
            if (l0 == 0 || l1 == 0) { emptySeen++; continue; }
            u128 k = exkey(p0, l0, p1, l1);
            if (seen.insert(k).second) {
                q.push_back(k);
                if ((long)q.size() >= maxstates) { truncated = true; head = q.size(); break; }
            }
        }
    }
    // project
    projOut.clear();
    projOut.reserve(q.size());
    for (u128 k : q) {
        int n0, n1;
        deckey(k, n0, n1, r0, r1);
        int o0, c0, o1, c1;
        cyc_reduce(r0, n0, o0, c0);
        cyc_reduce(r1, n1, o1, c1);
        projOut.push_back(canonw(r0 + o0, c0, r1 + o1, c1));
    }
    std::sort(projOut.begin(), projOut.end());
    projOut.erase(std::unique(projOut.begin(), projOut.end()), projOut.end());
    return (long)q.size();
}

// ---------------------------------------------------------------- main
static void usage() {
    fprintf(stderr,
            "usage: closure_check --keys F.keys --cap L --start 'u|v' [--target 'u|v']...\n"
            "                     [--threads N] [--selftest N] [--exact-bfs] [--maxexact N]\n");
    exit(2);
}

int main(int argc, char** argv) {
    std::string keysPath, startStr;
    std::vector<std::string> targets;
    int L = -1, threads = 1, selftest = 0;
    bool doExact = false;
    long maxExact = 50000000;
    long bench = 0;  // timing only: S = random classes of total L-1..L (all lookups miss)
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto next = [&]() -> std::string { if (i + 1 >= argc) usage(); return argv[++i]; };
        if (a == "--keys") keysPath = next();
        else if (a == "--cap") L = atoi(next().c_str());
        else if (a == "--start") startStr = next();
        else if (a == "--target") targets.push_back(next());
        else if (a == "--threads") threads = std::max(1, atoi(next().c_str()));
        else if (a == "--selftest") selftest = atoi(next().c_str());
        else if (a == "--exact-bfs") doExact = true;
        else if (a == "--maxexact") maxExact = atol(next().c_str());
        else if (a == "--bench") bench = atol(next().c_str());
        else usage();
    }
    if ((keysPath.empty() && !bench) || L < 2 || startStr.empty()) usage();
    if (L > 32) { fprintf(stderr, "cap > 32 not supported (single words are packed in 64 bits)\n"); return 2; }
    auto T0 = std::chrono::steady_clock::now();
    auto secs = [&]() { return std::chrono::duration<double>(std::chrono::steady_clock::now() - T0).count(); };

    bool fatal = false;
    // ---- start
    std::vector<uint8_t> su, sv;
    if (!parse_pair(startStr, su, sv)) { fprintf(stderr, "bad --start\n"); return 2; }
    printf("cap L = %d\n", L);
    printf("start (exact, freely reduced): %s | %s   total %zu\n", wstr(su.data(), (int)su.size()).c_str(),
           wstr(sv.data(), (int)sv.size()).c_str(), su.size() + sv.size());
    long sdet = det2(su.data(), (int)su.size(), sv.data(), (int)sv.size());
    printf("start abelianisation determinant = %ld %s\n", sdet,
           (sdet == 1 || sdet == -1) ? "(+-1: no empty relator is ever reachable)" : "(NOT +-1: empty-relator argument does not apply!)");
    if (sdet != 1 && sdet != -1) fatal = true;
    if ((int)(su.size() + sv.size()) > L) { printf("start total exceeds cap!\n"); fatal = true; }
    if (su.empty() || sv.empty()) { printf("start has empty relator\n"); fatal = true; }
    u128 startKey = 0;
    {
        int o0, c0, o1, c1;
        cyc_reduce(su.data(), (int)su.size(), o0, c0);
        cyc_reduce(sv.data(), (int)sv.size(), o1, c1);
        if (c0 > 0 && c1 > 0) startKey = canonw(su.data() + o0, c0, sv.data() + o1, c1);
    }

    std::vector<u128> S;
    size_t N = 0;
    if (bench) {
        // TIMING ONLY.  Random cyclically reduced pairs, total L-1 or L, encoded
        // in the input layout and then processed exactly like a dump.
        std::mt19937_64 rng(777);
        S.resize(bench);
        for (long t = 0; t < bench; t++) {
            int tot = L - (int)(rng() % 2), na = 1 + (int)(rng() % (tot - 1)), nb = tot - na;
            uint8_t w[2][64];
            int nn[2] = {na, nb};
            for (int q = 0; q < 2; q++)
                do {
                    for (int i = 0; i < nn[q]; i++) {
                        uint8_t c;
                        do c = (uint8_t)(rng() & 3); while (i > 0 && c == (w[q][i - 1] ^ 1));
                        w[q][i] = c;
                    }
                } while (!is_cyc_reduced(w[q], nn[q]));
            S[t] = mkkey(na, pack(w[0], na), nb, pack(w[1], nb));
        }
        N = S.size();
        goto have_keys;
    }
  {
    // ---- read & re-canonicalise the dump
    FILE* f = fopen(keysPath.c_str(), "rb");
    if (!f) { perror("open keys"); return 2; }
    fseek(f, 0, SEEK_END);
    long fsz = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (fsz % 16) { printf("FORMAT ERROR: file size %ld not a multiple of 16\n", fsz); return 1; }
    N = (size_t)fsz / 16;
    S.resize(N);
    {
        std::vector<uint8_t> raw(16 * std::min<size_t>(N, 1 << 20));
        size_t done = 0;
        while (done < N) {
            size_t chunk = std::min<size_t>(N - done, raw.size() / 16);
            if (fread(raw.data(), 16, chunk, f) != chunk) { printf("read error\n"); return 1; }
            for (size_t t = 0; t < chunk; t++) {
                // 16-byte little-endian key, assembled byte by byte (independent of the host byte order)
                u128 k = 0;
                for (int by = 15; by >= 0; by--) k = (k << 8) | (u128)raw[16 * t + by];
                S[done + t] = k;
            }
            done += chunk;
        }
    }
    fclose(f);
  }
have_keys:
    printf("keys read: %zu  (%.1f s)\n", N, secs());
    size_t badFormat = 0, notSorted = 0, badDet = 0, sameForm = 0;
    std::vector<size_t> byTot(65, 0);
    {
        uint8_t a[64], b[64];
        for (size_t t = 0; t < N; t++) {
            u128 k = S[t];
            if (t > 0 && !(S[t - 1] < k)) notSorted++;  // informational only
            int na = (int)(k >> 122), nb = (int)((k >> 116) & 63);
            bool ok = na >= 1 && nb >= 1 && na + nb <= L && na <= MAXW && nb <= MAXW;
            if (ok) {
                u128 letters = k & (((u128)1 << 116) - 1);
                if (2 * (na + nb) < 116 && (letters >> (2 * (na + nb))) != 0) ok = false;  // stray bits
            }
            if (ok) {
                deckey(k, na, nb, a, b);
                ok = is_cyc_reduced(a, na) && is_cyc_reduced(b, nb);
            }
            if (!ok) {
                if (badFormat < 5) printf("  bad key #%zu (na=%d nb=%d)\n", t, na, nb);
                badFormat++;
                S[t] = 0;
                continue;
            }
            long dt = det2(a, na, b, nb);
            if (dt != 1 && dt != -1) badDet++;
            byTot[na + nb]++;
            S[t] = canonw(a, na, b, nb);
            if (S[t] == k) sameForm++;
        }
    }
    printf("decoded: %zu bad (not cyclically reduced / total > cap / malformed)\n", badFormat);
    if (notSorted) printf("note: input keys not strictly increasing at %zu positions (informational)\n", notSorted);
    if (badFormat) fatal = true;
    printf("note: %zu of %zu input keys are already in our canonical form (informational)\n", sameForm, N);
    std::sort(S.begin(), S.end());
    size_t distinct = std::unique(S.begin(), S.end()) - S.begin();
    S.resize(distinct);
    S.shrink_to_fit();
    printf("distinct classes after OUR canonicalisation: %zu  (%s)\n", distinct,
           distinct == N ? "= number of keys, no duplicates" : "DUPLICATES: some keys denote the same class");
    if (distinct != N) fatal = true;
    if (badDet) { printf("ERROR: %zu classes with determinant != +-1 (not reachable from a det +-1 start)\n", badDet); fatal = true; }
    printf("classes by total length (as read):\n");
    for (int t = 0; t <= 64; t++)
        if (byTot[t]) printf("  total %2d: %zu\n", t, byTot[t]);
    printf("canonicalisation + sort: %.1f s\n", secs());

    auto inS = [&](u128 k) { return std::binary_search(S.begin(), S.end(), k); };
    bool startIn = startKey != 0 && inS(startKey);
    printf("start class %s : %s\n", keystr(startKey).c_str(), startIn ? "IN S" : "NOT in S");
    for (auto& ts : targets) {
        std::vector<uint8_t> tu, tv;
        if (!parse_pair(ts, tu, tv)) { printf("bad target %s\n", ts.c_str()); continue; }
        int o0, c0, o1, c1;
        cyc_reduce(tu.data(), (int)tu.size(), o0, c0);
        cyc_reduce(tv.data(), (int)tv.size(), o1, c1);
        if (!c0 || !c1) { printf("target %s: empty relator, not a class\n", ts.c_str()); continue; }
        u128 tk = canonw(tu.data() + o0, c0, tv.data() + o1, c1);
        printf("target %-22s (total %2d): %s\n", ts.c_str(), c0 + c1, inS(tk) ? "IN S" : "not in S");
    }

    // ---- optional self-test of the move-set reduction (Theorem 1)
    if (selftest > 0 && S.empty()) printf("selftest: skipped (no classes)\n");
    if (selftest > 0 && !S.empty()) {
        std::mt19937_64 rng(12345);
        int tested = 0, mism = 0;
        GenStats gst;
        for (int it = 0; it < 200 * selftest && tested < selftest; it++) {
            u128 k = S[rng() % S.size()];
            int na, nb;
            uint8_t a[64], b[64];
            deckey(k, na, nb, a, b);
            int cb = (L - na - nb) / 2;
            if (cb > 5) continue;
            std::set<u128> mine, brute;
            gen_moves(a, na, b, nb, L, gst, [&](const uint8_t* r, int nr, const uint8_t* B, int nB, const MoveDesc&) {
                mine.insert(canonw(r, nr, B, nB));
            });
            brute_moves(a, na, b, nb, L, cb, brute);
            if (mine != brute) {
                mism++;
                size_t extra = 0, miss = 0;
                for (auto x : mine) if (!brute.count(x)) extra++;
                for (auto x : brute) if (!mine.count(x)) miss++;
                printf("SELFTEST MISMATCH class %s: M-only %zu, brute-only %zu\n", keystr(k).c_str(), extra, miss);
            }
            tested++;
        }
        printf("selftest: %d classes, restricted M-results == brute-force results (all c, |c|<=(L-|u|-|v|)/2): %s\n",
               tested, mism ? "NO" : "yes");
        if (mism) fatal = true;
    }

    // ---- closure check
    std::atomic<size_t> nextIdx(0);
    std::atomic<u64> results(0), missing(0), degenerate(0), indirect(0);
    std::mutex mx;
    std::vector<std::string> examples;
    std::vector<u128> missKeys;
    const size_t CH = 4096;
    auto worker = [&]() {
        GenStats st;
        u64 myRes = 0, myMiss = 0;
        std::vector<u128> myMissKeys;
        std::vector<u128> local;
        while (true) {
            size_t lo = nextIdx.fetch_add(CH);
            if (lo >= S.size()) break;
            size_t hi = std::min(S.size(), lo + CH);
            for (size_t t = lo; t < hi; t++) {
                int na, nb;
                uint8_t a[64], b[64];
                deckey(S[t], na, nb, a, b);
                local.clear();
                gen_moves(a, na, b, nb, L, st, [&](const uint8_t* r, int nr, const uint8_t* B, int nB, const MoveDesc& d) {
                    u128 k = canonw(r, nr, B, nB);
                    myRes++;
                    if (!inS(k)) {
                        myMiss++;
                        if (!bench && myMissKeys.size() < 20000000) myMissKeys.push_back(k);
                        std::lock_guard<std::mutex> g(mx);
                        if (examples.size() < 5)
                            examples.push_back("  " + keystr(S[t]) + "  --[" + desc_str(d, a, na, b, nb) + "]-->  " +
                                               wstr(r, nr) + "|" + wstr(B, nB) + "  (class " + keystr(k) + ", total " +
                                               std::to_string(nr + nB) + ")");
                    }
                });
            }
        }
        results += myRes;
        missing += myMiss;
        degenerate += st.degenerate;
        indirect += st.indirect;
        std::lock_guard<std::mutex> g(mx);
        missKeys.insert(missKeys.end(), myMissKeys.begin(), myMissKeys.end());
    };
    double tc0 = secs();
    std::vector<std::thread> th;
    for (int t = 0; t < threads; t++) th.emplace_back(worker);
    for (auto& t : th) t.join();
    double tc = secs() - tc0;
    std::sort(missKeys.begin(), missKeys.end());
    missKeys.erase(std::unique(missKeys.begin(), missKeys.end()), missKeys.end());
    printf("closure: %llu move results with total <= %d examined\n", (unsigned long long)results.load(), L);
    printf("closure: %llu of them are case-E2 with a < b and 2b - a > L (no one-step in-cap realisation)\n",
           (unsigned long long)indirect.load());
    if (degenerate) printf("note: %llu products reduced to the empty word (det 0 classes)\n", (unsigned long long)degenerate.load());
    printf("closure: %llu results NOT in S (%zu distinct classes)\n", (unsigned long long)missing.load(), missKeys.size());
    for (auto& e : examples) printf("%s\n", e.c_str());
    printf("closure time: %.2f s with %d thread(s) = %.2f us/class (thread-seconds), %.0f classes/s\n", tc, threads,
           S.empty() ? 0.0 : tc * threads * 1e6 / S.size(), S.empty() ? 0.0 : S.size() / tc);

    // ---- optional exact BFS cross-check
    if (doExact) {
        std::vector<u128> proj;
        bool trunc;
        long emp;
        double te0 = secs();
        long ns = exact_bfs(su, sv, L, maxExact, proj, trunc, emp);
        size_t pNotS = 0, sNotP = 0;
        for (u128 k : proj) if (!inS(k)) pNotS++;
        sNotP = S.size() - (proj.size() - pNotS);
        printf("exact BFS: %ld exact states%s, %zu projected classes, empty-relator states hit: %ld (%.1f s)\n", ns,
               trunc ? " (TRUNCATED)" : "", proj.size(), emp, secs() - te0);
        printf("exact BFS: projected classes not in S: %zu; classes of S not projected: %zu%s\n", pNotS, sNotP,
               (!trunc && pNotS == 0 && sNotP == 0) ? "  => S == projection of exact capped component" : "");
    }

    bool pass = !fatal && startIn && missing.load() == 0;
    printf("RESULT: %s  (classes=%zu, start %s, results outside S=%llu)\n", pass ? "PASS" : "FAIL", S.size(),
           startIn ? "in S" : "NOT in S", (unsigned long long)missing.load());
    return pass ? 0 : 1;
}
