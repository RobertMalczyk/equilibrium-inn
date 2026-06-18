"""CI gate for the aggressive QA battery (qa/qa_suite.py).

Runs the full battery ONCE (module-scoped) and asserts every deep check is not a
FAIL — so a broken contract (determinism, resolution refinement, intervention
safety, trace invariants, config/input validation, parity, boundedness) fails CI.
WARN is allowed (soft targets like the incident corridor are not defects).

This is heavier than a unit test (it runs many full sessions); it is the promotion
gate, complementary to the focused unit tests. Run the report locally with:
    python -m qa.qa_suite
"""

import pytest

from qa import qa_suite as QA


@pytest.fixture(scope="module")
def results():
    return {r.id: r for r in QA.run_all(verbose=False)}


@pytest.mark.parametrize("check_id", [fn._meta[0] for fn in QA.CHECKS])
def test_qa_check(results, check_id):
    r = results[check_id]
    assert r.status != QA.FAIL, f"{r.id} {r.name}: {r.detail}"


def test_qa_verdict_is_promote(results):
    # no FAIL across the whole battery -> the engine is promotable through the inn.
    fails = [r.id for r in results.values() if r.status == QA.FAIL]
    assert not fails, f"QA battery FAILs: {fails}"
