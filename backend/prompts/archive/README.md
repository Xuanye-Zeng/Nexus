# Archived prompt versions

Prompts that have been superseded by a later version. They are kept in version
control (not deleted) because the iteration history is the load-bearing
narrative for this project — but they live outside `prompts/` so
`scripts/seed_prompts.py` doesn't re-seed them on startup.

The currently-live prompts are in `prompts/*.md` (one file per active version).
A version's `is_active` flag in the DB is the source of truth at runtime.

## What's here and why it was retired

| File | Reason |
|---|---|
| `bullet_rewriter.v1.md` – `v7.md` | Iteration toward v8. v8 was the stable local optimum (1% bullet-level fail rate over 100 rewrites). |
| `bullet_rewriter.v9.md` | Result-first phrasing regressed by fabricating a "0%" metric not in the source. Rolled back to v8. |
| `email_classifier.v1.md` | Misclassified a Figma rejection email as `application_confirmation` because the subject framing fooled it. v2 adds an explicit REJECTION OVERRIDE rule with 10 trigger phrases. |
| `master_intent_classifier.v2.md` | Knew the v1.5 admin tools (ingest_jobs / rescore_listings / get_top_resume_sections_for_jd). v3 added the M3 email tools (triage_emails / delete_emails) and the "delete requires at least one filter" safety. |

To revive a version: copy back to `prompts/`, set its `is_active: true` in the
frontmatter, and run `scripts/seed_prompts.py`. To replay an A/B test, run with
both versions seeded and only flip `is_active` at query time.
