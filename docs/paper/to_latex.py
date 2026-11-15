"""Turn docs/paper/paper.md into a two-column LaTeX paper for Overleaf.

    python -I docs/paper/to_latex.py          # from the repo root

Writes docs/paper/latex/main.tex, copies the figures next to it, and zips the folder as
docs/paper/latex_overleaf.zip (Overleaf: New Project -> Upload Project -> pick the zip -> Recompile).
pdfLaTeX, standard packages only. paper.md stays the source: edit it, then run this again.

Figure 1 is a Mermaid chart in paper.md; Overleaf cannot draw Mermaid, so it is redrawn here in TikZ.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "paper.md"
OUT = HERE / "latex"
ZIP = HERE / "latex_overleaf.zip"

AUTHORS = [("Luka Georgieski", "georgieskiluka"), ("Ilija Chrchev", "ilijachrchev"), ("Zhivko Stoimchev", "zstoimchev")]
KEYWORDS = "NISAR, L-band SAR, flood mapping, Sentinel-1, independent validation, pre-registration, LightGBM, Valencia, DANA"
WIDE_FIGS = {"fig4_june18_map.png"}

UNI = {"\u2013": "--", "\u2014": "---", "\u2212": "\\textminus{}", "\u2192": "$\\rightarrow$", "\u2191": "$\\uparrow$",
       "\u2265": "$\\geq$", "\u2264": "$\\leq$", "\u2713": "\\checkmark{}", "\u2717": "$\\times$", "\u00b7": "\\textperiodcentered{}",
       "\u00d7": "$\\times$", "\u00b1": "$\\pm$", "\u2021": "\\ddag{}", "\u00a7": "\\S{}", "\u00b2": "\\textsuperscript{2}",
       "\u00b3": "\\textsuperscript{3}", "\u2026": "\\ldots{}", "\u00a0": "~"}

PREAMBLE = r"""\documentclass[10pt,twocolumn]{article}
\usepackage[a4paper,margin=1.8cm,columnsep=0.7cm]{geometry}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{textcomp}
\usepackage{amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{array}
\usepackage[font=small,labelformat=empty]{caption}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning}
\usepackage{url}
\usepackage[colorlinks=true,linkcolor=blue!50!black,urlcolor=blue!50!black,citecolor=blue!50!black]{hyperref}
\usepackage{microtype}
\setlist{nosep,leftmargin=1.2em}
\newcolumntype{L}{>{\raggedright\arraybackslash}X}
\setlength{\parskip}{0.35em}
\setlength{\parindent}{0pt}
\renewcommand{\arraystretch}{1.15}
"""

FIG1 = r"""\begin{figure*}[t]
\centering
\begin{tikzpicture}[font=\scriptsize,
  box/.style={draw,rounded corners=2pt,align=center,text width=2.9cm,minimum height=0.9cm,fill=#1},
  box/.default=white, arr/.style={-{Stealth[length=2mm]},thick}, dar/.style={-{Stealth[length=2mm]},thick,dashed}]
\node[box=blue!8] (N) at (0,3.0) {NISAR GCOV\\HH $\cdot$ HV $\cdot$ 20 m\\every 12-day pass};
\node[box=orange!10] (S) at (0,1.5) {Sentinel-1 DSWx-S1\\water per pass};
\node[box] (R) at (0,0.1) {Rain before and during\\Open-Meteo / ECMWF IFS};
\node[box] (T) at (0,-1.15) {Terrain: height above\\nearest channel $\cdot$ DEM};
\node[box] (L) at (0,-2.4) {Land cover $\cdot$ JRC water\\history $\cdot$ past Sentinel-1 water};
\node[box] (W) at (3.8,2.25) {Water per pass\\open water + flooded vegetation};
\node[box=green!10] (M) at (3.8,-0.6) {\textbf{Flood-extent model}\\LightGBM, where water goes};
\node[box=blue!8] (V) at (7.6,2.25) {\textbf{NISAR as judge}\\18 Jun sample, optical referee\\DANA vs EMSR935};
\node[box=green!10] (X) at (7.6,0.35) {Independent test\\vs EMSR935};
\node[box] (A) at (7.6,-2.4) {Rain-threshold alert\\100 mm in 3 days};
\node[box] (O) at (11.4,-1.0) {Alert shown as a map\\of likely flooded places};
\draw[arr] (N) -- (W); \draw[arr] (S) -- (W); \draw[arr] (W) -- (V);
\draw[arr] (S.east) to node[above,sloped,pos=0.55]{labels} (M.west);
\draw[dar] (N.south east) to[bend left=12] node[above,sloped,pos=0.62]{NISAR labels (one version)} (M.north);
\draw[arr] (R.east) -- (M.west); \draw[arr] (T.east) -- (M.west); \draw[arr] (L.east) -- (M.west);
\draw[arr] (M) to node[above,sloped]{held-out DANA} (X);
\draw[arr] (M.east) to node[below,sloped]{where} (O.west);
\draw[arr] (A.east) -- (O.south west);
\end{tikzpicture}
\caption{%s}
\end{figure*}
"""


# ---------------------------------------------------------------- inline text
def esc_plain(s: str) -> str:
    s = s.replace("\\", "\\textbackslash{}")
    for a, b in (("&", "\\&"), ("%", "\\%"), ("$", "\\$"), ("#", "\\#"), ("_", "\\_"), ("{", "\\{"), ("}", "\\}"),
                 ("~", "\\textasciitilde{}"), ("^", "\\textasciicircum{}")):
        s = s.replace(a, b)
    s = s.replace("\\textbackslash\\{\\}", "\\textbackslash{}")
    return s


def esc_code(s: str) -> str:
    s = esc_plain(s)
    for ch in ("/", ".", "\\_", "-"):
        s = s.replace(ch, ch + "\\allowbreak{}")
    return "\\texttt{" + unicode(s) + "}"


def unicode(s: str) -> str:
    for a, b in UNI.items():
        s = s.replace(a, b)
    return s


def inline(s: str, safe_urls: bool = True) -> str:
    s = re.sub(r"<!--.*?-->", "", s)
    keep: list[str] = []

    def stash(x: str) -> str:
        keep.append(x)
        return f"\x00{len(keep) - 1}\x00"
    s = re.sub(r"`([^`]+)`", lambda m: stash(esc_code(m.group(1))), s)

    def url(m):
        u = m.group(0).rstrip(".,;:")
        tail = m.group(0)[len(u):]
        if safe_urls and not re.search(r"[#%{}\\]", u):
            return stash("\\url{" + u + "}") + tail
        return stash(esc_code(u)) + tail
    s = re.sub(r"https?://[^\s)>\]|]+", url, s)
    s = esc_plain(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\\emph{\1}", s)
    s = re.sub(r'"([^"\n]*)"', r"``\1''", s)
    s = unicode(s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], s)
    return s


# ---------------------------------------------------------------- blocks
def table(rows: list[str], caption: str | None, wide: bool) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, align, body = cells[0], cells[1], cells[2:]
    spec = []
    for a in align:
        a = a.strip()
        spec.append("r" if a.endswith(":") and not a.startswith(":") else "c" if a.startswith(":") and a.endswith(":") else "L")
    if "L" not in spec:
        spec[0] = "L"
    out = []
    env = "table*" if (caption and wide) else None
    if env:
        out.append("\\begin{table*}[tbp]\n\\centering")
        out.append("\\caption{" + caption + "}")
    elif caption:
        out.append("\\begin{table}[tbp]\n\\centering")
        out.append("\\caption{" + caption + "}")
    else:
        out.append("\\begin{center}")
    width = "\\textwidth" if (env or not caption) else "\\columnwidth"
    out.append("\\footnotesize")
    out.append(f"\\begin{{tabularx}}{{{width}}}{{{''.join(spec)}}}\n\\toprule")
    out.append(" & ".join("\\textbf{" + inline(h, False) + "}" for h in head) + " \\\\\n\\midrule")
    for r in body:
        r = r + [""] * (len(head) - len(r))
        out.append("{}" + " & ".join(inline(c, False) for c in r[:len(head)]) + " \\\\")   # {}: a row may start with [
    out.append("\\bottomrule\n\\end{tabularx}")
    out.append("\\end{table*}" if env else ("\\end{table}" if caption else "\\end{center}"))
    return "\n".join(out) + "\n"


def figure(images: list[str], caption: str) -> str:
    wide = any(Path(i).name in WIDE_FIGS for i in images)
    env = "figure*" if wide else "figure"
    w = "\\textwidth" if wide else "\\columnwidth"
    body = "\n\\par\\medskip\n".join(f"\\includegraphics[width={w}]{{figures/{Path(i).name}}}" for i in images)
    return f"\\begin{{{env}}}[tbp]\n\\centering\n{body}\n\\caption{{{caption}}}\n\\end{{{env}}}\n"


def caption_text(line: str) -> str:
    c = line.strip()[1:-1] if line.strip().startswith("*") and line.strip().endswith("*") else line.strip()
    m = re.match(r"(Figure|Table) (\d+)\. (.*)", c, re.S)
    if m:
        return f"\\textbf{{{m.group(1)} {m.group(2)}:}} " + inline(m.group(3), False)
    m = re.match(r"(Table \d+ as a chart): (.*)", c, re.S)
    if m:
        return f"\\textbf{{{m.group(1)}:}} " + inline(m.group(2), False)
    return inline(c, False)


def convert(md: str) -> str:
    lines = md.splitlines()
    i = 0
    title = ""
    while i < len(lines) and not lines[i].startswith("# "):
        i += 1
    title = lines[i][2:].strip(); i += 1
    while i < len(lines) and lines[i].strip() != "---":       # authors, affiliation, draft note
        i += 1
    i += 1
    thanks = " \\and ".join(f"{n}\\thanks{{GitHub: @{h}}}" for n, h in AUTHORS)
    out = [PREAMBLE, f"\\title{{\\Large {inline(title)}}}",
           f"\\author{{{thanks}\\\\[0.3em]\\small NASA Space Apps Challenge 2026, Valencia, Spain $\\cdot$ challenge ``Dancing with the SARs''}}",
           "\\date{15 November 2026}", "\\begin{document}", "\\maketitle"]
    para: list[str] = []
    list_stack: list[str] = []
    pending_images: list[str] = []
    pending_table_caption: str | None = None
    in_appendix = False

    def flush_para():
        if para:
            out.append(inline(" ".join(para)) + "\n")
            para.clear()

    def close_lists(level=0):
        while len(list_stack) > level:
            out.append(f"\\end{{{list_stack.pop()}}}")

    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if s == "---":
            flush_para(); close_lists(); i += 1; continue
        if s.startswith("```"):
            flush_para(); close_lists()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            if not s.startswith("```mermaid"):
                out.append("\\begin{verbatim}\n" + "\n".join(lines[i + 1:j]) + "\n\\end{verbatim}")
            i = j + 1; continue
        if s.startswith("#"):
            flush_para(); close_lists()
            level = len(s) - len(s.lstrip("#"))
            text = s[level:].strip()
            if level == 2 and text.lower() == "abstract":
                out.append("\\section*{Abstract}")
                i += 1
                body = []
                while i < len(lines) and lines[i].strip() != "---":
                    if lines[i].strip():
                        body.append(lines[i].strip())
                    i += 1
                out.append(inline(" ".join(body)) + "\n")
                out.append(f"\\textbf{{Keywords:}} {KEYWORDS}\n")
                continue
            m = re.match(r"Appendix ([A-Z])\. (.*)", text)
            if m:
                if not in_appendix:
                    out.append("\\onecolumn\n\\normalsize\n\\appendix"); in_appendix = True
                out.append(f"\\section{{{inline(m.group(2))}}}")
            elif re.match(r"\d+\.\d+ ", text):
                out.append(f"\\subsection{{{inline(text.split(' ', 1)[1])}}}")
            elif re.match(r"\d+\. ", text):
                out.append(f"\\section{{{inline(text.split(' ', 1)[1])}}}")
            elif level >= 3:
                out.append(f"\\subsection*{{{inline(text)}}}")
            else:
                out.append(f"\\section*{{{inline(text)}}}")
            i += 1; continue
        m = re.match(r"!\[[^\]]*\]\(([^)]+)\)", s)
        if m:
            flush_para(); close_lists()
            pending_images.append(m.group(1)); i += 1; continue
        if s.startswith("*") and s.endswith("*") and (pending_images or re.match(r"\*(Figure|Table) \d+", s)):
            flush_para(); close_lists()
            if pending_images:
                out.append(figure(pending_images, caption_text(s))); pending_images = []
            elif s.startswith("*Figure"):
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j].strip().startswith("```mermaid"):
                    out.append(FIG1 % caption_text(s))
                else:
                    para.append(s)
            else:
                pending_table_caption = caption_text(s)
            i += 1; continue
        if s.startswith("|"):
            flush_para(); close_lists()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i]); i += 1
            out.append(table(rows, pending_table_caption, wide=not in_appendix))
            pending_table_caption = None
            continue
        if s.startswith(">"):
            flush_para(); close_lists()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip()); i += 1
            out.append("\\begin{quote}\\small\n" + inline(" ".join(x for x in q if x)) + "\n\\end{quote}")
            continue
        m = re.match(r"^( *)([-*]|\d+\.) (.*)", ln)
        if m:
            flush_para()
            depth = len(m.group(1)) // 2 + 1
            kind = "enumerate" if m.group(2)[0].isdigit() else "itemize"
            while len(list_stack) > depth:
                out.append(f"\\end{{{list_stack.pop()}}}")
            if len(list_stack) == depth and list_stack[-1] != kind:
                out.append(f"\\end{{{list_stack.pop()}}}")
            while len(list_stack) < depth:
                list_stack.append(kind); out.append(f"\\begin{{{kind}}}")
            text = m.group(3)
            j = i + 1
            while j < len(lines) and lines[j].strip() and not re.match(r"^ *([-*]|\d+\.) ", lines[j]) \
                    and not lines[j].strip().startswith(("|", "#", ">", "!", "```")):
                text += " " + lines[j].strip(); j += 1
            out.append("\\item{} " + inline(text))      # {} so a leading [..] is text, not an item label
            i = j; continue
        if not s:
            flush_para(); close_lists(); i += 1; continue
        para.append(s); i += 1
    flush_para(); close_lists()
    out.append("\\end{document}")
    tex = "\n".join(out)
    # references: no bullets, hanging indent
    tex = tex.replace("\\section*{References}", "\\section*{References}\\small")
    return tex


def main() -> int:
    tex = convert(SRC.read_text(encoding="utf-8"))
    (OUT / "figures").mkdir(parents=True, exist_ok=True)      # overwrite in place (OneDrive can lock folders)
    used = set(re.findall(r"figures/([\w.-]+\.png)", tex))
    for old in (OUT / "figures").glob("*.png"):
        if old.name not in used:
            old.unlink()
    for f in sorted(used):
        shutil.copyfile(HERE / "figures" / f, OUT / "figures" / f)
    (OUT / "main.tex").write_text(tex, encoding="utf-8")
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(OUT).as_posix())
    print("wrote", OUT / "main.tex", "and", ZIP, f"({ZIP.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
