"""
test-electronics-prompt-size.py
--------------------------------
Extends the prompt-size experiment to the Electronics scenario with a
4th variant: SCRAPED — a bidder who has read the official Apple tech specs
(extracted at runtime from the spec PDFs in data/product-docs/ELECTRONICS/).

4 prompt variants for bidder "Alex" (university student, wants a tablet setup):
  SHORT   : one sentence + budget only
  MEDIUM  : key preferences paragraph with explicit item values
  FULL    : detailed description with exact bundle values and explicit warnings
  SCRAPED : bidder who read official Apple Support tech specs (real documents)

Key experimental hook: Apple Pencil 2nd Gen is INCOMPATIBLE with iPad 9th Gen
(works only with iPad Air / Pro). Will each variant catch this?

Items:
  AIRPODS2      — Apple AirPods 2nd Gen
  AIRPODSPROMAX — Apple AirPods Max
  IPAD9         — Apple iPad 9th Gen
  IPAD12        — Apple iPad Air M2
  APPLEPENCIL2  — Apple Pencil 2nd Gen
  APPLEPENCILPRO — Apple Pencil Pro

Usage:
    cd "DT Study"
    source venv/bin/activate
    python scripts/test-electronics-prompt-size.py
"""

import os
import re
import csv
import statistics
import textwrap
import pypdf
import matplotlib
matplotlib.use("Agg")          # no display needed — saves to file
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from dotenv import load_dotenv

load_dotenv(".env")

from alpha.scenario import ElectronicsScenario as scenario, Bundle
from alpha.person import Seed
from alpha.persons.standard_person.core import StandardValuePipeline

# ── Prompt variants ───────────────────────────────────────────────────────────

SHORT = (
    "Alex is a 22-year-old university student looking for a tablet and stylus "
    "for digital note-taking and studying. Budget around $550."
)

MEDIUM = (
    "Alex is a 22-year-old CS student who wants an iPad and Apple Pencil for "
    "annotating lecture notes and research papers. "
    "Alex values the iPad Air M2 (IPAD12) at $420 — the top priority for its "
    "speed and note-taking compatibility. The Apple Pencil Pro (APPLEPENCILPRO) "
    "is valued at $80 standalone, but jumps to a $100 complement when paired "
    "with IPAD12 — together they form the core $520 setup Alex is after. "
    "The Apple Pencil 2nd Gen (APPLEPENCIL2) is an acceptable alternative at $65. "
    "The iPad 9th Gen (IPAD9) is a budget fallback at $200. "
    "The AirPods Max (AIRPODSPROMAX) would be useful for studying in noisy "
    "environments — valued at $180. The basic AirPods 2nd Gen (AIRPODS2) are "
    "a nice-to-have at $70. "
    "Alex only ever uses one pair of headphones and one stylus at a time — "
    "duplicate items of the same type add no extra value."
)

FULL = (
    "### Alex's Auction Preferences and Valuation of Bundles\n\n"
    "**Background**\n"
    "Alex is a 22-year-old computer science student who relies on digital "
    "note-taking for lectures and research papers. Alex has been saving for a "
    "tablet-and-stylus setup and sees this auction as an opportunity to acquire "
    "the tools needed for academic success. Alex's priority is a functional "
    "note-taking setup that pairs well with an existing iPhone and MacBook.\n\n"
    "**Item Valuations**\n\n"
    "- AIRPODS2 (AirPods 2nd Gen): $70. Alex already owns Sony earphones but "
    "would appreciate wireless earbuds for commuting and gym sessions. "
    "Convenient but not a priority.\n"
    "- AIRPODSPROMAX (AirPods Max): $180. The active noise cancellation is "
    "highly attractive for studying in busy libraries. Heavy for long sessions "
    "but primarily used at a desk. Valued as a focus-enhancing tool.\n"
    "- IPAD9 (iPad 9th Gen): $200. A capable but aging model. Suitable for "
    "reading PDFs and basic tasks. Notable limitation: only compatible with "
    "Apple Pencil 1st Gen — not the 2nd Gen or Pro.\n"
    "- IPAD12 (iPad Air M2): $420. Alex's top priority. M2 chip future-proofs "
    "the device through graduation. Compatible with both Apple Pencil 2nd Gen "
    "and Pencil Pro. 11-inch display is ideal for PDFs and paper annotation.\n"
    "- APPLEPENCIL2 (Apple Pencil 2nd Gen): $65 standalone. Magnetically "
    "attaches and wirelessly charges on IPAD12. Essential for the note-taking "
    "workflow. IMPORTANT: incompatible with IPAD9.\n"
    "- APPLEPENCILPRO (Apple Pencil Pro): $80 standalone. Preferred over the "
    "2nd Gen for its squeeze gesture and barrel roll. Also incompatible with "
    "IPAD9.\n\n"
    "**Bundle Valuations**\n\n"
    "- IPAD12 alone: $420\n"
    "- IPAD12 + APPLEPENCILPRO: $520 (synergy — unlocks full note-taking workflow)\n"
    "- IPAD12 + APPLEPENCIL2: $505 (slightly less preferred than Pro)\n"
    "- IPAD12 + APPLEPENCILPRO + AIRPODSPROMAX: $700 (ideal study setup)\n"
    "- IPAD12 + APPLEPENCILPRO + AIRPODS2: $590\n"
    "- IPAD9 alone: $200\n"
    "- IPAD9 + APPLEPENCIL2: $200 (no added value — incompatible; pencil "
    "cannot be used with iPad 9th Gen)\n"
    "- AIRPODSPROMAX alone: $180\n"
    "- AIRPODS2 alone: $70\n"
    "- AIRPODS2 + AIRPODSPROMAX: $180 (substitutes — can only wear one pair; "
    "value equals the better one)\n"
    "- APPLEPENCIL2 + APPLEPENCILPRO: $80 (substitutes — only one pencil "
    "useful at a time; value = preferred one)\n"
    "- ALL items: $700 (same as best bundle — redundant items add nothing)\n\n"
    "**Evaluation Process**\n"
    "Alex applies a substitution-first rule: items of the same functional "
    "category (headphones, stylus) are valued at the price of the preferred "
    "one — no additive bonus for duplicates. Complementary pairs (iPad + "
    "compatible Pencil) receive a synergy premium because together they enable "
    "a workflow neither item enables alone. Incompatible combinations "
    "(IPAD9 + APPLEPENCIL2 or APPLEPENCILPRO) receive no additional value — "
    "Alex will not pay extra for an item that cannot be used with the main device."
)

def build_scraped_desc(pdf_dir="data/product-docs/ELECTRONICS", max_chars_per_product=2000):
    """Build SCRAPED variant by extracting text from official Apple spec PDFs."""
    products = [
        ("AIRPODS2",       "Apple AirPods 2nd Generation"),
        ("AIRPODSPROMAX",  "Apple AirPods Max"),
        ("IPAD9",          "Apple iPad 9th Generation"),
        ("IPAD12",         "Apple iPad Air 11-inch (M2)"),
        ("APPLEPENCIL2",   "Apple Pencil 2nd Generation"),
        ("APPLEPENCILPRO", "Apple Pencil Pro"),
    ]
    sections = []
    for code, name in products:
        pdf_path = os.path.join(pdf_dir, f"{code}_specs.pdf")
        if not os.path.exists(pdf_path):
            sections.append(f"[{code} — {name}]\n(spec PDF not found)")
            continue
        reader = pypdf.PdfReader(pdf_path)
        raw = " ".join(p.extract_text() or "" for p in reader.pages)
        raw = re.sub(r'\s+', ' ', raw).strip()
        sections.append(f"[{code} — {name}]\n{raw[:max_chars_per_product]}")

    return (
        "Alex is a 22-year-old CS student participating in the auction. "
        "Before bidding, Alex read the official Apple Support tech spec pages "
        "for each item. The relevant excerpts are reproduced below.\n\n"
        "--- OFFICIAL APPLE SUPPORT TECH SPECS ---\n\n"
        + "\n\n".join(sections)
        + "\n\n--- END OF TECH SPECS ---\n\n"
        "Alex's goal is to acquire an iPad and a compatible stylus for "
        "university note-taking and PDF annotation. "
        "Budget ceiling: approximately $550. "
        "Alex makes purchasing decisions strictly based on the official "
        "compatibility information in the specs above."
    )


SCRAPED = build_scraped_desc()

VARIANTS = {
    "SHORT  ": SHORT,
    "MEDIUM ": MEDIUM,
    "FULL   ": FULL,
    "SCRAPED": SCRAPED,
}

VARIANT_COLORS = {
    "SHORT  ": "#e74c3c",
    "MEDIUM ": "#f39c12",
    "FULL   ": "#2ecc71",
    "SCRAPED": "#8e44ad",
}

# ── Representative bundles ────────────────────────────────────────────────────
# Order: AIRPODS2, AIRPODSPROMAX, IPAD9, IPAD12, APPLEPENCIL2, APPLEPENCILPRO

TEST_BUNDLES = [
    # Singletons
    Bundle(scenario, [1, 0, 0, 0, 0, 0]),  # AIRPODS2
    Bundle(scenario, [0, 1, 0, 0, 0, 0]),  # AIRPODSPROMAX
    Bundle(scenario, [0, 0, 1, 0, 0, 0]),  # IPAD9
    Bundle(scenario, [0, 0, 0, 1, 0, 0]),  # IPAD12
    Bundle(scenario, [0, 0, 0, 0, 1, 0]),  # APPLEPENCIL2
    Bundle(scenario, [0, 0, 0, 0, 0, 1]),  # APPLEPENCILPRO
    # Key combos — COMPATIBLE
    Bundle(scenario, [0, 0, 0, 1, 0, 1]),  # IPAD12 + APPLEPENCILPRO  ← primary setup
    Bundle(scenario, [0, 0, 0, 1, 1, 0]),  # IPAD12 + APPLEPENCIL2
    Bundle(scenario, [0, 1, 0, 1, 0, 1]),  # IPAD12 + AIRPODSPROMAX + APPLEPENCILPRO ← ideal
    Bundle(scenario, [1, 0, 0, 1, 0, 1]),  # IPAD12 + AIRPODS2 + APPLEPENCILPRO
    # Key combo — INCOMPATIBLE (Pencil 2nd Gen does NOT work with iPad 9)
    Bundle(scenario, [0, 0, 1, 0, 1, 0]),  # IPAD9 + APPLEPENCIL2  ← incompatibility trap
    Bundle(scenario, [0, 0, 1, 0, 0, 1]),  # IPAD9 + APPLEPENCILPRO ← also incompatible
    # Substitutes (two of same category)
    Bundle(scenario, [1, 1, 0, 0, 0, 0]),  # AIRPODS2 + AIRPODSPROMAX (redundant)
    Bundle(scenario, [0, 0, 0, 0, 1, 1]),  # APPLEPENCIL2 + APPLEPENCILPRO (redundant)
    # All items
    Bundle(scenario, [1, 1, 1, 1, 1, 1]),  # ALL items
]

BUNDLE_LABELS = [
    "AIRPODS2",
    "AIRPODSPROMAX",
    "IPAD9",
    "IPAD12",
    "APPLEPENCIL2",
    "APPLEPENCILPRO",
    "IPAD12+PENCILPRO",
    "IPAD12+PENCIL2",
    "IPAD12+MAX+PENCILPRO",
    "IPAD12+PODS2+PENCILPRO",
    "IPAD9+PENCIL2 [INCOMPAT]",   # ← incompatibility trap
    "IPAD9+PENCILPRO [INCOMPAT]", # ← also incompatible
    "PODS2+PODSMAX [SUBST]",
    "PENCIL2+PENCILPRO [SUBST]",
    "ALL items",
]

# Items to highlight as "incompatibility traps" — index in TEST_BUNDLES
INCOMPATIBLE_INDICES = [10, 11]

# ── Run valuations ────────────────────────────────────────────────────────────

pipeline = StandardValuePipeline()
results = {}

print("=" * 70)
print("  Electronics Prompt Size Experiment — Alex (student buyer)")
print("  Scenario: ELECTRONICS (6 items)")
print(f"  Bundles tested: {len(TEST_BUNDLES)}")
print(f"  Variants: {', '.join(v.strip() for v in VARIANTS)}")
print(f"  SCRAPED variant: {len(SCRAPED):,} chars (~{len(SCRAPED)//4:,} tokens)")
print("=" * 70)

for variant_name, description in VARIANTS.items():
    print(f"\n{'─'*70}")
    print(f"  Variant: {variant_name.strip()}")
    print(f"  Description length: ~{len(description)//4} tokens")
    print(f"{'─'*70}")

    seed = Seed(code="alex", scenario="ELECTRONICS", description=description)
    values = []

    for bundle, label in zip(TEST_BUNDLES, BUNDLE_LABELS):
        try:
            value = pipeline(scenario=scenario, seed=seed, bundle=bundle)
            values.append(value)
            flag = "  ← INCOMPAT TRAP" if label.endswith("[INCOMPAT]") else ""
            print(f"  {label:<35} → ${value:,.0f}{flag}")
        except Exception as e:
            values.append(None)
            print(f"  {label:<35} → ERROR: {e}")

    results[variant_name.strip()] = values

# ── Side-by-side comparison ───────────────────────────────────────────────────

print(f"\n{'='*90}")
print("  SIDE-BY-SIDE COMPARISON")
print(f"{'='*90}")
header = f"  {'Bundle':<35} {'SHORT':>8} {'MEDIUM':>8} {'FULL':>8} {'SCRAPED':>8}"
print(header)
print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

short_v   = results.get("SHORT",   [None]*len(TEST_BUNDLES))
medium_v  = results.get("MEDIUM",  [None]*len(TEST_BUNDLES))
full_v    = results.get("FULL",    [None]*len(TEST_BUNDLES))
scraped_v = results.get("SCRAPED", [None]*len(TEST_BUNDLES))

def fmt(v):
    return f"${v:,.0f}" if v is not None else "ERR"

def pct_diff(a, b):
    """Absolute % difference of a vs b (b = reference)."""
    if a is None or b is None:
        return None
    if b == 0:
        return 0.0 if a == 0 else 100.0
    return abs(a - b) / b * 100

for i, label in enumerate(BUNDLE_LABELS):
    s, m, f, sc = short_v[i], medium_v[i], full_v[i], scraped_v[i]
    flag = "  ◄ incompat" if i in INCOMPATIBLE_INDICES else ""
    print(f"  {label:<35} {fmt(s):>8} {fmt(m):>8} {fmt(f):>8} {fmt(sc):>8}{flag}")

print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

# Summary stats vs FULL
for name, vals in [("SHORT", short_v), ("MEDIUM", medium_v), ("SCRAPED", scraped_v)]:
    diffs = [pct_diff(vals[i], full_v[i]) for i in range(len(TEST_BUNDLES))
             if vals[i] is not None and full_v[i] is not None]
    if diffs:
        print(f"\n  {name:<8} vs FULL — Mean diff: {statistics.mean(diffs):.1f}%  "
              f"Max: {max(diffs):.1f}%")

# Compatibility trap analysis
print(f"\n{'='*70}")
print("  COMPATIBILITY TRAP ANALYSIS")
print(f"  (IPAD9 + PENCIL2/PRO should = IPAD9 alone — pencil is useless)")
print(f"{'='*70}")
print(f"  {'Variant':<10} {'IPAD9 alone':>12} {'IPAD9+PENCIL2':>14} "
      f"{'Extra paid':>12} {'IPAD9+PENCILPRO':>16} {'Extra paid':>12}")
print(f"  {'-'*10} {'-'*12} {'-'*14} {'-'*12} {'-'*16} {'-'*12}")

for name, vals in [("SHORT", short_v), ("MEDIUM", medium_v),
                   ("FULL", full_v), ("SCRAPED", scraped_v)]:
    ipad9   = vals[2]   # IPAD9 singleton
    incompat_p2  = vals[10]  # IPAD9 + PENCIL2
    incompat_pro = vals[11]  # IPAD9 + PENCILPRO

    extra_p2  = (incompat_p2  - ipad9) if (ipad9 is not None and incompat_p2  is not None) else None
    extra_pro = (incompat_pro - ipad9) if (ipad9 is not None and incompat_pro is not None) else None

    print(f"  {name:<10} {fmt(ipad9):>12} {fmt(incompat_p2):>14} "
          f"{'$'+str(int(extra_p2)) if extra_p2 is not None else 'N/A':>12} "
          f"{fmt(incompat_pro):>16} "
          f"{'$'+str(int(extra_pro)) if extra_pro is not None else 'N/A':>12}")

# Token cost summary
print(f"\n{'='*70}")
print("  TOKEN COST ESTIMATE (for full 64-bundle XOR table)")
print(f"{'='*70}")
for name, desc in VARIANTS.items():
    desc_tokens = len(desc) // 4
    total = (desc_tokens + 50) * 64 + 50 * 64
    print(f"  {name.strip():<8}: ~{desc_tokens:>6} tokens/call × 64 = ~{total:>9,} tokens total")

# ── Save CSV ──────────────────────────────────────────────────────────────────

os.makedirs("data/experiments", exist_ok=True)
csv_path = "data/experiments/electronics_prompt_size_results.csv"

with open(csv_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["bundle", "incompatibility_trap", "short", "medium", "full", "scraped",
                     "short_vs_full_pct", "medium_vs_full_pct", "scraped_vs_full_pct"])
    for i, label in enumerate(BUNDLE_LABELS):
        s, m, fv, sc = short_v[i], medium_v[i], full_v[i], scraped_v[i]
        writer.writerow([
            label,
            "YES" if i in INCOMPATIBLE_INDICES else "NO",
            s, m, fv, sc,
            round(pct_diff(s,  fv) or 0, 1),
            round(pct_diff(m,  fv) or 0, 1),
            round(pct_diff(sc, fv) or 0, 1),
        ])

print(f"\n  Results saved → {csv_path}")

# ── Visualisations ────────────────────────────────────────────────────────────

plot_dir = "data/experiments/plots"
os.makedirs(plot_dir, exist_ok=True)

variant_names  = ["SHORT", "MEDIUM", "FULL", "SCRAPED"]
variant_keys   = ["SHORT  ", "MEDIUM ", "FULL   ", "SCRAPED"]
variant_colors = ["#e74c3c", "#f39c12", "#2ecc71", "#8e44ad"]
all_vals = [short_v, medium_v, full_v, scraped_v]

# ── Plot 1: Grouped bar chart — all bundles × all variants ────────────────────

fig, ax = plt.subplots(figsize=(18, 6))
x       = np.arange(len(BUNDLE_LABELS))
n_var   = len(variant_names)
bar_w   = 0.18
offsets = np.linspace(-(n_var-1)/2, (n_var-1)/2, n_var) * bar_w

for i, (name, color, vals) in enumerate(zip(variant_names, variant_colors, all_vals)):
    heights = [v if v is not None else 0 for v in vals]
    bars = ax.bar(x + offsets[i], heights, bar_w, label=name, color=color, alpha=0.85,
                  edgecolor="white", linewidth=0.5)

# Shade incompatibility trap bundles
for idx in INCOMPATIBLE_INDICES:
    ax.axvspan(idx - 0.45, idx + 0.45, alpha=0.08, color="red", zorder=0)
    ax.text(idx, ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 800,
            "⚠ incompat", ha="center", va="bottom", fontsize=7, color="darkred")

ax.set_xticks(x)
ax.set_xticklabels(BUNDLE_LABELS, rotation=40, ha="right", fontsize=8)
ax.set_ylabel("Bundle valuation ($)", fontsize=11)
ax.set_title("Electronics Auction — Bundle Valuations by Prompt Variant\n"
             "(Alex, student bidder — SHORT / MEDIUM / FULL / SCRAPED)",
             fontsize=13, fontweight="bold")
ax.legend(title="Prompt variant", fontsize=9)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
ax.set_ylim(bottom=0)
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
p1 = f"{plot_dir}/1_grouped_bar.png"
plt.savefig(p1, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Plot 1 saved → {p1}")

# ── Plot 2: Heatmap — bundles × variants ─────────────────────────────────────

matrix = np.array([[v if v is not None else 0 for v in vals] for vals in all_vals],
                  dtype=float)   # shape: (n_variants, n_bundles)

fig, ax = plt.subplots(figsize=(16, 4))
im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd", vmin=0)
plt.colorbar(im, ax=ax, label="Value ($)")
ax.set_yticks(range(n_var))
ax.set_yticklabels(variant_names, fontsize=10)
ax.set_xticks(range(len(BUNDLE_LABELS)))
ax.set_xticklabels(BUNDLE_LABELS, rotation=40, ha="right", fontsize=8)
ax.set_title("Electronics — Valuation Heatmap (higher = warmer)", fontsize=12, fontweight="bold")

# Annotate cells with dollar values
for row in range(n_var):
    for col in range(len(BUNDLE_LABELS)):
        val = matrix[row, col]
        ax.text(col, row, f"${val:,.0f}", ha="center", va="center",
                fontsize=7, color="black" if val < matrix.max() * 0.7 else "white")

# Highlight incompatibility trap columns
for idx in INCOMPATIBLE_INDICES:
    ax.add_patch(mpatches.FancyBboxPatch(
        (idx - 0.5, -0.5), 1, n_var,
        boxstyle="square,pad=0", linewidth=2,
        edgecolor="red", facecolor="none", zorder=5))

plt.tight_layout()
p2 = f"{plot_dir}/2_heatmap.png"
plt.savefig(p2, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Plot 2 saved → {p2}")

# ── Plot 3: Mean absolute error vs FULL (per variant) ────────────────────────

compare_variants = [("SHORT", short_v, "#e74c3c"),
                    ("MEDIUM", medium_v, "#f39c12"),
                    ("SCRAPED", scraped_v, "#8e44ad")]

fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
fig.suptitle("Deviation from FULL description — per bundle\n(Alex, Electronics scenario)",
             fontsize=12, fontweight="bold")

for ax, (name, vals, color) in zip(axes, compare_variants):
    diffs = []
    for i in range(len(TEST_BUNDLES)):
        d = pct_diff(vals[i], full_v[i])
        diffs.append(d if d is not None else 0)

    bar_colors = ["#c0392b" if i in INCOMPATIBLE_INDICES else color
                  for i in range(len(diffs))]
    bars = ax.barh(range(len(diffs)), diffs, color=bar_colors, alpha=0.8, edgecolor="white")

    ax.set_yticks(range(len(BUNDLE_LABELS)))
    ax.set_yticklabels(BUNDLE_LABELS, fontsize=7.5)
    ax.set_xlabel("Absolute % diff vs FULL", fontsize=9)
    ax.set_title(f"{name}\n(mean {statistics.mean(diffs):.1f}%)", fontsize=10, fontweight="bold")
    ax.axvline(0, color="black", linewidth=0.8)
    ax.grid(axis="x", alpha=0.3)

    # Annotate incompatibility traps
    for idx in INCOMPATIBLE_INDICES:
        ax.axhline(idx, color="red", linewidth=1, linestyle="--", alpha=0.5)

plt.tight_layout()
p3 = f"{plot_dir}/3_error_vs_full.png"
plt.savefig(p3, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Plot 3 saved → {p3}")

# ── Plot 4: Compatibility trap focus ─────────────────────────────────────────

fig, ax = plt.subplots(figsize=(10, 5))

trap_labels = ["IPAD9 alone", "IPAD9+PENCIL2\n[INCOMPAT]", "IPAD9+PENCILPRO\n[INCOMPAT]"]
trap_indices = [2, 10, 11]
x = np.arange(len(trap_labels))
bar_w = 0.18
offsets = np.linspace(-(n_var-1)/2, (n_var-1)/2, n_var) * bar_w

for i, (name, color, vals) in enumerate(zip(variant_names, variant_colors, all_vals)):
    heights = [vals[idx] if vals[idx] is not None else 0 for idx in trap_indices]
    ax.bar(x + offsets[i], heights, bar_w, label=name, color=color, alpha=0.85,
           edgecolor="white")

# Ideal (rational) line — should equal IPAD9 alone value from FULL
ipad9_full = full_v[2]
if ipad9_full:
    ax.axhline(ipad9_full, color="black", linewidth=1.5, linestyle="--",
               label=f"Expected rational cap (=${ipad9_full:,.0f})")

ax.set_xticks(x)
ax.set_xticklabels(trap_labels, fontsize=10)
ax.set_ylabel("Bundle valuation ($)", fontsize=11)
ax.set_title("Compatibility Trap — Does the LLM 'waste' money on an incompatible pencil?\n"
             "(A rational bidder should value IPAD9+PENCIL ≈ IPAD9 alone)",
             fontsize=11, fontweight="bold")
ax.legend(fontsize=9)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
ax.set_ylim(bottom=0)
ax.grid(axis="y", alpha=0.3)
ax.set_facecolor("#fafafa")
plt.tight_layout()
p4 = f"{plot_dir}/4_compatibility_trap.png"
plt.savefig(p4, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Plot 4 saved → {p4}")

# ── Plot 5: Token cost vs accuracy (scatter) ──────────────────────────────────

token_costs = {
    "SHORT":   (len(SHORT)   // 4 + 50) * 64 + 50 * 64,
    "MEDIUM":  (len(MEDIUM)  // 4 + 50) * 64 + 50 * 64,
    "FULL":    (len(FULL)    // 4 + 50) * 64 + 50 * 64,
    "SCRAPED": (len(SCRAPED) // 4 + 50) * 64 + 50 * 64,
}

mean_errors = {}
for name, vals in [("SHORT", short_v), ("MEDIUM", medium_v),
                   ("FULL", full_v), ("SCRAPED", scraped_v)]:
    diffs = [pct_diff(vals[i], full_v[i]) for i in range(len(TEST_BUNDLES))
             if vals[i] is not None and full_v[i] is not None and name != "FULL"]
    mean_errors[name] = statistics.mean(diffs) if diffs else 0

fig, ax = plt.subplots(figsize=(8, 5))
for name, color in zip(["SHORT", "MEDIUM", "SCRAPED"], ["#e74c3c", "#f39c12", "#8e44ad"]):
    ax.scatter(token_costs[name], mean_errors[name], color=color, s=150, zorder=5,
               label=name, edgecolors="white", linewidth=1.5)
    ax.annotate(name, (token_costs[name], mean_errors[name]),
                textcoords="offset points", xytext=(8, 4), fontsize=10)

ax.scatter(token_costs["FULL"], 0, color="#2ecc71", s=200, zorder=5,
           label="FULL (baseline)", marker="*", edgecolors="white")
ax.annotate("FULL\n(baseline)", (token_costs["FULL"], 0),
            textcoords="offset points", xytext=(8, 4), fontsize=10)

ax.set_xlabel("Estimated token cost (64-bundle XOR table)", fontsize=11)
ax.set_ylabel("Mean absolute deviation from FULL (%)", fontsize=11)
ax.set_title("Token Cost vs. Valuation Accuracy\n(Electronics scenario, Alex)",
             fontsize=12, fontweight="bold")
ax.legend(fontsize=9)
ax.grid(alpha=0.3)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
ax.set_ylim(bottom=-5)
plt.tight_layout()
p5 = f"{plot_dir}/5_cost_vs_accuracy.png"
plt.savefig(p5, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Plot 5 saved → {p5}")

print(f"\n{'='*70}")
print(f"  All done. Results in data/experiments/")
print(f"  Plots in data/experiments/plots/")
print(f"{'='*70}\n")
