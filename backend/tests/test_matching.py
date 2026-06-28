"""Top-K mean cosine matching is how Nexus ranks jobs against the active
resume. The math is small but load-bearing — every job listing's
match_score column is downstream of these few functions.
"""
import math

import pytest

from services.matching import _clip01, _cosine_sim, top_k_mean

# ---- cosine sim ----


class TestCosineSim:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_sim(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_sim([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_sim([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_handles_different_magnitudes(self):
        # cos sim is scale-invariant
        assert _cosine_sim([1, 0], [10, 0]) == pytest.approx(1.0)

    def test_zero_vector_returns_zero(self):
        # No divide-by-zero blow-up
        assert _cosine_sim([0, 0, 0], [1, 1, 1]) == 0.0


# ---- top-K mean ----


class TestTopKMean:
    def test_top_k_picks_strongest_matches(self):
        jd = [1.0, 0.0]
        sections = [
            [1.0, 0.0],   # perfect match
            [0.9, 0.1],   # strong
            [0.5, 0.5],   # mediocre
            [0.0, 1.0],   # orthogonal
        ]
        score = top_k_mean(jd, sections, k=2)
        # Top 2 are the perfect + strong matches; mean > 0.95
        assert score > 0.95

    def test_k_clamps_to_at_least_one(self):
        # Even with k=0, falls back to at-least-one element
        jd = [1.0, 0.0]
        score = top_k_mean(jd, [[1.0, 0.0]], k=0)
        assert score == pytest.approx(1.0)

    def test_negative_scores_clipped_to_zero(self):
        # If best section is orthogonal-or-worse, score clips at 0
        jd = [1.0, 0.0]
        score = top_k_mean(jd, [[-1.0, 0.0], [-0.9, 0.1]], k=2)
        assert score == 0.0

    def test_empty_inputs_return_zero(self):
        assert top_k_mean([], [[1.0, 0.0]]) == 0.0
        assert top_k_mean([1.0, 0.0], []) == 0.0

    def test_clip01(self):
        assert _clip01(0.5) == 0.5
        assert _clip01(-1.0) == 0.0
        assert _clip01(2.0) == 1.0
        assert _clip01(0.0) == 0.0
        assert _clip01(1.0) == 1.0

    def test_k_larger_than_section_count_uses_all(self):
        # NB cosine is scale-invariant, so [1,0] and [10,0] both match [1,0]
        # at 1.0. Use vectors with different DIRECTIONS to exercise the mean.
        jd = [1.0, 0.0]
        sections = [[1.0, 0.0], [1.0, 1.0]]  # sims: 1.0 and 1/sqrt(2)
        score = top_k_mean(jd, sections, k=10)
        expected = (1.0 + 1.0 / math.sqrt(2)) / 2
        assert score == pytest.approx(expected, abs=1e-6)

    def test_skips_empty_section_embeddings(self):
        jd = [1.0, 0.0]
        sections = [[1.0, 0.0], [], [1.0, 1.0]]  # empty middle gets filtered
        score = top_k_mean(jd, sections, k=2)
        expected = (1.0 + 1.0 / math.sqrt(2)) / 2
        assert score == pytest.approx(expected, abs=1e-6)
