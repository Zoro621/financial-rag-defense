# LaTeX Paper — Overleaf Upload Instructions

## Files to Upload

Upload **all** of the following to your Overleaf project root:

- `main.tex` — primary document (entry point)
- `sections_part2.tex` — continuation (Sections V–XII)
- `references.bib` — bibliography (40 entries, 35 cited)
- `figures/` — all figure files (upload the entire folder)

## Compilation

1. Open Overleaf → New Project → Upload Project (zip the `paper/` folder)
2. Set **main.tex** as the main document
3. Compiler: **pdfLaTeX** (or LaTeX + dvipdf)
4. Bibliography: Overleaf auto-detects BibTeX

## Figures

| File | Description |
|------|-------------|
| `architecture_diagram.png` | Extended framework architecture (Fig. 1 in paper) |
| `fig1_asr_bar.png` | ASR by defense configuration (Fig. 2 in paper) |
| `fig3_adaptive_curves.png` | Adaptive attack degradation curves (Fig. 3 in paper) |
| `fig6_nli_heatmap.png` | NLI threshold ablation heatmap (Fig. 4 in paper) |

## Notes

- Uses `IEEEtran` document class (standard on Overleaf)
- 40 references in bib file; 35 are cited in the paper
- The `.webp` architecture diagram is also provided for non-LaTeX use
