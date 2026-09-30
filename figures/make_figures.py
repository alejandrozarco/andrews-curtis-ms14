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

OUT = os.path.join(ROOT, "figures")
THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9",
                  axis="#c3c2b7", s1="#2a78d6", s2="#eb6834"),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a",
                 axis="#383835", s1="#3987e5", s2="#d95926"),
}
STARTS = {"XyyxYYY|XXXYxxy": "P1 (ac-02089)", "XyyxYYY|XXXYxxY": "P2 (ac-08126)"}


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
        if not re.match(r"exh_P[12]_c\d+\.log$", fn):
            continue
        for line in open(os.path.join(ROOT, "runs", fn)):
            m = re.match(r"RESULT start=(\S+) cap=(\d+) .*states=(\d+) .*complete=1", line)
            if m and m.group(1) in STARTS:
                res.setdefault(m.group(1), {})[int(m.group(2))] = int(m.group(3))
    return res


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
    fig.tight_layout(); fig.savefig(os.path.join(OUT, name), facecolor=t["surface"]); plt.close(fig)


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
    fig.tight_layout(); fig.savefig(os.path.join(OUT, name), facecolor=t["surface"]); plt.close(fig)


if __name__ == "__main__":
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none"})
    res = search_results(); exact, cyc = certificate_profile()
    for mode, t in THEMES.items():
        fig_search(t, f"search_growth_{mode}.svg", res)
        fig_path(t, f"certificate_profile_{mode}.svg", exact, cyc)
    print("wrote figures to", OUT)
