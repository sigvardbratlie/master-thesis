# Thesis Writing Guide

## Rules

- **Language**: All text must be in English — formal academic prose, no contractions.
- **Style**: Third person. Precise and concise. Every claim backed by a citation or result.
- **Files**: Chapters live in `thesis/chapters/`. References in `thesis/sample.bib`. Figures in `thesis/figures/`. Root document is `thesis/main.tex`.
- **Before writing**: Read the relevant chapter `.tex` file to understand the current state and structure.
- **Citations**: Add new BibTeX entries to `sample.bib` before citing. Use `\cite{key}` in text.
- **LaTeX**: Use `\chapter`, `\section`, `\subsection` only. Labels use prefixes: `fig:`, `tab:`, `sec:`, `eq:`. Blank lines for paragraphs — no `\\` in prose.
- **Scope**: Only edit `.tex` files and `sample.bib`. Never touch build artifacts (`.aux`, `.log`, `.bbl`, etc.).
