"""Markdown → HTML → PDF pipeline for the customized resume export.

The `bullet_rewriter` prompt emits BEFORE / AFTER / REASON triples per bullet.
On the resume PDF the user actually hands to a recruiter we ONLY want the
final AFTER text (or the BEFORE text when AFTER=KEEP). The parsing rules here
mirror `frontend/src/lib/parseRewrite.ts` so what renders in the PDF matches
what the UI shows.

The PDF stage is intentionally a pure `markdown_to_pdf(md, title) -> bytes`
function so it stays trivially testable (no FastAPI, no I/O, no globals).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape

# WeasyPrint is imported lazily inside `markdown_to_pdf` — it pulls in native
# cairo/pango/gdk libraries that aren't present in every environment (bare
# CI runners, IDE analyzers). Keeping the top-level import to `markdown` only
# lets `parse_rewrite` + `rewrite_to_clean_markdown` be imported and unit-tested
# without the full PDF stack installed.
import markdown as md_lib

# ---- regexes mirrored from frontend/src/lib/parseRewrite.ts ------------------

SECTION_RE = re.compile(r"^##\s+([^\n]+)")
ITEM_RE = re.compile(r"^###\s+([^\n]+)")
BEFORE_RE = re.compile(r"^\s*-?\s*BEFORE:\s*(.+)$", re.IGNORECASE)
AFTER_RE = re.compile(r"^\s*AFTER:\s*(.+)$", re.IGNORECASE)
REASON_RE = re.compile(r"^\s*REASON:\s*(.+)$", re.IGNORECASE)


# ---- structured intermediate form -------------------------------------------


@dataclass
class BulletTriple:
    before: str
    after: str
    kept: bool

    @property
    def final(self) -> str:
        """The line that actually belongs on the resume — AFTER unless KEEP."""
        return self.before if self.kept else self.after


@dataclass
class RewrittenItem:
    heading: str
    bullets: list[BulletTriple] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)


@dataclass
class RewrittenSection:
    name: str
    items: list[RewrittenItem] = field(default_factory=list)
    preamble: list[str] = field(default_factory=list)


# ---- parser: mirrors parseRewrite.ts ----------------------------------------


def parse_rewrite(text: str) -> list[RewrittenSection]:
    """Parse the bullet_rewriter output into sections + BEFORE/AFTER triples.

    Mirrors `frontend/src/lib/parseRewrite.ts`. `AFTER: KEEP` means "use the
    BEFORE text as-is"; any other AFTER value replaces the BEFORE.
    """
    sections: list[RewrittenSection] = []
    current_section: RewrittenSection | None = None
    current_item: RewrittenItem | None = None
    pending: dict[str, str] | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending and current_item and pending.get("before"):
            after = pending.get("after", "")
            kept = after.strip().upper() == "KEEP"
            current_item.bullets.append(
                BulletTriple(before=pending["before"], after=after, kept=kept)
            )
        pending = None

    for raw in text.split("\n"):
        line = raw.strip()

        m = SECTION_RE.match(line)
        if m:
            flush_pending()
            current_item = None
            current_section = RewrittenSection(name=m.group(1).strip().upper())
            sections.append(current_section)
            continue

        if current_section is None:
            continue

        m = ITEM_RE.match(line)
        if m:
            flush_pending()
            current_item = RewrittenItem(heading=m.group(1).strip())
            current_section.items.append(current_item)
            continue

        m = BEFORE_RE.match(line)
        if m:
            flush_pending()
            pending = {"before": m.group(1).strip()}
            continue

        m = AFTER_RE.match(line)
        if m and pending is not None:
            pending["after"] = m.group(1).strip()
            continue

        m = REASON_RE.match(line)
        if m and pending is not None:
            # We drop REASON — recruiter-facing PDF doesn't need editorial notes.
            continue

        if not line:
            continue
        if current_item is not None:
            current_item.raw_lines.append(line)
        else:
            current_section.preamble.append(line)

    flush_pending()
    return sections


def rewrite_to_clean_markdown(sections: list[RewrittenSection]) -> str:
    """Emit recruiter-ready markdown: only final bullet text, no BEFORE/REASON."""
    out: list[str] = []
    for section in sections:
        out.append(f"## {section.name}")
        for line in section.preamble:
            out.append(line)
        for item in section.items:
            out.append("")
            out.append(f"### {item.heading}")
            for b in item.bullets:
                out.append(f"- {b.final}")
            for r in item.raw_lines:
                out.append(r)
        out.append("")
    return "\n".join(out).strip()


# ---- HTML template ----------------------------------------------------------

_CSS = """
@page {
  size: Letter;
  margin: 1in;
}
html { font-family: 'Inter', 'Helvetica Neue', system-ui, sans-serif; color: #111; }
body { font-size: 11pt; line-height: 1.35; margin: 0; }
h1 {
  font-size: 24pt;
  font-weight: 600;
  margin: 0 0 4pt 0;
  letter-spacing: -0.01em;
  page-break-after: avoid;
}
h2 {
  font-size: 14pt;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 14pt 0 4pt 0;
  border-bottom: 0.5pt solid #333;
  padding-bottom: 2pt;
  page-break-after: avoid;
}
h3 {
  font-size: 11pt;
  font-weight: 600;
  margin: 8pt 0 2pt 0;
  page-break-after: avoid;
}
ul { margin: 2pt 0 6pt 0; padding-left: 18pt; page-break-inside: avoid; }
li { margin: 1pt 0; }
p { margin: 2pt 0; }
"""


def _wrap_html(body_html: str, title: str) -> str:
    return (
        "<!DOCTYPE html>"
        f"<html><head><meta charset=\"utf-8\"><title>{escape(title)}</title>"
        f"<style>{_CSS}</style></head>"
        f"<body><h1>{escape(title)}</h1>{body_html}</body></html>"
    )


# ---- public entry point -----------------------------------------------------


def markdown_to_pdf(md: str, title: str) -> bytes:
    """Convert BEFORE/AFTER/REASON-flavored resume markdown into a PDF.

    Parses the rewriter output into sections + triples (`AFTER: KEEP` falls
    back to BEFORE), strips REASON notes, renders through the markdown lib,
    wraps in the resume HTML template, and hands to WeasyPrint.

    If the input isn't in the BEFORE/AFTER format at all (no BEFORE lines
    detected), we fall back to rendering the raw markdown — this covers the
    "user already cleaned the output" and "plain markdown from elsewhere" cases.
    """
    sections = parse_rewrite(md)
    has_triples = any(item.bullets for section in sections for item in section.items)
    body_md = rewrite_to_clean_markdown(sections) if has_triples else md.strip()
    body_html = md_lib.markdown(body_md, extensions=["extra"]) if body_md else ""
    html_doc = _wrap_html(body_html, title=title or "Resume")
    from weasyprint import HTML  # lazy — see top-of-file note

    return HTML(string=html_doc).write_pdf()
