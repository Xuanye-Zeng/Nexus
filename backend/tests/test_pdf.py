"""Tests for services.pdf — BEFORE/AFTER/REASON parsing + PDF magic bytes.

The parser here MUST behave the same way as
`frontend/src/lib/parseRewrite.ts` so what the user copies out of the UI
matches what lands in the exported PDF.

PDF-generating tests require WeasyPrint's native deps (cairo, pango, gdk-pixbuf).
Install on macOS: `brew install cairo pango gdk-pixbuf libffi`.
Install on Ubuntu: `apt-get install libpango-1.0-0 libpangoft2-1.0-0`.
CI runs `apt-get install …` before pytest so these tests DO execute there.
"""
import pytest

from services.pdf import (
    markdown_to_pdf,
    parse_rewrite,
    rewrite_to_clean_markdown,
)


def _weasyprint_native_libs_available() -> bool:
    """Attempt a tiny PDF render — succeeds only if cairo/pango are on the box."""
    try:
        from weasyprint import HTML

        HTML(string="<p>ping</p>").write_pdf()
        return True
    except Exception:  # noqa: BLE001 — env probe, any failure = "not available"
        return False


_HAS_PDF_LIBS = _weasyprint_native_libs_available()
requires_weasyprint = pytest.mark.skipif(
    not _HAS_PDF_LIBS,
    reason="cairo/pango not installed — install via brew (macOS) or apt-get (Linux)",
)

# ---- parse_rewrite ---------------------------------------------------------


class TestParseRewrite:
    def test_basic_triple_extracts_after(self):
        md = (
            "## PROJECTS\n"
            "### Project A (2024)\n"
            "- BEFORE: Built a legacy thing\n"
            "AFTER: Built a scalable Kubernetes system\n"
            "REASON: mirrors JD terminology\n"
        )
        sections = parse_rewrite(md)
        assert len(sections) == 1
        assert sections[0].name == "PROJECTS"
        assert len(sections[0].items) == 1
        item = sections[0].items[0]
        assert item.heading == "Project A (2024)"
        assert len(item.bullets) == 1
        b = item.bullets[0]
        assert b.after == "Built a scalable Kubernetes system"
        assert b.final == "Built a scalable Kubernetes system"
        assert b.kept is False

    def test_after_keep_falls_back_to_before(self):
        md = (
            "## EXPERIENCE\n"
            "### Role @ Co (2023)\n"
            "- BEFORE: Reduced latency by 30%\n"
            "AFTER: KEEP\n"
            "REASON: already tight\n"
        )
        [section] = parse_rewrite(md)
        b = section.items[0].bullets[0]
        assert b.kept is True
        assert b.final == "Reduced latency by 30%"

    def test_multiple_bullets_in_one_item(self):
        md = (
            "## PROJECTS\n"
            "### Project A\n"
            "- BEFORE: One\n"
            "AFTER: One rewritten\n"
            "REASON: r1\n"
            "\n"
            "- BEFORE: Two\n"
            "AFTER: KEEP\n"
            "REASON: r2\n"
        )
        [section] = parse_rewrite(md)
        bullets = section.items[0].bullets
        assert [b.final for b in bullets] == ["One rewritten", "Two"]
        assert [b.kept for b in bullets] == [False, True]

    def test_skills_section_passes_raw_lines(self):
        md = (
            "## PROJECTS\n"
            "### Project A\n"
            "- BEFORE: X\n"
            "AFTER: Y\n"
            "REASON: r\n"
            "## SKILLS\n"
            "- Programming Languages: Python, Java\n"
        )
        sections = parse_rewrite(md)
        skills = [s for s in sections if s.name == "SKILLS"][0]
        # Skills section has no ### items — the bullet line becomes preamble.
        assert any(
            "Programming Languages" in line for line in skills.preamble
        )

    def test_no_before_after_structure_yields_empty_bullets(self):
        md = "## PROJECTS\n### Project A\nSome free text here\n"
        [section] = parse_rewrite(md)
        assert section.items[0].bullets == []
        assert "Some free text here" in section.items[0].raw_lines


# ---- rewrite_to_clean_markdown ---------------------------------------------


class TestCleanMarkdown:
    def test_final_output_drops_before_and_reason(self):
        md = (
            "## PROJECTS\n"
            "### Project A\n"
            "- BEFORE: Old text with 30%\n"
            "AFTER: New shiny bullet\n"
            "REASON: mirrors JD\n"
        )
        clean = rewrite_to_clean_markdown(parse_rewrite(md))
        assert "BEFORE" not in clean
        assert "REASON" not in clean
        assert "New shiny bullet" in clean
        assert "Old text with 30%" not in clean

    def test_kept_bullets_render_before_text(self):
        md = (
            "## PROJECTS\n"
            "### Project A\n"
            "- BEFORE: Reduced latency by 30%\n"
            "AFTER: KEEP\n"
            "REASON: keep the number\n"
        )
        clean = rewrite_to_clean_markdown(parse_rewrite(md))
        assert "Reduced latency by 30%" in clean
        assert "KEEP" not in clean


# ---- markdown_to_pdf edge cases + magic bytes ------------------------------


@requires_weasyprint
class TestMarkdownToPdf:
    def test_returns_pdf_magic_bytes(self):
        md = (
            "## PROJECTS\n"
            "### Project A (2024)\n"
            "- BEFORE: Built a thing\n"
            "AFTER: Built a scalable distributed system\n"
            "REASON: mirrors JD\n"
        )
        pdf = markdown_to_pdf(md, title="Alex Zeng Resume")
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF-")
        # Sanity — a non-trivial PDF is going to be at least a few KB.
        assert len(pdf) > 1000

    def test_plain_markdown_without_triples_still_renders(self):
        pdf = markdown_to_pdf("# Alex Zeng\n\n- One\n- Two\n", title="Resume")
        assert pdf.startswith(b"%PDF-")

    def test_empty_markdown_returns_valid_pdf(self):
        pdf = markdown_to_pdf("", title="Resume")
        assert pdf.startswith(b"%PDF-")

    def test_single_bullet_input(self):
        md = (
            "## PROJECTS\n"
            "### Only One\n"
            "- BEFORE: Wrote code\n"
            "AFTER: Shipped code to production for 10M users\n"
            "REASON: quantify impact\n"
        )
        pdf = markdown_to_pdf(md, title="Resume")
        assert pdf.startswith(b"%PDF-")


# ---- markdown_to_pdf shouldn't crash on odd inputs -------------------------


@requires_weasyprint
@pytest.mark.parametrize(
    "md",
    [
        "",
        "# Just a heading",
        "## PROJECTS\n### Item\nplain text\n",
        "## PROJECTS\n### Item\n- BEFORE: x\nAFTER: y\nREASON: z\n",
    ],
)
def test_markdown_to_pdf_never_crashes(md: str) -> None:
    pdf = markdown_to_pdf(md, title="Resume")
    assert pdf.startswith(b"%PDF-")
