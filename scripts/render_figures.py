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


def _save_fig(fig, png_path):
    """Save a figure as PNG (submission raster) and a PDF vector sibling."""
    fig.savefig(png_path, dpi=DPI, facecolor=C_WHITE)
    fig.savefig(Path(png_path).with_suffix(".pdf"), facecolor=C_WHITE)


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

    # Row positions — five evenly spaced stages (width 1.6, gap 0.4)
    main_y = 1.7
    box_h = 1.1
    bw = 1.6
    xs = [0.1, 2.1, 4.1, 6.1, 8.1]  # left edges; right edges 1.7/3.7/5.7/7.7/9.7

    _box(xs[0], main_y, bw, box_h, "#DBEAFE", "XPT Files",
         "TU/TR/RS/EX/DM\nAE/DS/TA/SUPPDM")
    _box(xs[1], main_y, bw, box_h, "#E0E7FF", "RDF Knowledge\nGraph",
         "CAVE namespace\nRDF triples")
    _box(xs[2], main_y, bw, box_h, "#BFDBFE", "L1: SHACL",
         "111 shapes\n(85+8+18)")
    _box(xs[3], main_y, bw, box_h, "#A7F3D0", "L3: CaveAgent",
         "RECIST Table 7\nLangGraph")
    _box(xs[4], main_y, bw, box_h, "#F3F4F6", "Audit Store",
         "SQLite WAL\nMerkle chain")

    # Arrows between main boxes (right edge -> next left edge)
    for xr, xl in zip([x + bw for x in xs[:4]], xs[1:]):
        _arrow(xr, main_y + box_h / 2, xl, main_y + box_h / 2)

    # Output boxes below L1 and L3 (generic; no track-specific metrics inside
    # a schematic architecture diagram)
    out_y = 0.3
    out_h = 0.8
    _box(xs[2], out_y, bw, out_h, "#EFF6FF", "L1 Violations")
    _box(xs[3], out_y, bw, out_h, "#ECFDF5", "L3 Traces")

    # Downward arrows
    _arrow(xs[2] + bw / 2, main_y, xs[2] + bw / 2, out_y + out_h)
    _arrow(xs[3] + bw / 2, main_y, xs[3] + bw / 2, out_y + out_h)

    # Legend (no in-image title — PLOS requires titles only in the caption)
    legend_items = [
        mpatches.Patch(facecolor="#BFDBFE", edgecolor="#374151", label="L1 (SHACL)"),
        mpatches.Patch(facecolor="#A7F3D0", edgecolor="#374151", label="L3 (Agent)"),
        mpatches.Patch(facecolor="#F3F4F6", edgecolor="#374151", label="Infrastructure"),
    ]
    ax.legend(handles=legend_items, loc="upper right", framealpha=0.9,
              fontsize=7, edgecolor="#D1D5DB")

    _save_fig(fig, outpath)
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
    labels_x = ["Pinnacle 21\nFDA (B1)", "CORE (B2)", "L1-only (B3)", "CAVE\nL1+L3"]
    ncol = len(labels_x)

    # Build matrix (0 = not detected, 1 = detected); columns match Table 3
    matrix = np.zeros((n, ncol))
    for i, r in enumerate(rows):
        matrix[i, 0] = int(r["P21_FDA_detected"])
        matrix[i, 1] = int(r["CORE_detected"])
        matrix[i, 2] = int(r["L1_only_detected"])
        matrix[i, 3] = int(r["CAVE_L1L3_detected"])

    fig, ax = plt.subplots(1, 1, figsize=(COL_WIDTH, 6.5))
    fig.patch.set_facecolor(C_WHITE)

    # Custom colormap: grey (0) → blue (1) — colorblind-safe
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap([C_GREY, C_BLUE])

    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=1)

    # Gridlines
    for i in range(n + 1):
        ax.axhline(i - 0.5, color=C_WHITE, linewidth=1.5)
    for j in range(ncol + 1):
        ax.axvline(j - 0.5, color=C_WHITE, linewidth=1.5)

    # Axis labels
    ax.set_xticks(range(ncol))
    ax.set_xticklabels(labels_x, fontsize=8, fontweight="bold")
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")

    ax.set_yticks(range(n))
    ax.set_yticklabels(labels_y, fontsize=7)

    # Cell annotations
    for i in range(n):
        for j in range(ncol):
            val = int(matrix[i, j])
            txt = "Y" if val == 1 else "-"
            color = C_WHITE if val == 1 else C_GREY_MID
            ax.text(j, i, txt, ha="center", va="center",
                    fontsize=9, fontweight="bold", color=color)

    # Highlight A19 row
    a19_idx = next(i for i, r in enumerate(rows) if r["archetype_id"] == "A19")
    ax.add_patch(plt.Rectangle((-0.5, a19_idx - 0.5), ncol, 1,
                               fill=False, edgecolor=C_GREEN, linewidth=2.5,
                               linestyle="--", zorder=5))
    ax.text(ncol + 0.15, a19_idx, "← L3 only", fontsize=7, color=C_GREEN_DARK,
            va="center", fontweight="bold")
    # No in-image title (PLOS requires titles only in the caption)

    # Legend
    legend_items = [
        mpatches.Patch(facecolor=C_BLUE, edgecolor="#374151", label="Detected"),
        mpatches.Patch(facecolor=C_GREY, edgecolor="#374151", label="Not detected"),
    ]
    ax.legend(handles=legend_items, loc="upper center",
              bbox_to_anchor=(0.5, -0.02), ncol=2,
              fontsize=8, edgecolor="#D1D5DB", framealpha=0.9)

    fig.tight_layout()
    _save_fig(fig, outpath)
    plt.close(fig)
    print(f"  Figure 2 saved: {outpath} ({outpath.stat().st_size:,} bytes)")


# ── Figure 3: Timing Comparison ─────────────────────────────────────────────

def render_figure3(outpath: Path, json_path: Path):
    """Horizontal bar chart: timing comparison by component."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    timing = data["timing"]
    # Source data
    components = ["Clean-data L1 baseline", "L1 (SHACL, 111 shapes)", "L3 (Agent)", "Full CAVE (L1+L3)"]
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
    ax1.text(times[3] + 1.5, 3.45, f"CAVE / Clean L1 = {ratio:.2f}×",
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

    # No in-image suptitle (PLOS requires titles only in the caption)
    fig.tight_layout()
    _save_fig(fig, outpath)
    plt.close(fig)
    print(f"  Figure 3 saved: {outpath} ({outpath.stat().st_size:,} bytes)")


# ── Supplementary Figure S1: Oxigraph scaling ───────────────────────────────

def render_figure_scaling(outpath: Path, json_path: Path):
    """Log-log scaling: SPARQL detection (sub-linear) vs end-to-end pipeline."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = sorted(data["scale_results"], key=lambda r: r["subjects"])
    subj = np.array([r["subjects"] for r in rows], dtype=float)
    detect_s = np.array([r["sparql_query_s"] for r in rows], dtype=float)
    e2e_s = np.array([r["subjects"] / r["end_to_end_throughput_subjects_per_s"]
                      for r in rows], dtype=float)

    sc = data["scaling"]
    exp_detect = sc["sparql_query_exponent_loglog"]
    exp_e2e = sc["end_to_end_exponent_loglog"]

    fig, ax = plt.subplots(1, 1, figsize=(COL_WIDTH * 0.72, 3.4))
    fig.patch.set_facecolor(C_WHITE)

    # Fitted power-law reference lines (anchored at the first point)
    xs = np.linspace(subj.min(), subj.max(), 100)
    ax.plot(xs, detect_s[0] * (xs / subj[0]) ** exp_detect,
            color=C_BLUE, lw=1.2, ls="--", alpha=0.8, zorder=1)
    ax.plot(xs, e2e_s[0] * (xs / subj[0]) ** exp_e2e,
            color=C_ORANGE, lw=1.2, ls="--", alpha=0.8, zorder=1)

    ax.plot(subj, detect_s, "o-", color=C_BLUE, lw=1.8, ms=7, zorder=3,
            label=f"SPARQL detection (slope {exp_detect:.2f}, sub-linear)")
    ax.plot(subj, e2e_s, "s-", color=C_ORANGE, lw=1.8, ms=6, zorder=3,
            label=f"End-to-end pipeline (slope {exp_e2e:.2f})")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Cohort size (subjects)", fontsize=9)
    ax.set_ylabel("Wall-clock time (s)", fontsize=9)
    ax.set_xticks(subj)
    ax.set_xticklabels([f"{int(s):,}" for s in subj])
    # Suppress default log-scale minor tick labels (2x10^3 etc.) that would
    # otherwise overlap the custom cohort-size labels.
    import matplotlib.ticker as mticker
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    ax.grid(True, which="both", alpha=0.3, zorder=0)
    ax.set_facecolor(C_BG)
    ax.legend(fontsize=7.5, loc="upper left", framealpha=0.9, edgecolor="#D1D5DB")

    fig.tight_layout()
    _save_fig(fig, outpath)
    plt.close(fig)
    print(f"  Figure S1 saved: {outpath} ({outpath.stat().st_size:,} bytes)")


# ── Supplementary Figure S2: real-data transfer (Item E) ─────────────────────

def render_figure_realdata(outpath: Path, synta_json: Path, ca012_json: Path):
    """3-state real-data transfer heatmap: detected / applicable-missed / N/A."""
    def states(path):
        s = json.load(open(path, encoding="utf-8"))["summary"]
        return set(s["detected_ids"]), set(s["missed_ids"])

    sd, sm = states(synta_json)
    cd, cm = states(ca012_json)
    aids = [f"A{i:02d}" for i in range(1, 21)]

    def code(a, det, mis):
        return 2 if a in det else (1 if a in mis else 0)  # 2=detected 1=missed 0=N/A

    matrix = np.array([[code(a, sd, sm), code(a, cd, cm)] for a in aids], dtype=float)

    from matplotlib.colors import ListedColormap
    cmap = ListedColormap([C_GREY, C_ORANGE, C_BLUE])

    fig, ax = plt.subplots(1, 1, figsize=(3.4, 6.2))
    fig.patch.set_facecolor(C_WHITE)
    ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=2)

    for i in range(len(aids) + 1):
        ax.axhline(i - 0.5, color=C_WHITE, lw=1.5)
    for j in range(3):
        ax.axvline(j - 0.5, color=C_WHITE, lw=1.5)

    ax.set_xticks(range(2))
    ax.set_xticklabels(["Synta\n4783-08", "CA012\n(mBC)"], fontsize=8, fontweight="bold")
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    ax.set_yticks(range(len(aids)))
    ax.set_yticklabels(aids, fontsize=7)

    sym = {2: "Y", 1: "x", 0: "-"}
    txtcol = {2: C_WHITE, 1: C_WHITE, 0: C_GREY_MID}
    for i in range(len(aids)):
        for j in range(2):
            v = int(matrix[i, j])
            ax.text(j, i, sym[v], ha="center", va="center",
                    fontsize=8, fontweight="bold", color=txtcol[v])

    legend_items = [
        mpatches.Patch(facecolor=C_BLUE, edgecolor="#374151", label="Detected"),
        mpatches.Patch(facecolor=C_ORANGE, edgecolor="#374151", label="Applicable, missed"),
        mpatches.Patch(facecolor=C_GREY, edgecolor="#374151", label="Not applicable"),
    ]
    ax.legend(handles=legend_items, loc="upper center", bbox_to_anchor=(0.5, -0.015),
              ncol=1, fontsize=7.5, edgecolor="#D1D5DB", framealpha=0.9)

    fig.tight_layout()
    _save_fig(fig, outpath)
    plt.close(fig)
    print(f"  Figure S2 saved: {outpath} ({outpath.stat().st_size:,} bytes)")


# ── PNG → publication TIFF (PLOS: RGB, LZW, 300 dpi) ─────────────────────────

def png_to_tiff(png_path: Path, tif_path: Path):
    """Convert a rendered PNG to a PLOS-compliant TIFF (RGB, LZW, 300 dpi)."""
    from PIL import Image
    im = Image.open(png_path).convert("RGB")
    im.save(tif_path, format="TIFF", compression="tiff_lzw", dpi=(DPI, DPI))


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Render CAVE-Onc manuscript figures.")
    parser.add_argument("--outdir", default="docs/figures",
                        help="PNG working directory (also holds detection_heatmap.csv)")
    parser.add_argument("--tifdir", default="docs/latex/plos_submission/figures",
                        help="Where submission TIFFs (Fig1-3) and Fig S1 are written")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    tifdir = Path(args.tifdir)
    tifdir.mkdir(parents=True, exist_ok=True)

    _setup_font()

    print("Rendering CAVE-Onc figures...")
    render_figure1(outdir / "figure1_architecture.png")
    render_figure2(outdir / "figure2_heatmap.png", outdir / "detection_heatmap.csv")
    render_figure3(outdir / "figure3_timing.png", Path("eval/p8_benchmark_results.json"))
    render_figure_scaling(tifdir / "FigS1_scaling.png", Path("eval/scale_benchmark_large.json"))
    render_figure_realdata(tifdir / "FigS2_realdata.png",
                           Path("eval/real_data_e2_synta.json"),
                           Path("eval/real_data_e2_ca012.json"))

    print("Converting main figures to publication TIFFs (+ vector PDF)...")
    import shutil
    for stem, name in [("figure1_architecture", "Fig1"),
                       ("figure2_heatmap", "Fig2"),
                       ("figure3_timing", "Fig3")]:
        png_to_tiff(outdir / f"{stem}.png", tifdir / f"{name}.tif")
        shutil.copy(outdir / f"{stem}.pdf", tifdir / f"{name}.pdf")  # vector sibling
        print(f"  {name}.tif + {name}.pdf")
    print("Done.")


if __name__ == "__main__":
    main()
