"""Verify the 3-layer employer lookup against a set of canonical Adzuna-style
brand names. Prints which layer hit and the matched LCA filer + count.

Run from backend/:  venv/bin/python -m scripts.test_employer_lookup
"""
import asyncio

from db import SessionLocal
from services.employer_lookup import lookup_employer

# Mix of cases:
#  - exact wins (Apple, Stripe, Snowflake)
#  - alias wins (Meta, Amazon, Walmart, JPMC, Ford, Cognizant)
#  - prefix wins (Goldman Sachs -> Goldman Sachs & Co LLC, Capital One)
#  - miss (a random small startup that doesn't sponsor)
TEST_NAMES = [
    "Apple",
    "Google",
    "Microsoft",
    "NVIDIA",
    "Stripe",
    "Snowflake",
    "Anthropic",
    "Salesforce",
    "Adobe",
    "LinkedIn",
    "Meta",
    "Facebook",
    "Amazon",
    "AWS",
    "Amazon Web Services",
    "TikTok",
    "Walmart",
    "Ford",
    "JPMorgan",
    "JPMC",
    "Capital One",
    "Goldman Sachs",
    "Cognizant",
    "Infosys",
    "TCS",
    "Deloitte",
    "EY",
    "PwC",
    "Tesla",
    "Uber",
    "PayPal",
    "Cisco",
    "IBM",
    "Oracle",
    "Intel",
    "Qualcomm",
    "Some Random Local Startup",
]


async def main() -> None:
    async with SessionLocal() as s:
        print(f"{'adzuna name':<30}  {'layer':<7}  {'12mo':>6}  {'matched legal':<55}")
        print("-" * 110)
        layer_counts = {"exact": 0, "alias": 0, "prefix": 0, "miss": 0}
        for name in TEST_NAMES:
            row, layer = await lookup_employer(s, name)
            layer_counts[layer] += 1
            if row:
                print(
                    f"{name:<30}  {layer:<7}  {row.lca_count_last_12mo:>6}  "
                    f"{row.employer_name_display[:55]}"
                )
            else:
                print(f"{name:<30}  {layer:<7}  {'-':>6}  -")
        print("-" * 110)
        print(f"summary: {layer_counts}")


if __name__ == "__main__":
    asyncio.run(main())
