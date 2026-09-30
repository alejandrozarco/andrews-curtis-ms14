#!/usr/bin/env python3
"""Regenerate the figures in figures/ from the data in this repository (light and dark variants).
usage: python3 figures/make_figures.py        (needs matplotlib)"""
import json, os, re, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from verify import apply, reduce_word  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch  # noqa: E402

OUT = os.path.join(ROOT, "figures")
THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9",
                  axis="#c3c2b7", s1="#2a78d6", s2="#eb6834"),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a",
                 axis="#383835", s1="#3987e5", s2="#d95926"),
}
STARTS = {"XyyxYYY|XXXYxxy": "P1 (ac-02089)", "XyyxYYY|XXXYxxY": "P2 (ac-08126)"}
# the length-14 cases of the map figure: name -> (relators as acsearch start string, SAIR ACC id)
CASES = {"P1": ("XyyxYYY|XXXYxxy", "ac-02089"), "C6": ("xxyxxYY|xyXYYXy", None),
         "P2": ("XyyxYYY|XXXYxxY", "ac-08126"), "C3": ("xxyXy|xyyyyyxYY", None),
         "C4": ("xxxxyXy|xyyyxYY", None), "AK(3)": ("xxxYYYY|xyxYXY", "ac-00399"), "trivial": ("x|y", None)}


def style(ax, t):
    ax.set_facecolor(t["surface"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(t["axis"])
    ax.tick_params(colors=t["muted"], labelsize=9, length=0)
    ax.xaxis.label.set_color(t["ink2"]); ax.yaxis.label.set_color(t["ink2"])
    ax.grid(axis="y", color=t["grid"], linewidth=0.6); ax.set_axisbelow(True)


def search_results():
    res = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "runs"))):
        if not re.match(r"exh_P[12]_c\d+(_k\d+)?\.log$", fn):
            continue
        for r in read_results(fn):
            if r["start"] in STARTS:
                res.setdefault(r["start"], {})[r["cap"]] = r["states"]
    return res


def read_results(fn):
    """complete runs in runs/<fn> that satisfy the conjugator-bound completeness condition, with their hits"""
    out, hits = [], []
    lines = open(os.path.join(ROOT, "runs", fn)).read().splitlines()
    for n, line in enumerate(lines):
        h = re.match(r"HIT target \d+ \((\S+)\)", line)
        if h:
            hits.append(h.group(1))
        m = re.match(r"RESULT start=(\S+) cap=(\d+) conj=(\d+) .*states=(\d+) .*complete=1 hit=\d+ overflow=0", line)
        if m:
            # conjugators up to floor((cap - m)/2) are needed, m = minimum total length in the component
            mt = int(re.match(r"states by total length: (\d+):", lines[n + 1]).group(1))
            cap, conj = int(m.group(2)), int(m.group(3))
            if conj >= (cap - mt) // 2:
                out.append(dict(start=m.group(1), cap=cap, states=int(m.group(4)), hits=hits))
    return out


def exhausted_caps():
    """largest completely enumerated cap per case, and the other cases found inside that component"""
    names = {canon_start(v[0]): k for k, v in CASES.items()}
    best = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "runs"))):
        if re.match(r"exh_\w+_c\d+(_k\d+)?\.log$", fn):
            for r in read_results(fn):
                name = names[canon_start(r["start"])]
                found = sorted({names[canon_start(h)] for h in r["hits"]} - {name})
                if r["cap"] > best.get(name, (0,))[0]:
                    best[name] = (r["cap"], found)
    return best


def canon_start(st):
    """class of a presentation "u|v" in acsearch's quotient (logs print targets canonicalised, starts as given)"""
    from make_cert import canon, parse  # noqa: E402
    return canon([parse(w) for w in st.split("|")])


def cyclic_len(w):
    w = list(w)
    while len(w) >= 2 and w[0] == -w[-1]:
        w = w[1:-1]
    return len(w)


def certificate_profile():
    c = json.load(open(os.path.join(ROOT, "certs", "P1_equiv_C6.json")))
    S = [reduce_word(list(r)) for r in c["initial"]]
    exact, cyc = [sum(map(len, S))], [sum(cyclic_len(r) for r in S)]
    for mv in c["moves"]:
        S = apply(S, mv, c["generators"])
        exact.append(sum(map(len, S))); cyc.append(sum(cyclic_len(r) for r in S))
    return exact, cyc


def fig_search(t, name, res):
    fig, ax = plt.subplots(figsize=(7.5, 4.2)); fig.patch.set_facecolor(t["surface"])
    for (start, label), col in zip(STARTS.items(), (t["s1"], t["s2"])):
        caps = sorted(res[start]); vals = [res[start][c] for c in caps]
        ax.plot(caps, vals, color=col, linewidth=2, marker="o", markersize=8,
                markeredgecolor=t["surface"], markeredgewidth=2, label=label)
        ax.annotate(f"{vals[-1]:,}", (caps[-1], vals[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=9, color=t["ink2"])
    ax.set_yscale("log"); ax.set_xticks(sorted(next(iter(res.values()))))
    ticks = [2e6, 5e6, 1e7, 2e7, 5e7, 1e8]
    ax.set_yticks(ticks); ax.set_yticklabels([f"{v/1e6:g}M" for v in ticks]); ax.minorticks_off()
    ax.set_ylim(1.5e6, 1.3e8)
    ax.set_xlim(28.7, 32.9)
    style(ax, t)
    ax.set_xlabel("cap on total cyclically reduced relator length")
    ax.set_ylabel("states in the capped component")
    ax.set_title("Capped AC components: no AK(3), trivial presentation or other start found",
                 color=t["ink"], fontsize=11, loc="left")
    leg = ax.legend(frameon=False, fontsize=9, loc="upper left")
    for txt in leg.get_texts():
        txt.set_color(t["ink2"])
    fig.tight_layout(); fig.savefig(os.path.join(OUT, name), facecolor=t["surface"], metadata={"Date": None}); plt.close(fig)


def fig_path(t, name, exact, cyc):
    fig, ax = plt.subplots(figsize=(7.5, 4.2)); fig.patch.set_facecolor(t["surface"])
    x = range(len(exact))
    ax.plot(x, exact, color=t["s1"], linewidth=1.5, label="exact words")
    ax.plot(x, cyc, color=t["s2"], linewidth=1.5, label="cyclically reduced")
    for series, col in ((exact, t["s1"]), (cyc, t["s2"])):
        i = max(range(len(series)), key=series.__getitem__)
        ax.annotate(f"peak {series[i]}", (i, series[i]), xytext=(0, 6), textcoords="offset points",
                    ha="center", fontsize=9, color=t["ink2"])
    style(ax, t)
    ax.set_xlabel("move index"); ax.set_ylabel("total relator length"); ax.set_ylim(10, max(exact) + 6)
    ax.set_title("Certificate P1 → C6: total relator length along the 1066 moves",
                 color=t["ink"], fontsize=11, loc="left")
    leg = ax.legend(frameon=False, fontsize=9, loc="lower right")
    for txt in leg.get_texts():
        txt.set_color(t["ink2"])
    fig.tight_layout(); fig.savefig(os.path.join(OUT, name), facecolor=t["surface"], metadata={"Date": None}); plt.close(fig)


def fig_map(t, name, caps, cert_moves):
    fig, ax = plt.subplots(figsize=(7.5, 4.3)); fig.patch.set_facecolor(t["surface"])
    ax.set_facecolor(t["surface"]); ax.set_xlim(-0.1, 10.1); ax.set_ylim(0, 5.8); ax.set_aspect("equal"); ax.axis("off")
    pos = {"trivial": (3.0, 4.45), "AK(3)": (7.0, 4.45),
           "P1": (0.95, 2.35), "C6": (3.0, 2.35), "P2": (5.05, 2.35), "C3": (7.1, 2.35), "C4": (9.15, 2.35)}
    groups = {g: [g] + found for g, (_, found) in caps.items()}  # searched start -> cases in its component
    member = {c: g for g, cs in groups.items() for c in cs}
    for g, cs in groups.items():  # one box per enumerated component, labelled with its cap
        xs = [pos[c][0] for c in cs]
        x0, x1 = min(xs) - 0.9, max(xs) + 0.9
        ax.add_patch(FancyBboxPatch((x0, 0.75), x1 - x0, 2.15, boxstyle="round,pad=0,rounding_size=0.15",
                                    facecolor="none", edgecolor=t["s1"], linewidth=1.2))
        ax.text((x0 + x1) / 2, 0.98, f"cap L = {caps[g][0]}", ha="center", va="center",
                fontsize=8.5, color=t["s1"], fontweight="bold")
    if member.get("C6") == member.get("P1") is not None:
        (xa, y), (xb, _) = pos["P1"], pos["C6"]
        ax.plot([xa + 0.34, xb - 0.34], [y, y], color=t["s2"], linewidth=3, solid_capstyle="round")
        ax.text((xa + xb) / 2, y + 0.14, "certificate", ha="center", va="bottom", fontsize=7.5, color=t["s2"])
        ax.text((xa + xb) / 2, y - 0.14, f"{cert_moves} moves", ha="center", va="top", fontsize=7.5, color=t["s2"])
    for c, (x, y) in pos.items():
        rel, sair = CASES[c]
        searched = c in member
        ax.add_patch(Circle((x, y), 0.32, facecolor=t["s1"] if searched else t["surface"],
                            edgecolor=t["s1"] if searched else t["muted"], linewidth=1.4))
        ax.text(x, y, "1" if c == "trivial" else c, ha="center", va="center", fontsize=9 if len(c) < 4 else 7.5,
                fontweight="bold", color=t["surface"] if searched else t["ink"])
        sub = "x\ny" if c == "trivial" else rel.replace("|", "\n")
        ax.text(x, y - 0.42, sub + (f"\n{sair}" if sair else ""), ha="center", va="top", fontsize=7.5,
                color=t["ink2"], family="DejaVu Sans Mono", linespacing=1.25)
    for c in ("trivial", "AK(3)"):
        ax.text(pos[c][0] + 0.45, pos[c][1], "trivial presentation" if c == "trivial" else "not enumerated here",
                ha="left", va="center", fontsize=8, color=t["muted"])
    ax.text(-0.1, 5.6, "Length-14 cases: certified link and capped components", ha="left", va="center",
            fontsize=11, color=t["ink"])
    ax.text(-0.1, 0.35, "Each box is the complete component of its start at total length ≤ L; it contains no case "
            "outside the box.\nAny AC path leaving a box, to another case or to the trivial presentation, "
            "reaches total length > L.", ha="left", va="center", fontsize=8, color=t["ink2"], linespacing=1.4)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, name), facecolor=t["surface"], metadata={"Date": None}); plt.close(fig)

if __name__ == "__main__":
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none", "svg.hashsalt": "ac-ms14"})
    res = search_results(); exact, cyc = certificate_profile(); caps = exhausted_caps()
    for mode, t in THEMES.items():
        fig_search(t, f"search_growth_{mode}.svg", res)
        fig_path(t, f"certificate_profile_{mode}.svg", exact, cyc)
        fig_map(t, f"hard_cases_{mode}.svg", caps, len(exact) - 1)
    print("wrote figures to", OUT)
