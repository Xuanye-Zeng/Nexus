"""normalize_company_name() is the join key between Adzuna brand names and
DOL OFLC LCA legal entity names. These tests pin the contract that 97%
canonical-brand match rate depends on.
"""
import pytest

from services.normalize import normalize_company_name

# ---- happy paths: legal suffix stripping ----


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Amazon.com Services LLC", "amazon com services"),
        ("Amazon Web Services Inc", "amazon web services"),
        ("AMAZON WEB SERVICES, INC", "amazon web services"),
        ("Apple Inc.", "apple"),
        ("Google LLC", "google"),
        ("Microsoft Corporation", "microsoft"),
        ("Stripe, Inc.", "stripe"),
        ("NVIDIA Corporation", "nvidia"),
        ("Tesla, Inc.", "tesla"),
        ("Salesforce, Inc.", "salesforce"),
        ("Cognizant Technology Solutions US Corp", "cognizant technology solutions us"),
        ("INFOSYS LIMITED", "infosys"),
        ("Lockheed Martin Corporation", "lockheed martin"),
    ],
)
def test_strips_trailing_legal_suffix(raw, expected):
    assert normalize_company_name(raw) == expected


# ---- "The X" prefix ----


def test_strips_leading_the():
    assert normalize_company_name("The New York Times Company") == "new york times"
    assert normalize_company_name("THE BOEING COMPANY") == "boeing"


# ---- ampersand preserved (AT&T, AGI & Co, etc.) ----


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("AT&T Inc.", "at&t"),
        ("Ernst & Young U.S. LLP", "ernst & young u s"),
        ("JPMorgan Chase & Co.", "jpmorgan chase &"),
        ("Goldman Sachs & Co. LLC", "goldman sachs &"),
        ("Johnson & Johnson", "johnson & johnson"),
    ],
)
def test_keeps_ampersand(raw, expected):
    assert normalize_company_name(raw) == expected


# ---- stacked suffixes: "Stripe, Inc., LLC" should strip BOTH ----


def test_strips_stacked_suffixes():
    assert normalize_company_name("Stripe, Inc., LLC") == "stripe"
    assert normalize_company_name("Anthropic, PBC") == "anthropic pbc"  # PBC not in suffix list


# ---- empty / null / whitespace ----


@pytest.mark.parametrize("raw", ["", "  ", None])
def test_empty_inputs_return_empty(raw):
    assert normalize_company_name(raw) == ""


# ---- case normalization ----


def test_lowercases():
    assert normalize_company_name("APPLE") == "apple"
    assert normalize_company_name("ApPLe iNc.") == "apple"


# ---- punctuation collapse ----


def test_strips_punctuation_keeps_letters_digits_ampersand():
    # Periods, commas, dashes get removed; letters and digits survive.
    assert normalize_company_name("Yahoo!") == "yahoo"
    assert normalize_company_name("E*Trade Financial") == "e trade financial"
    assert normalize_company_name("3M Company") == "3m"
    assert normalize_company_name("Booz Allen Hamilton Holding Corporation") == "booz allen hamilton holding"
