"""Render a markdown report to a self-contained local HTML file, and optionally PDF.

PDF uses headless Chrome if it is installed. Nothing is uploaded.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from pathlib import Path

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
    "msedge",
]

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo","Noto Sans KR",-apple-system,
       BlinkMacSystemFont,"Segoe UI",sans-serif;
       max-width: 52rem; margin: 0 auto; padding: 2.2rem 1.4rem;
       line-height: 1.62; font-size: 15px; color: #1a1a1a; background: #fff; }
h1 { font-size: 1.7rem; letter-spacing: -.5px; margin: 0 0 .3em; }
h2 { font-size: 1.15rem; margin: 2em 0 .5em; padding: .35em .6em;
     background: #1a1a1a; color: #fff; border-radius: 4px; }
h3 { font-size: 1rem; margin: 1.5em 0 .4em; border-bottom: 2px solid #1a1a1a;
     padding-bottom: .2em; }
table { width: 100%; border-collapse: collapse; margin: .8em 0; font-size: .9rem;
        display: block; overflow-x: auto; }
th, td { border: 1px solid #ccc; padding: .4em .6em; text-align: left;
         vertical-align: top; }
th { background: #f0f0f0; }
code { background: #f2f2f2; padding: .1em .35em; border-radius: 3px;
       font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em; }
pre { background: #f6f6f6; padding: .8em; border-radius: 5px; overflow-x: auto; }
blockquote { margin: .8em 0; padding: .5em .9em; border-left: 4px solid #8a7a2a;
             background: #f8f8f0; }
hr { border: 0; border-top: 1px solid #ddd; margin: 2em 0; }
@media (prefers-color-scheme: dark) {
  body { background: #16181a; color: #e6e6e6; }
  h2 { background: #e6e6e6; color: #16181a; }
  h3 { border-color: #e6e6e6; }
  th { background: #24282c; } th, td { border-color: #3a3f45; }
  code, pre { background: #24282c; }
  blockquote { background: #22241f; border-color: #b8a63f; }
  hr { border-color: #3a3f45; }
}
@media print { body { max-width: none; padding: 0; } h2 { -webkit-print-color-adjust: exact; } }
"""


def _md_to_html(md: str) -> str:
    """Minimal markdown -> HTML. Enough for the report shapes we generate."""
    out: list[str] = []
    in_table = False
    in_code = False

    def inline(t: str) -> str:
        t = html.escape(t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
        return t

    for raw in md.splitlines():
        line = raw.rstrip()

        if line.startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(raw))
            continue

        is_row = line.startswith("|") and line.endswith("|")
        if in_table and not is_row:
            out.append("</table>")
            in_table = False
        if is_row:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue

        if not line.strip():
            continue
        if line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")), 6)
            out.append(f"<h{level}>{inline(line.lstrip('#').strip())}</h{level}>")
        elif re.match(r"^\s*[-*]\s+", line):
            item = re.sub(r"^\s*[-*]\s+", "", line)
            out.append(f"<li>{inline(item)}</li>")
        elif line.startswith(">"):
            out.append(f"<blockquote>{inline(line.lstrip('> '))}</blockquote>")
        elif set(line.strip()) <= {"-"} and len(line.strip()) >= 3:
            out.append("<hr>")
        else:
            out.append(f"<p>{inline(line)}</p>")

    if in_table:
        out.append("</table>")
    if in_code:
        out.append("</pre>")

    body = "\n".join(out)
    body = re.sub(r"(?:<li>.*?</li>\n?)+", lambda m: f"<ul>{m.group(0)}</ul>", body, flags=re.S)
    return body


def to_html(markdown: str, title: str, out_path: str | Path) -> Path:
    p = Path(out_path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "<!doctype html>\n<html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body>\n{_md_to_html(markdown)}\n</body></html>",
        encoding="utf-8",
    )
    return p


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


def to_pdf(html_path: str | Path, out_path: str | Path) -> Path | None:
    chrome = find_chrome()
    if not chrome:
        return None
    src = Path(html_path).expanduser().resolve()
    dst = Path(out_path).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={dst}", src.as_uri()],
        capture_output=True, text=True,
    )
    return dst if dst.exists() and proc.returncode == 0 else None
