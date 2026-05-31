"""Markdown -> PDF rendering for the download buttons.

Used by the period-briefing expander and the board-meeting export. Pure:
takes a Markdown string and returns PDF bytes; no Streamlit, no SQLite.

Depends on two optional packages — `markdown` (Markdown -> HTML) and
`weasyprint` (HTML -> PDF). They are imported lazily so the rest of the
app keeps running if the PDF stack is not installed locally; the UI
falls back to a disabled button with an explanatory caption.

Installing on Ubuntu (deployment target):
    sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0
    pip install markdown weasyprint

Installing on macOS (dev):
    brew install pango cairo libffi
    pip install markdown weasyprint
"""

from __future__ import annotations

from typing import Optional


try:
    import markdown as _markdown
    from weasyprint import CSS, HTML  # type: ignore
    PDF_AVAILABLE = True
    IMPORT_ERROR: Optional[str] = None
except Exception as _exc:  # pragma: no cover - import side-effect guard
    _markdown = None  # type: ignore[assignment]
    HTML = None  # type: ignore[assignment]
    CSS = None  # type: ignore[assignment]
    PDF_AVAILABLE = False
    IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"


_PDF_CSS = """
@page {
    size: A4;
    margin: 2cm 2cm 2.2cm 2cm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 9pt;
        color: #888;
    }
}
body {
    font-family: 'Helvetica', 'Arial', sans-serif;
    font-size: 10.5pt;
    color: #222;
    line-height: 1.45;
}
h1 {
    font-size: 20pt;
    margin: 0 0 0.4em;
    border-bottom: 2px solid #2b5d8a;
    padding-bottom: 0.2em;
    color: #1a3d5c;
}
h2 {
    font-size: 14pt;
    margin: 1.4em 0 0.4em;
    color: #1a3d5c;
    border-bottom: 1px solid #cdd6df;
    padding-bottom: 0.15em;
    page-break-after: avoid;
}
h3 {
    font-size: 12pt;
    margin: 1.1em 0 0.3em;
    color: #2b5d8a;
    page-break-after: avoid;
}
h4 {
    font-size: 11pt;
    margin: 0.9em 0 0.25em;
    color: #2b5d8a;
    page-break-after: avoid;
}
p, li { margin: 0.3em 0; }
ul, ol { margin: 0.4em 0 0.4em 1.4em; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.6em 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}
th, td {
    border: 1px solid #cdd6df;
    padding: 4px 8px;
    text-align: left;
    vertical-align: top;
}
th { background: #eef2f6; font-weight: 600; }
code {
    font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
    font-size: 9.5pt;
    background: #f5f5f5;
    padding: 1px 4px;
    border-radius: 3px;
}
pre {
    background: #f5f5f5;
    padding: 0.6em 0.8em;
    border-radius: 4px;
    font-size: 9.5pt;
    overflow-x: auto;
}
hr { border: none; border-top: 1px solid #cdd6df; margin: 1em 0; }
blockquote {
    margin: 0.6em 0;
    padding: 0.4em 0.8em;
    border-left: 3px solid #cdd6df;
    color: #555;
    background: #fafbfc;
}
em { color: #555; }
"""


def markdown_to_pdf(md_text: str, *, title: str = "") -> bytes:
    """Render a Markdown document to PDF bytes.

    Raises RuntimeError if the optional PDF dependencies are not
    installed; callers should gate on `PDF_AVAILABLE` first.
    """
    if not PDF_AVAILABLE:
        raise RuntimeError(
            "PDF export requires the optional 'markdown' and 'weasyprint' "
            f"packages: {IMPORT_ERROR}"
        )

    html_body = _markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    html_doc = (
        "<!doctype html><html><head>"
        "<meta charset='utf-8'>"
        f"<title>{_html_escape(title)}</title>"
        "</head><body>"
        f"{html_body}"
        "</body></html>"
    )
    return HTML(string=html_doc).write_pdf(stylesheets=[CSS(string=_PDF_CSS)])


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
