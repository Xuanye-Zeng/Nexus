"""Pin the Workday CXS connector's pure parsers — the relative-timestamp
parser and the HTML stripper. Both are called for every Workday listing
during ingest, so silent regressions here would corrupt scraped_at on
thousands of rows.
"""
from datetime import UTC, datetime

import pytest

from connectors.workday import _parse_posted_on, _strip_html


class TestParsePostedOn:
    """Workday emits strings like 'Posted 2 Days Ago' / 'Posted Today'.
    We need stable UTC datetimes for scraped_at."""

    def test_today(self):
        dt = _parse_posted_on("Posted Today")
        delta = abs((datetime.now(UTC) - dt).total_seconds())
        assert delta < 5  # within a few seconds of now

    def test_yesterday(self):
        dt = _parse_posted_on("Posted Yesterday")
        delta = (datetime.now(UTC) - dt).total_seconds()
        assert 86_300 < delta < 86_500  # ~24h ago, allowing for clock slip

    @pytest.mark.parametrize(
        "phrase,approx_seconds_ago",
        [
            ("Posted 3 Days Ago", 3 * 86_400),
            ("Posted 1 Day Ago", 86_400),
            ("Posted 2 Weeks Ago", 2 * 7 * 86_400),
            ("Posted 5 Hours Ago", 5 * 3600),
            ("Posted 45 Minutes Ago", 45 * 60),
        ],
    )
    def test_relative_units(self, phrase, approx_seconds_ago):
        dt = _parse_posted_on(phrase)
        delta = (datetime.now(UTC) - dt).total_seconds()
        # Allow generous slack for test wall-clock skew
        assert abs(delta - approx_seconds_ago) < 60

    def test_plus_sign_tolerated(self):
        # Workday occasionally emits "Posted 30+ Days Ago" — should still parse
        dt = _parse_posted_on("Posted 30+ Days Ago")
        delta = (datetime.now(UTC) - dt).total_seconds()
        assert abs(delta - 30 * 86_400) < 60

    @pytest.mark.parametrize("garbage", [None, "", "totally unparseable"])
    def test_unparseable_falls_back_to_now(self, garbage):
        dt = _parse_posted_on(garbage)
        delta = abs((datetime.now(UTC) - dt).total_seconds())
        assert delta < 5


class TestStripHtml:
    """Workday job descriptions are HTML; we serve plain-ish text downstream
    to the LLM + the dashboard. The stripper is conservative: drop tags,
    normalize line breaks, decode common entities — don't try to be a full
    HTML5 parser."""

    def test_removes_tags(self):
        assert _strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_br_becomes_newline(self):
        out = _strip_html("Line one<br>Line two<br />Line three")
        assert "Line one\nLine two\nLine three" in out

    def test_closing_p_becomes_paragraph_break(self):
        out = _strip_html("<p>First</p><p>Second</p>")
        assert "First" in out
        assert "Second" in out
        # Either one or two newlines between — collapse rule is N>=3 -> 2
        assert "\n" in out

    def test_li_becomes_newline(self):
        out = _strip_html("<ul><li>One</li><li>Two</li></ul>")
        assert "One" in out
        assert "Two" in out
        assert "One\nTwo" in out or "One \nTwo" in out

    def test_entities_decoded(self):
        assert _strip_html("Smith &amp; Co") == "Smith & Co"
        assert _strip_html("&lt;script&gt;") == "<script>"
        assert _strip_html("Joe&#39;s shop") == "Joe's shop"
        assert _strip_html("&nbsp;hello") == "hello"  # leading nbsp collapsed by strip()

    def test_collapses_excessive_blank_lines(self):
        out = _strip_html("a</p></p></p></p>b")
        # All those </p> would produce many \n\n; the regex collapses 3+ to 2
        assert "\n\n\n" not in out

    @pytest.mark.parametrize("garbage", [None, ""])
    def test_passthrough_empty(self, garbage):
        assert _strip_html(garbage) == garbage
