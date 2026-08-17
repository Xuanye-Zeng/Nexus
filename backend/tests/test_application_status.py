"""Pin the sticky applied_at rule + status enum boundary.

The endpoint's job is DB I/O — those paths are exercised via manual smoke
tests + `/api/jobs/applications*` in the running app. This pins the
*decision rule* (when to stamp applied_at) so the sticky invariant can
never quietly regress: reverting a status from 'applied' back to 'saved'
must preserve the historical applied_at timestamp so the weekly-cadence
KPI on the Dashboard stays honest.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from routers.jobs import _ALL_STATUSES, _APPLIED_STAGES, next_applied_at

NOW = datetime(2026, 8, 17, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


class TestNextAppliedAt:
    def test_saved_from_scratch_stays_none(self):
        assert next_applied_at(None, "saved", NOW) is None

    def test_applied_from_scratch_stamps_now(self):
        assert next_applied_at(None, "applied", NOW) == NOW

    @pytest.mark.parametrize(
        "stage",
        sorted(_APPLIED_STAGES),
    )
    def test_every_applied_family_stage_stamps_when_previously_null(self, stage):
        assert next_applied_at(None, stage, NOW) == NOW

    def test_withdrawn_from_scratch_stays_none(self):
        """Withdrawing without ever applying is legit — we track intent to
        drop the pipeline, not a phantom application."""
        assert next_applied_at(None, "withdrawn", NOW) is None

    def test_revert_applied_to_saved_preserves_original_stamp(self):
        """The core sticky invariant. User applied at NOW, then decides to
        step back to `saved`. The historical fact ("applied at NOW") stays."""
        assert next_applied_at(NOW, "saved", LATER) == NOW

    def test_revert_applied_to_withdrawn_preserves_original_stamp(self):
        assert next_applied_at(NOW, "withdrawn", LATER) == NOW

    def test_reapply_after_withdraw_does_not_reset_stamp(self):
        """You withdrew, then re-applied. The KPI cares about "did the user
        submit an application in this window" — reusing the original stamp
        avoids double-counting the same posting."""
        assert next_applied_at(NOW, "applied", LATER) == NOW

    def test_transition_within_applied_family_preserves_stamp(self):
        assert next_applied_at(NOW, "interviewing", LATER) == NOW
        assert next_applied_at(NOW, "offer", LATER) == NOW
        assert next_applied_at(NOW, "rejected", LATER) == NOW


class TestStatusEnumConsistency:
    def test_all_statuses_includes_applied_stages(self):
        """The status enum in the DB check constraint MUST cover every
        applied-family stage — a mismatch would mean the resolver stamps
        applied_at on a status the DB rejects."""
        for stage in _APPLIED_STAGES:
            assert stage in _ALL_STATUSES

    def test_saved_and_withdrawn_not_in_applied_family(self):
        """Guard rail — 'saved' and 'withdrawn' are BEFORE-and-AFTER the
        application submission event; stamping them would corrupt the
        weekly-cadence signal."""
        assert "saved" not in _APPLIED_STAGES
        assert "withdrawn" not in _APPLIED_STAGES
