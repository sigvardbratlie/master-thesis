# Thesis

LaTeX source for master thesis: "Context Compression Techniques for Legal Document Analysis"

## Structure

```
thesis/
├── main.tex              # Root document
├── preamble.tex          # LaTeX preamble (packages, settings)
├── sample.bib            # BibTeX references
├── chapters/
│   ├── introduction.tex
│   ├── theory.tex
│   ├── method.tex
│   ├── results.tex
│   ├── discussion.tex
│   └── conclusion.tex
└── figures/               # Images
```

## Build

```bash
cd thesis
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

Or use the `.fls` / `.log` files from a previous build.

## Run live pdf preview
```bash
cd thesis
latexmk --pvc --pdf main.tex
```
