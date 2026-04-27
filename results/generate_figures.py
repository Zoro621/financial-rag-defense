"""
results/generate_figures.py
Generates all 6 figures from Section 14 of the implementation manual.

Run AFTER all experiment scripts have completed.
Usage:
    python results/generate_figures.py
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import TABLES_DIR, FIGURES_DIR

FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# Style
plt.rcParams.update({
    "figure.dpi":       150,
    "font.family":      "DejaVu Sans",
    "axes.spines.top":  False,
    "axes.spines.right": False,
    "axes.grid":        True,
    "grid.alpha":       0.3,
})
PALETTE = sns.color_palette("Set2", 8)


# =========================================================================== #
#  Figure 1 — ASR vs. Defense Config
# =========================================================================== #
def figure1_asr_bar():
    """Side-by-side grouped bar: baseline configs + Unit 1 + Unit 2 + combined."""
    baseline_path = TABLES_DIR / "baseline_results.csv"
    unit1_path    = TABLES_DIR / "unit1_results.csv"
    if not baseline_path.exists():
        print("Figure 1: baseline_results.csv missing — skipping")
        return

    df    = pd.read_csv(baseline_path)
    names = df["defense_config"].tolist()
    asrs  = df["asr_pct"].tolist()

    if unit1_path.exists():
        u1   = pd.read_csv(unit1_path)
        names += u1["defense_config"].tolist()
        asrs  += u1["asr_pct"].tolist()

    fig, ax = plt.subplots(figsize=(14, 6))
    x       = np.arange(len(names))
    colors  = [PALETTE[0]] * 8 + [PALETTE[2]] * (len(names) - 8)
    bars    = ax.bar(x, asrs, color=colors, alpha=0.85, edgecolor="white")

    ax.axhline(asrs[0], color="grey", linestyle="--", alpha=0.5, label="No-defense baseline")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Attack Success Rate (%)")
    ax.set_title("Figure 1 — ASR by Defense Configuration")

    patches = [
        mpatches.Patch(color=PALETTE[0], label="Baseline configs"),
        mpatches.Patch(color=PALETTE[2], label="Unit 1 (NLI guardrail)"),
    ]
    ax.legend(handles=patches, loc="upper right")
    plt.tight_layout()
    path = FIGURES_DIR / "fig1_asr_bar.png"
    plt.savefig(path); plt.close()
    print(f"  Saved: {path}")


# =========================================================================== #
#  Figure 2 — FPR comparison with stratification
# =========================================================================== #
def figure2_fpr_stratified():
    """Grouped bar: regex vs guard vs NLI, with A/B/C stratum breakdown."""
    unit1_path = TABLES_DIR / "unit1_results.csv"
    if not unit1_path.exists():
        print("Figure 2: unit1_results.csv missing — skipping")
        return

    df = pd.read_csv(unit1_path)
    configs = df["defense_config"].tolist()
    strata  = ["fpr_stratum_a", "fpr_stratum_b", "fpr_stratum_c"]
    labels  = ["Stratum A (Simple)", "Stratum B (Moderate)", "Stratum C (Complex)"]
    colors  = [PALETTE[0], PALETTE[1], PALETTE[2]]

    x      = np.arange(len(configs))
    width  = 0.25
    fig, ax = plt.subplots(figsize=(12, 6))

    for i, (col, label, color) in enumerate(zip(strata, labels, colors)):
        vals = df[col].tolist() if col in df.columns else [0] * len(configs)
        ax.bar(x + i * width, vals, width, label=label, color=color, alpha=0.85)

    ax.set_xticks(x + width)
    ax.set_xticklabels(configs, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("False Positive Rate (%)")
    ax.set_title("Figure 2 — Stratified FPR by Defense Config (Unit 1 / Gap 7)")
    ax.legend()
    plt.tight_layout()
    path = FIGURES_DIR / "fig2_fpr_stratified.png"
    plt.savefig(path); plt.close()
    print(f"  Saved: {path}")


# =========================================================================== #
#  Figure 3 — Adaptive ASR Degradation Curves
# =========================================================================== #
def figure3_adaptive_asr_curves():
    """Line plot: ASR vs iteration for 3 configs × 3 strategies."""
    unit3_path = TABLES_DIR / "unit3_results.json"
    if not unit3_path.exists():
        print("Figure 3: unit3_results.json missing — skipping")
        return

    with open(unit3_path) as f:
        data = json.load(f)

    fig, ax   = plt.subplots(figsize=(10, 6))
    styles    = ["-", "--", ":"]
    configs   = list(data.keys())
    strategies = ["paraphrase", "roleplay", "indirect"]
    config_colors = {c: PALETTE[i] for i, c in enumerate(configs)}

    for ci, config in enumerate(configs):
        for si, strategy in enumerate(strategies):
            try:
                curve = data[config][strategy]["asr_curve"]
                iters = list(range(1, len(curve) + 1))
                ax.plot(iters, curve, color=config_colors[config],
                        linestyle=styles[si], marker="o", markersize=4,
                        label=f"{config} / {strategy}")
            except KeyError:
                pass

    ax.set_xlabel("Iteration")
    ax.set_ylabel("Cumulative ASR (%)")
    ax.set_title("Figure 3 — Adaptive Attack ASR Degradation Curve")
    ax.legend(fontsize=7, ncol=2)
    plt.tight_layout()
    path = FIGURES_DIR / "fig3_adaptive_curves.png"
    plt.savefig(path); plt.close()
    print(f"  Saved: {path}")


# =========================================================================== #
#  Figure 4 — Defense Durability Bar Chart
# =========================================================================== #
def figure4_durability():
    """Bar chart: iteration at which ASR first exceeds 10% per config."""
    unit3_path = TABLES_DIR / "unit3_results.json"
    if not unit3_path.exists():
        print("Figure 4: unit3_results.json missing — skipping")
        return

    with open(unit3_path) as f:
        data = json.load(f)

    names   = []
    values  = []
    exceeds = []

    for config, strategies in data.items():
        for strategy, d in strategies.items():
            names.append(f"{config}\n{strategy}")
            iter10 = d.get("iteration_to_10pct")
            if iter10 is None:
                values.append(10)   # never exceeded — use max
                exceeds.append(True)
            else:
                values.append(iter10)
                exceeds.append(False)

    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(names))
    colors = [PALETTE[2] if e else PALETTE[0] for e in exceeds]
    ax.bar(x, values, color=colors, alpha=0.85, edgecolor="white")

    for xi, (v, e) in enumerate(zip(values, exceeds)):
        label = f">{v}" if e else str(v)
        ax.text(xi, v + 0.1, label, ha="center", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=7)
    ax.set_ylabel("Iteration at which ASR first exceeds 10%")
    ax.set_title("Figure 4 — Defense Durability")
    patches = [
        mpatches.Patch(color=PALETTE[2], label="Never exceeded 10%"),
        mpatches.Patch(color=PALETTE[0], label="Exceeded at iteration N"),
    ]
    ax.legend(handles=patches)
    plt.tight_layout()
    path = FIGURES_DIR / "fig4_durability.png"
    plt.savefig(path); plt.close()
    print(f"  Saved: {path}")


# =========================================================================== #
#  Figure 5 — Multi-Turn Context-Dependent ASR
# =========================================================================== #
def figure5_multiturn():
    """Grouped bars: single-turn ASR vs multi-turn turn-3 ASR."""
    unit4_path = TABLES_DIR / "unit4_results.json"
    if not unit4_path.exists():
        print("Figure 5: unit4_results.json missing — skipping")
        return

    with open(unit4_path) as f:
        data = json.load(f)

    configs  = list(data.keys())
    asr_hist = [data[c]["asr_with_history_pct"]    for c in configs]
    asr_no   = [data[c]["asr_no_history_pct"]      for c in configs]
    ctx_dep  = [data[c]["context_dependent_asr"]   for c in configs]

    x      = np.arange(len(configs))
    width  = 0.3
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x - width/2, asr_no,   width, label="Single-turn ASR",      color=PALETTE[0], alpha=0.85)
    ax.bar(x + width/2, asr_hist, width, label="Multi-turn (Turn 3) ASR", color=PALETTE[1], alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(configs, rotation=20, ha="right")
    ax.set_ylabel("ASR (%)")
    ax.set_title("Figure 5 — Multi-Turn vs. Single-Turn ASR (Unit 4)")
    ax.legend()
    plt.tight_layout()
    path = FIGURES_DIR / "fig5_multiturn.png"
    plt.savefig(path); plt.close()
    print(f"  Saved: {path}")


# =========================================================================== #
#  Figure 6 — NLI Threshold × FPR/ASR Heatmap
# =========================================================================== #
def figure6_nli_heatmap():
    """5×2 heatmap: threshold values × {FPR, ASR}."""
    ablation_path = TABLES_DIR / "ablation_summary.csv"
    if not ablation_path.exists():
        print("Figure 6: ablation_summary.csv missing — skipping")
        return

    df = pd.read_csv(ablation_path)
    abl2 = df[df["ablation_id"] == "2"].copy()
    if abl2.empty:
        print("Figure 6: Ablation 2 rows not found — skipping")
        return

    abl2["threshold"] = abl2["value"].astype(float)
    abl2 = abl2.sort_values("threshold")

    matrix = abl2[["fpr_pct", "asr_pct"]].values.astype(float)
    fig, ax = plt.subplots(figsize=(5, 6))
    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["FPR (%)", "ASR (%)"])
    ax.set_yticks(range(len(abl2)))
    ax.set_yticklabels(abl2["threshold"].tolist())
    ax.set_ylabel("NLI Threshold")
    ax.set_title("Figure 6 — NLI Threshold × FPR/ASR Heatmap")
    plt.colorbar(im, ax=ax, fraction=0.046)

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=9)

    plt.tight_layout()
    path = FIGURES_DIR / "fig6_nli_heatmap.png"
    plt.savefig(path); plt.close()
    print(f"  Saved: {path}")


# =========================================================================== #
#  Main
# =========================================================================== #
if __name__ == "__main__":
    print("=== Generating Figures ===\n")
    figure1_asr_bar()
    figure2_fpr_stratified()
    figure3_adaptive_asr_curves()
    figure4_durability()
    figure5_multiturn()
    figure6_nli_heatmap()
    print("\n✅ All figures generated.")
