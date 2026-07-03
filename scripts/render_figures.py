"""
Render publication-quality figures for CAVE-Onc manuscript.

Produces three figures:
  - Figure 1: Architecture diagram (two-layer pipeline)
  - Figure 2: Detection heatmap (20 archetypes × 3 configurations)
  - Figure 3: Timing comparison bar chart

All output at 300 DPI, column width (~180 mm ≈ 7.09 in).

Usage:
    python -m scripts.render_figures [--outdir docs/figures]
"""

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np


# ── Shared style ─────────────────────────────────────────────────────────────

DPI = 300
COL_WIDTH = 7.09  # inches (≈180 mm)

# Color palette
C_BLUE      = "#3B82F6"
C_BLUE_DARK = "#1E40AF"
C_GREEN     = "#10B981"
C_GREEN_DARK= "#047857"
C_PURPLE    = "#8B5CF6"
C_ORANGE    = "#F59E0B"
C_GREY      = "#E5E7EB"
C_GREY_MID  = "#9CA3AF"
C_RED       = "#DC2626"
C_RED_DARK  = "#991B1B"
C_BG        = "#FAFAFA"
C_TEXT      = "#1F2937"
C_WHITE     = "#FFFFFF"


def _setup_font():
    """Configure matplotlib for clean, publication-ready fonts."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 9,
        "axes.labelsize": 10,
        "axes.titlesize": 11,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
    })


# ── Figure 1: Architecture Diagram ──────────────────────────────────────────

def render_figure1(outpath: Path):
    """Architecture diagram: left-to-right pipeline flow."""
    fig, ax = plt.subplots(1, 1, figsize=(COL_WIDTH, 3.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")
    fig.patch.set_facecolor(C_WHITE)

    def _box(x, y, w, h, color, label, sublabel=None, alpha=0.9):
        """Draw a rounded box with label."""
        box = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.08",
            facecolor=color, edgecolor="#374151",
            linewidth=1.2, alpha=alpha, zorder=2
        )
        ax.add_patch(box)
        cx, cy = x + w / 2, y + h / 2
        if sublabel:
            ax.text(cx, cy + 0.18, label, ha="center", va="center",
                    fontsize=8, fontweight="bold", color=C_TEXT, zorder=3)
            ax.text(cx, cy - 0.18, sublabel, ha="center", va="center",
                    fontsize=6.5, color="#4B5563", zorder=3)
        else:
            ax.text(cx, cy, label, ha="center", va="center",
                    fontsize=8, fontweight="bold", color=C_TEXT, zorder=3)

    def _arrow(x1, y1, x2, y2):
        """Draw a connecting arrow."""
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="-|>", color="#6B7280",
                lw=1.5, connectionstyle="arc3,rad=0"
            ),
            zorder=1
        )

    # Row positions
    main_y = 1.7
    box_h = 1.1

    # Input
    _box(0.1, main_y, 1.3, box_h, "#DBEAFE", "XPT Files",
         "TU/TR/RS/EX/DM\nAE/DS/TA/SUPPDM")

    # RDF KG
    _box(1.9, main_y, 1.5, box_h, "#E0E7FF", "RDF Knowledge\nGraph",
         "CAVE namespace\n1.5M+ triples")

    # L1
    _box(3.9, main_y, 1.5, box_h, "#BFDBFE", "L1: SHACL",
         "111 shapes\n(85+8+18)")

    # L3
    _box(5.9, main_y, 1.5, box_h, "#A7F3D0", "L3: CaveAgent",
         "RECIST Table 7\nLangGraph")

    # Audit
    _box(7.9, main_y, 1.5, box_h, "#F3F4F6", "Audit Store",
         "SQLite WAL\nMerkle chain")

    # Arrows between main boxes
    _arrow(1.4, main_y + box_h / 2, 1.9, main_y + box_h / 2)
    _arrow(3.4, main_y + box_h / 2, 3.9, main_y + box_h / 2)
    _arrow(5.4, main_y + box_h / 2, 5.9, main_y + box_h / 2)
    _arrow(7.4, main_y + box_h / 2, 7.9, main_y + box_h / 2)

    # Output boxes below
    out_y = 0.3
    out_h = 0.8

    _box(3.9, out_y, 1.5, out_h, "#EFF6FF", "L1 Violations",
         "5,803 flags")
    _box(5.9, out_y, 1.5, out_h, "#ECFDF5", "L3 Traces",
         "A19 detected")

    # Downward arrows
    _arrow(4.65, main_y, 4.65, out_y + out_h)
    _arrow(6.65, main_y, 6.65, out_y + out_h)

    # Title bar
    ax.text(5.0, 3.6, "CAVE-Onc Two-Layer Validation Architecture",
            ha="center", va="center", fontsize=11, fontweight="bold",
            color=C_TEXT)

    # Legend
    legend_items = [
        mpatches.Patch(facecolor="#BFDBFE", edgecolor="#374151", label="L1 (SHACL)"),
        mpatches.Patch(facecolor="#A7F3D0", edgecolor="#374151", label="L3 (Agent)"),
        mpatches.Patch(facecolor="#F3F4F6", edgecolor="#374151", label="Infrastructure"),
    ]
    ax.legend(handles=legend_items, loc="upper right", framealpha=0.9,
              fontsize=7, edgecolor="#D1D5DB")

    fig.savefig(outpath, dpi=DPI, facecolor=C_WHITE)
    plt.close(fig)
    print(f"  Figure 1 saved: {outpath} ({outpath.stat().st_size:,} bytes)")


# ── Figure 2: Detection Heatmap ─────────────────────────────────────────────

def render_figure2(outpath: Path, csv_path: Path):
    """Detection heatmap: 20 archetypes × 3 configurations."""
    # Load data
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    n = len(rows)
    labels_y = [f"{r['archetype_id']}: {r['name']}" for r in rows]
    labels_x = ["CORE (B2)", "L1-only (B3)", "CAVE L1+L3"]

    # Build matrix (0 = not detected, 1 = detected)
    matrix = np.zeros((n, 3))
    for i, r in enumerate(rows):
        matrix[i, 0] = int(r["CORE_detected"])
        matrix[i, 1] = int(r["L1_only_detected"])
        matrix[i, 2] = int(r["CAVE_L1L3_detected"])

    fig, ax = plt.subplots(1, 1, figsize=(COL_WIDTH, 6.5))
    fig.patch.set_facecolor(C_WHITE)

    # Custom colormap: grey (0) → blue (1) — colorblind-safe
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap([C_GREY, C_BLUE])

    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=1)

    # Gridlines
    for i in range(n + 1):
        ax.axhline(i - 0.5, color=C_WHITE, linewidth=1.5)
    for j in range(4):
        ax.axvline(j - 0.5, color=C_WHITE, linewidth=1.5)

    # Axis labels
    ax.set_xticks(range(3))
    ax.set_xticklabels(labels_x, fontsize=9, fontweight="bold")
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")

    ax.set_yticks(range(n))
    ax.set_yticklabels(labels_y, fontsize=7)

    # Cell annotations
    for i in range(n):
        for j in range(3):
            val = int(matrix[i, j])
            txt = "Y" if val == 1 else "-"
            color = C_WHITE if val == 1 else C_GREY_MID
            ax.text(j, i, txt, ha="center", va="center",
                    fontsize=9, fontweight="bold", color=color)

    # Highlight A19 row
    a19_idx = next(i for i, r in enumerate(rows) if r["archetype_id"] == "A19")
    ax.add_patch(plt.Rectangle((-0.5, a19_idx - 0.5), 3, 1,
                               fill=False, edgecolor=C_GREEN, linewidth=2.5,
                               linestyle="--", zorder=5))
    ax.text(3.15, a19_idx, "← L3 only", fontsize=7, color=C_GREEN_DARK,
            va="center", fontweight="bold")

    ax.set_title("Contradiction Archetype Detection Across Configurations",
                 fontsize=11, fontweight="bold", pad=20, color=C_TEXT)

    # Legend
    legend_items = [
        mpatches.Patch(facecolor=C_BLUE, edgecolor="#374151", label="Detected"),
        mpatches.Patch(facecolor=C_GREY, edgecolor="#374151", label="Not detected"),
    ]
    ax.legend(handles=legend_items, loc="lower right",
              fontsize=8, edgecolor="#D1D5DB", framealpha=0.9)

    fig.tight_layout()
    fig.savefig(outpath, dpi=DPI, facecolor=C_WHITE)
    plt.close(fig)
    print(f"  Figure 2 saved: {outpath} ({outpath.stat().st_size:,} bytes)")


# ── Figure 3: Timing Comparison ─────────────────────────────────────────────

def render_figure3(outpath: Path, json_path: Path):
    """Horizontal bar chart: timing comparison by component."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    timing = data["timing"]
    # Source data
    components = ["CORE baseline", "L1 (SHACL, 111 shapes)", "L3 (Agent)", "Full CAVE (L1+L3)"]
    times = [
        timing.get("clean_baseline_l1_s", 103.664),
        timing["mean_per_archetype_l1_s"],
        timing["mean_per_archetype_l3_s"],
        timing["mean_full_pipeline_s"],
    ]
    colors = [C_ORANGE, C_BLUE, C_GREEN, C_PURPLE]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(COL_WIDTH, 2.8),
                                    gridspec_kw={"width_ratios": [4, 1]})
    fig.patch.set_facecolor(C_WHITE)

    # Panel (a): Full scale — ensure L3 bar is visually visible
    y_pos = np.arange(len(components))
    # Use a minimum display width for very short bars so they remain visible
    display_times = list(times)
    min_bar_width = max(times) * 0.015  # ~1.5% of max for visibility
    for i, t in enumerate(times):
        if t < min_bar_width:
            display_times[i] = min_bar_width
    bars1 = ax1.barh(y_pos, display_times, color=colors, edgecolor="#374151",
                      linewidth=0.8, height=0.6, zorder=2)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(components, fontsize=8)
    ax1.set_xlabel("Time (seconds)", fontsize=9)
    ax1.set_title("(a) Full scale", fontsize=9, fontweight="bold")
    ax1.invert_yaxis()
    ax1.grid(axis="x", alpha=0.3, zorder=0)
    ax1.set_facecolor(C_BG)

    # Annotations
    for i, (t, bar) in enumerate(zip(times, bars1)):
        if t > 1:
            ax1.text(t + 1.5, i, f"{t:.1f}s", va="center", fontsize=7, color=C_TEXT)
        else:
            # Use arrow annotation to connect label to the tiny bar
            ax1.annotate(
                f"{t*1000:.0f}ms", xy=(display_times[i], i),
                xytext=(max(times) * 0.15, i),
                fontsize=7, color=C_GREEN_DARK, fontweight="bold",
                va="center",
                arrowprops=dict(arrowstyle="->", color=C_GREEN_DARK, lw=1.0),
            )

    # CAVE/CORE ratio annotation
    ratio = timing["cave_to_baseline_ratio"]
    ax1.text(times[3] + 1.5, 3.45, f"CAVE/CORE = {ratio:.2f}×",
             fontsize=7, color=C_PURPLE, fontweight="bold", va="top")

    # Panel (b): Zoomed L3
    ax2.barh([0], [times[2]], color=[C_GREEN], edgecolor="#374151",
              linewidth=0.8, height=0.5, zorder=2)
    ax2.set_yticks([0])
    ax2.set_yticklabels(["L3 Agent"], fontsize=8)
    ax2.set_xlabel("Time (seconds)", fontsize=9)
    ax2.set_title("(b) L3 detail", fontsize=9, fontweight="bold")
    ax2.set_xlim(0, 0.05)
    ax2.grid(axis="x", alpha=0.3, zorder=0)
    ax2.set_facecolor(C_BG)
    ax2.text(times[2] + 0.002, 0, f"{times[2]*1000:.0f}ms",
             va="center", fontsize=8, color=C_GREEN_DARK, fontweight="bold")

    fig.suptitle("Mean Validation Time per Archetype by Component",
                 fontsize=11, fontweight="bold", color=C_TEXT, y=1.02)
    fig.tight_layout()
    fig.savefig(outpath, dpi=DPI, facecolor=C_WHITE)
    plt.close(fig)
    print(f"  Figure 3 saved: {outpath} ({outpath.stat().st_size:,} bytes)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Render CAVE-Onc manuscript figures.")
    parser.add_argument("--outdir", default="docs/figures", help="Output directory")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    _setup_font()

    print("Rendering CAVE-Onc figures...")
    render_figure1(outdir / "figure1_architecture.png")
    render_figure2(outdir / "figure2_heatmap.png", outdir / "detection_heatmap.csv")
    render_figure3(outdir / "figure3_timing.png", Path("eval/p8_benchmark_results.json"))
    print("Done. All figures saved to", outdir)


if __name__ == "__main__":
    main()
