"""
generate_architecture.py  — v3 (IEEE publication quality, fully consistent)
Produces a clean, professional architecture diagram of the
Extended Financial RAG Defense Framework.
Output: architecture_diagram.png / .webp  (300 DPI)
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

# ═══════════════════════════════════════════════════════════════════
#  Global style constants — single source of truth
# ═══════════════════════════════════════════════════════════════════
FONT       = "sans-serif"

# Colours
C_BASE     = "#CADCEB"        # steel blue   — baseline components
C_NEW      = "#FAD9B0"        # warm sand    — new contributions
C_EVAL     = "#C5E4C0"        # sage green   — evaluation extensions
C_IO       = "#E0E0E0"        # neutral grey — entry / exit nodes
C_AUDIT    = "#D5D5EC"        # light lilac  — audit log
C_DELIVER  = "#C2E0C2"        # light green  — final response
C_REJECT   = "#F2C4C4"        # muted pink   — rejection indicator
C_BG       = "#F7F7F7"        # stage background fill
C_BDR      = "#444444"        # border colour for all boxes
C_BG_BDR   = "#B0B0B0"        # border colour for stage backgrounds
C_ARROW    = "#333333"        # flow arrow colour
C_RED      = "#B03030"        # rejection arrow / text colour
C_TXT      = "#1A1A1A"        # title text
C_SUB      = "#3A3A3A"        # subtitle text

# Typography — unified sizes
FS_TITLE   = 13.5             # diagram title
FS_BOX     = 9.5              # component box title
FS_SUB     = 8.0              # component box subtitle
FS_ENTRY   = 10.5             # entry node (User Query) title
FS_STAGE   = 8.5              # stage background label
FS_REJECT  = 8.5              # reject node + arrow label text

# Dimensions
LW_BOX     = 1.0              # component box border width
LW_BG      = 0.7              # stage background border width
LW_ARROW   = 1.3              # all flow arrows
LW_REJECT  = 1.1              # rejection arrows (dashed)
BOX_W      = 4.0              # standard two-column box width
BOX_H      = 1.15             # standard two-column box height
GAP_V      = 0.55             # vertical gap between stage groups
CX         = 5.5              # canvas centre-x

# ═══════════════════════════════════════════════════════════════════
#  Drawing helpers
# ═══════════════════════════════════════════════════════════════════

def box(ax, cx, cy, w, h, title, subtitle="", color=C_BASE,
        title_fs=FS_BOX, sub_fs=FS_SUB):
    """Rounded box centred at (cx, cy)."""
    x0 = cx - w / 2
    y0 = cy - h / 2
    p = FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0.10",
                       facecolor=color, edgecolor=C_BDR, linewidth=LW_BOX,
                       zorder=2)
    ax.add_patch(p)
    if subtitle:
        ax.text(cx, cy + 0.16, title, ha="center", va="center",
                fontsize=title_fs, fontweight="bold", color=C_TXT,
                fontfamily=FONT, zorder=3)
        ax.text(cx, cy - 0.20, subtitle, ha="center", va="center",
                fontsize=sub_fs, color=C_SUB, fontfamily=FONT,
                zorder=3, linespacing=1.30)
    else:
        ax.text(cx, cy, title, ha="center", va="center",
                fontsize=title_fs, fontweight="bold", color=C_TXT,
                fontfamily=FONT, zorder=3)

def stage_bg(ax, x0, y0, w, h, label):
    """Translucent background rectangle for a stage group."""
    p = FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0.06",
                       facecolor=C_BG, edgecolor=C_BG_BDR, linewidth=LW_BG,
                       linestyle="-", zorder=0, alpha=0.85)
    ax.add_patch(p)
    ax.text(x0 + 0.20, y0 + h - 0.18, label, fontsize=FS_STAGE,
            fontweight="bold", color=C_BDR, va="top", fontfamily=FONT,
            fontstyle="italic", zorder=1)

def arrow_down(ax, x, y_top, y_bot):
    ax.annotate("", xy=(x, y_bot), xytext=(x, y_top),
                arrowprops=dict(arrowstyle="-|>", color=C_ARROW, lw=LW_ARROW))

def arrow_right(ax, x0, y, x1):
    ax.annotate("", xy=(x1, y), xytext=(x0, y),
                arrowprops=dict(arrowstyle="-|>", color=C_ARROW, lw=LW_ARROW))

def arrow_reject(ax, x0, y0, x1, y1, label="Reject"):
    """Dashed red arrow to a rejection node."""
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", color=C_RED, lw=LW_REJECT,
                                linestyle="--"))
    mx = (x0 + x1) / 2
    my = (y0 + y1) / 2
    ax.text(mx, my + 0.14, label, fontsize=FS_REJECT, color=C_RED,
            fontweight="bold", ha="center", va="bottom", fontfamily=FONT,
            zorder=4)

def reject_node(ax, cx, cy, label="Rejected"):
    """Small rejection indicator box."""
    w, h = 1.55, 0.50
    x0 = cx - w / 2
    y0 = cy - h / 2
    p = FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0.06",
                       facecolor=C_REJECT, edgecolor=C_RED, linewidth=LW_BOX,
                       zorder=2)
    ax.add_patch(p)
    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=FS_REJECT, fontweight="bold", color=C_RED,
            fontfamily=FONT, zorder=3)


# ═══════════════════════════════════════════════════════════════════
#  Main diagram
# ═══════════════════════════════════════════════════════════════════
def main():
    fig, ax = plt.subplots(figsize=(12.0, 15.0), dpi=300)
    ax.set_xlim(0, 13)
    ax.set_ylim(-1.0, 17.5)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")

    # ── Title ───────────────────────────────────────────────────
    ax.text(CX, 17.15, "Extended Defense Framework for Financial RAG Systems",
            ha="center", va="center", fontsize=FS_TITLE, fontweight="bold",
            color=C_TXT, fontfamily=FONT)

    # ── Rejection column (right side, reused) ───────────────────
    RX = 11.8  # rejection node x — outside stage backgrounds

    # ═════════════════════════════════════════════════════════════
    #  USER QUERY
    # ═════════════════════════════════════════════════════════════
    y_q = 16.2
    box(ax, CX, y_q, 4.8, 0.75, "User Query",
        "Single-turn or multi-turn", color=C_IO, title_fs=FS_ENTRY)

    # ═════════════════════════════════════════════════════════════
    #  STAGE 1 — INPUT FILTERING
    # ═════════════════════════════════════════════════════════════
    s1_top = 15.15
    s1_cy  = s1_top - 0.65
    s1_bot = s1_cy - BOX_H / 2
    stage_bg(ax, 0.4, s1_bot - 0.20, 10.2, 1.80, "Stage 1: Input Filtering")

    box(ax, 3.2, s1_cy, BOX_W, BOX_H, "Regex Input Filter",
        "10 prohibited-pattern categories", color=C_BASE)
    box(ax, 7.5, s1_cy, BOX_W, BOX_H, "Prompt Guard 2",
        "86M-parameter BERT classifier", color=C_BASE)

    arrow_down(ax, CX, y_q - 0.375, s1_top)
    reject_node(ax, RX, s1_cy, "Rejected")
    arrow_reject(ax, 7.5 + BOX_W/2, s1_cy, RX - 0.78, s1_cy, "Blocked")

    # ═════════════════════════════════════════════════════════════
    #  STAGE 2 — RETRIEVAL + INTEGRITY
    # ═════════════════════════════════════════════════════════════
    s2_top = s1_bot - 0.20 - GAP_V
    s2_cy  = s2_top - 0.65
    s2_bot = s2_cy - BOX_H / 2
    stage_bg(ax, 0.4, s2_bot - 0.20, 10.2, 1.80, "Stage 2: Retrieval and Integrity Verification")

    box(ax, 3.2, s2_cy, BOX_W, BOX_H, "FAISS Vector Retrieval",
        "Top-5 chunks, MiniLM-L6-v2", color=C_BASE)
    box(ax, 7.5, s2_cy, BOX_W, BOX_H, "Retrieval Integrity\nChecker",
        "Embedding centroid\nanomaly detection", color=C_NEW)

    arrow_down(ax, CX, s1_bot - 0.20, s2_top)
    arrow_right(ax, 3.2 + BOX_W/2, s2_cy, 7.5 - BOX_W/2)
    reject_node(ax, RX, s2_cy, "Flagged")
    arrow_reject(ax, 7.5 + BOX_W/2, s2_cy, RX - 0.78, s2_cy, "Anomaly")

    # ═════════════════════════════════════════════════════════════
    #  STAGE 3 — GENERATION
    # ═════════════════════════════════════════════════════════════
    s3_top = s2_bot - 0.20 - GAP_V
    s3_cy  = s3_top - 0.65
    s3_bot = s3_cy - BOX_H / 2
    stage_bg(ax, 0.4, s3_bot - 0.20, 10.2, 1.80, "Stage 3: Response Generation")

    box(ax, 3.2, s3_cy, BOX_W, BOX_H, "System Prompt",
        "Goal Prioritization with\ninternal reasoning chain", color=C_BASE)
    box(ax, 7.5, s3_cy, BOX_W, BOX_H, "LLM Generation",
        "Retrieved context integrated\ninto response generation", color=C_BASE)

    arrow_down(ax, CX, s2_bot - 0.20, s3_top)
    arrow_right(ax, 3.2 + BOX_W/2, s3_cy, 7.5 - BOX_W/2)

    # ═════════════════════════════════════════════════════════════
    #  STAGE 4 — OUTPUT VERIFICATION  (3 layers, vertically stacked)
    # ═════════════════════════════════════════════════════════════
    # Three layers stacked vertically, centred
    layer_h = 0.95
    layer_gap = 0.40
    s4_inner_h = 3 * layer_h + 2 * layer_gap
    s4_pad_top = 0.45
    s4_pad_bot = 0.20
    s4_total   = s4_inner_h + s4_pad_top + s4_pad_bot
    s4_top_y   = s3_bot - 0.20 - GAP_V
    s4_bot_y   = s4_top_y - s4_total

    stage_bg(ax, 0.4, s4_bot_y, 10.2, s4_total,
             "Stage 4: Multi-Layer Output Verification")

    # Layer A
    la_cy = s4_top_y - s4_pad_top - layer_h / 2
    box(ax, CX, la_cy, 6.0, layer_h,
        "Layer A: Token-Level Output Filtering",
        "Regex pattern matching and Prompt Guard classification",
        color=C_BASE)

    # Layer B
    lb_cy = la_cy - layer_h / 2 - layer_gap - layer_h / 2
    box(ax, CX, lb_cy, 6.0, layer_h,
        "Layer B: NLI Semantic Guardrail",
        "DeBERTa-v3 cross-encoder entailment scoring\n"
        "for financial risk term context classification",
        color=C_NEW)

    # Layer C
    lc_cy = lb_cy - layer_h / 2 - layer_gap - layer_h / 2
    box(ax, CX, lc_cy, 6.0, layer_h,
        "Layer C: Response Grounding Verifier",
        "Cosine similarity between response and\n"
        "retrieved chunks; calibrated threshold",
        color=C_NEW)

    # Arrows between layers
    arrow_down(ax, CX, s3_bot - 0.20, s4_top_y)
    arrow_down(ax, CX, la_cy - layer_h / 2, lb_cy + layer_h / 2)
    arrow_down(ax, CX, lb_cy - layer_h / 2, lc_cy + layer_h / 2)

    # Reject arrows from each layer
    reject_node(ax, RX, la_cy, "Rejected")
    arrow_reject(ax, CX + 3.0, la_cy, RX - 0.78, la_cy, "Blocked")

    reject_node(ax, RX, lb_cy, "Rejected")
    arrow_reject(ax, CX + 3.0, lb_cy, RX - 0.78, lb_cy, "Blocked")

    reject_node(ax, RX, lc_cy, "Rejected")
    arrow_reject(ax, CX + 3.0, lc_cy, RX - 0.78, lc_cy, "Blocked")

    # ═════════════════════════════════════════════════════════════
    #  STAGE 5 — AUDIT + DELIVERY
    # ═════════════════════════════════════════════════════════════
    s5_top = s4_bot_y - GAP_V
    s5_cy  = s5_top - 0.65
    s5_bot = s5_cy - BOX_H / 2
    stage_bg(ax, 0.4, s5_bot - 0.20, 10.2, 1.80,
             "Stage 5: Stratified Audit and Delivery")

    box(ax, 3.2, s5_cy, BOX_W, BOX_H, "Audit Log",
        "Query stratum, stage outcomes,\nintegrity and grounding scores",
        color=C_AUDIT)
    box(ax, 7.5, s5_cy, BOX_W, BOX_H, "Final Response",
        "Delivered to user", color=C_DELIVER)

    arrow_down(ax, CX, lc_cy - layer_h / 2, s5_top)

    # ═════════════════════════════════════════════════════════════
    #  EVALUATION EXTENSIONS (bottom bar)
    # ═════════════════════════════════════════════════════════════
    ev_top = s5_bot - 0.20 - GAP_V
    ev_cy  = ev_top - 0.55
    ev_bot = ev_cy - 0.55
    stage_bg(ax, 0.4, ev_bot - 0.10, 10.2, 1.55,
             "Evaluation Protocol Extensions")

    ew = 2.9
    eh = 0.90
    box(ax, 2.1, ev_cy, ew, eh, "Adaptive Attack\nEvaluation",
        "PAIR-style iterative loop\n3 strategies, 10 iterations", color=C_EVAL)
    box(ax, 5.5, ev_cy, ew, eh, "Multi-Turn Attack\nEvaluation",
        "3-turn escalation\nsequences (n = 50)", color=C_EVAL)
    box(ax, 8.9, ev_cy, ew, eh, "Defense Efficiency\nMetric Extension",
        "Regulatory compliance\nweighting profile", color=C_EVAL)

    arrow_down(ax, CX, s5_bot - 0.20, ev_top)

    # ═════════════════════════════════════════════════════════════
    #  LEGEND  (bottom-left, outside flow)
    # ═════════════════════════════════════════════════════════════
    legend_patches = [
        mpatches.Patch(fc=C_BASE, ec=C_BDR, lw=0.6,
                       label="Baseline (Song & Lee, 2026)"),
        mpatches.Patch(fc=C_NEW, ec=C_BDR, lw=0.6,
                       label="New defense (this work)"),
        mpatches.Patch(fc=C_EVAL, ec=C_BDR, lw=0.6,
                       label="Evaluation extension (this work)"),
    ]
    ax.legend(handles=legend_patches, loc="lower left", fontsize=8,
              frameon=True, framealpha=0.95, edgecolor="#AAAAAA",
              bbox_to_anchor=(0.02, 0.0), bbox_transform=ax.transAxes,
              handlelength=1.2, handletextpad=0.5)

    # ── Save ────────────────────────────────────────────────────
    plt.tight_layout(pad=0.3)
    for fmt in ("png", "webp"):
        out = f"architecture_diagram.{fmt}"
        fig.savefig(out, format=fmt, dpi=300, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        print(f"Saved: {out}")
    plt.close()


if __name__ == "__main__":
    main()
