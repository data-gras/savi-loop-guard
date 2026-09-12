"""
Trip/no-trip scenarios for both detectors (velocity and structural,
including the fuzzy tool-name matching) - bursts vs. steady rates,
near-duplicate tool names, and mixed bursty-and-repetitive patterns.
"""
import pytest
from datetime import datetime, timezone, timedelta

from loop_guard import LoopGuard, CallEvent, LoopType, LoopDetected


def _event(agent_id, seconds_offset=0, tool_call=None, span_id=None):
    return CallEvent(
        span_id=span_id or f"span_{agent_id}_{seconds_offset}_{tool_call}",
        agent_id=agent_id,
        timestamp=datetime.now(timezone.utc) + timedelta(seconds=seconds_offset),
        tool_call=tool_call,
    )


# ── Velocity / structural trip and no-trip scenarios ────────────────────────

def test_velocity_loop_detected():
    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    for i in range(6):
        guard.record(_event("agent-looper", seconds_offset=i * 4))
    issues = guard.check()
    assert len(issues) == 1
    assert issues[0]["type"] == LoopType.VELOCITY


def test_no_false_positive_for_slow_agent():
    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    for i in range(6):
        guard.record(_event("agent-slow", seconds_offset=i * 60))
    assert guard.check() == []


def test_structural_loop_detected():
    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    for i in range(6):
        guard.record(_event("agent-repeater", seconds_offset=i * 10, tool_call="search(query='AI news')"))
    issues = guard.check()
    structural = [i for i in issues if i["type"] == LoopType.STRUCTURAL]
    assert len(structural) == 1


def test_single_call_no_loop():
    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    guard.record(_event("agent-once"))
    assert guard.check() == []


def test_thresholds_configurable():
    guard = LoopGuard(velocity_window_seconds=60, velocity_call_limit=2, structural_call_limit=5)
    for i in range(3):
        guard.record(_event("agent-tight", seconds_offset=i * 10))
    issues = guard.check()
    assert any(i["type"] == LoopType.VELOCITY for i in issues)


# ── Fuzzy tool-name matching ─────────────────────────────────────────────────

class TestToolTokens:
    def _fn(self, name):
        from loop_guard.detector import _tool_tokens
        return _tool_tokens(name)

    def test_splits_on_underscore(self):
        tokens = self._fn("search_web")
        assert "search" in tokens and "web" in tokens

    def test_strips_v_suffix(self):
        tokens = self._fn("search_web_v2")
        assert "v2" not in tokens
        assert "search" in tokens and "web" in tokens

    def test_empty_string_returns_empty_set(self):
        assert self._fn("") == set()


class TestJaccard:
    def _fn(self, a, b):
        from loop_guard.detector import _jaccard
        return _jaccard(a, b)

    def test_identical_sets_return_one(self):
        assert self._fn({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets_return_zero(self):
        assert self._fn({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        assert abs(self._fn({"a", "b"}, {"b", "c"}) - 1 / 3) < 0.001


class TestCanonicalTool:
    def _fn(self, name, seen, threshold=0.70):
        from loop_guard.detector import _canonical_tool
        return _canonical_tool(name, seen, threshold)

    def test_new_tool_registers_itself_as_canonical(self):
        seen = {}
        assert self._fn("search_web", seen) == "search_web"
        assert "search_web" in seen

    def test_similar_tool_maps_to_existing_canonical(self):
        seen = {}
        self._fn("search_web", seen)
        assert self._fn("search_web_v2", seen) == "search_web"

    def test_dissimilar_tool_registers_new_canonical(self):
        seen = {}
        self._fn("search_web", seen)
        assert self._fn("send_email", seen) == "send_email"


class TestDetectLoopsFuzzy:
    def _guard(self, threshold=0.70):
        return LoopGuard(
            velocity_window_seconds=30, velocity_call_limit=5,
            structural_call_limit=3, tool_fuzzy_similarity_threshold=threshold,
        )

    def test_exact_repeated_tool_triggers_structural_loop(self):
        guard = self._guard()
        for i in range(5):
            guard.record(_event("agent1", seconds_offset=i * 10, tool_call="search_web", span_id=f"s{i}"))
        structural = [i for i in guard.check() if i["type"] == LoopType.STRUCTURAL]
        assert len(structural) >= 1

    def test_fuzzy_variant_triggers_same_structural_loop(self):
        guard = self._guard(threshold=0.70)
        tools = ["search_web", "search_web_v2", "search_web", "search_web_v2"]
        for i, t in enumerate(tools):
            guard.record(_event("agent1", seconds_offset=i * 10, tool_call=t, span_id=f"s{i}"))
        structural = [i for i in guard.check() if i["type"] == LoopType.STRUCTURAL]
        assert len(structural) >= 1

    def test_unrelated_tools_not_grouped(self):
        guard = self._guard(threshold=0.70)
        tools = ["search_web", "send_email", "search_web", "send_email"]
        for i, t in enumerate(tools):
            guard.record(_event("agent1", seconds_offset=i * 10, tool_call=t, span_id=f"s{i}"))
        structural = [i for i in guard.check() if i["type"] == LoopType.STRUCTURAL]
        assert len(structural) == 0

    def test_structural_issue_includes_tool_variants(self):
        guard = self._guard(threshold=0.70)
        tools = ["search_web", "search_web_v2", "search_web_v3", "search_web", "search_web_v2"]
        for i, t in enumerate(tools):
            guard.record(_event("agent1", seconds_offset=i * 10, tool_call=t, span_id=f"s{i}"))
        structural = [i for i in guard.check() if i["type"] == LoopType.STRUCTURAL]
        assert structural and "tool_variants" in structural[0]


# ── check_before_call() / LoopDetected — the genuine gap vs. real competitors ──

def test_check_before_call_raises_on_velocity_trip():
    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    for i in range(5):
        guard.check_before_call(_event("agent-looper", seconds_offset=i * 4))
    with pytest.raises(LoopDetected) as exc_info:
        guard.check_before_call(_event("agent-looper", seconds_offset=5 * 4))
    assert exc_info.value.loop_type == "velocity_loop"
    assert exc_info.value.details["agent_id"] == "agent-looper"


def test_check_before_call_does_not_raise_when_no_loop():
    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    guard.check_before_call(_event("agent-once"))  # should not raise


def test_check_before_call_raises_at_same_point_check_would_return_nonempty():
    # Same trip condition as test_velocity_loop_detected above (6 calls,
    # 4s apart, limit 5) - confirms check_before_call's raise fires at the
    # exact same underlying condition check() reports, not a different one.
    guard_observed = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    for i in range(6):
        guard_observed.record(_event("agent-looper", seconds_offset=i * 4, span_id=f"s{i}"))
    assert len(guard_observed.check()) == 1

    guard_preventive = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    raised = False
    for i in range(6):
        try:
            guard_preventive.check_before_call(_event("agent-looper", seconds_offset=i * 4, span_id=f"s{i}"))
        except LoopDetected:
            raised = True
            assert i == 5  # trips on the 6th call, same as check()'s window math
    assert raised


def test_check_before_call_raises_on_structural_trip():
    # The velocity test above never exercises check_before_call()'s other
    # trip condition - a preventive-mode caller relying only on velocity
    # coverage would still be exposed to a tool-repeat loop.
    guard = LoopGuard(
        velocity_window_seconds=30, velocity_call_limit=10,  # high enough to not also trip
        structural_call_limit=3, tool_fuzzy_similarity_threshold=0.70,
    )
    for i in range(3):
        guard.check_before_call(_event("agent1", seconds_offset=i * 10, tool_call="search_web", span_id=f"s{i}"))
    with pytest.raises(LoopDetected) as exc_info:
        guard.check_before_call(_event("agent1", seconds_offset=40, tool_call="search_web", span_id="s4"))
    assert exc_info.value.loop_type == "structural_loop"
    assert exc_info.value.details["agent_id"] == "agent1"


def test_velocity_and_structural_can_both_fire_in_one_check():
    # check() runs both detectors independently and appends to the same
    # list - neither trip suppresses the other. Worth proving explicitly
    # since production loops often look bursty AND repetitive at once.
    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=3, structural_call_limit=3)
    for i in range(4):
        guard.record(_event("agent1", seconds_offset=i * 4, tool_call="search_web", span_id=f"s{i}"))
    issues = guard.check()
    assert any(i["type"] == LoopType.VELOCITY for i in issues)
    assert any(i["type"] == LoopType.STRUCTURAL for i in issues)


def test_agents_are_isolated_from_each_other():
    # by_agent groups events per agent_id before either check runs - a
    # looping agent must never cause a false trip for an unrelated one
    # sharing the same LoopGuard instance.
    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    for i in range(6):
        guard.record(_event("agent-a", seconds_offset=i * 4))
    guard.record(_event("agent-b", seconds_offset=0))
    issues = guard.check()
    assert any(i["agent_id"] == "agent-a" and i["type"] == LoopType.VELOCITY for i in issues)
    assert not any(i["agent_id"] == "agent-b" for i in issues)


def test_velocity_window_boundary():
    # check() only evaluates fixed-size windows of exactly
    # velocity_call_limit + 1 consecutive (by time) events - not a
    # continuously-sliding window. With exactly 6 events there is exactly
    # one such window to check, so these boundary values matter.
    #
    # Uses one fixed base timestamp rather than _event()'s implicit
    # datetime.now() per call - at an exact 30s boundary, the real wall-clock
    # time elapsed between six separate now() calls is enough to push the
    # computed elapsed_s a hair past 30, flipping the <=30 check. That's a
    # timing artifact of the test helper, not of the detector.
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def _at(agent_id, offset, span_id):
        return CallEvent(span_id=span_id, agent_id=agent_id, timestamp=base + timedelta(seconds=offset))

    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    for i in range(5):
        guard.record(_at("agent1", i * 6, f"s{i}"))
    assert guard.check() == []  # 5 calls, no window of 6 exists yet

    guard.record(_at("agent1", 30, "s5"))  # 6th call, span exactly 30s
    assert any(i["type"] == LoopType.VELOCITY for i in guard.check())  # <=30s: trips

    guard2 = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    for i in range(5):
        guard2.record(_at("agent1", i * 6, f"s{i}"))
    guard2.record(_at("agent1", 31, "s5"))  # span 31s
    assert guard2.check() == []  # >30s: does not trip


def test_loop_detected_details_carry_the_real_fields():
    # The issue dict's actual shape (per detector.py's issues.append() calls):
    # velocity -> agent_id/elapsed_s/call_count, structural ->
    # agent_id/tool_call/tool_variants/call_count. No timestamp/span_id/
    # window_seconds field exists on either - asserting for those would be
    # asserting something this package has never actually produced.
    guard = LoopGuard(velocity_window_seconds=30, velocity_call_limit=5, structural_call_limit=5)
    for i in range(5):
        guard.check_before_call(_event("agent-looper", seconds_offset=i * 4, span_id=f"s{i}"))
    with pytest.raises(LoopDetected) as exc_info:
        guard.check_before_call(_event("agent-looper", seconds_offset=5 * 4, span_id="s5"))
    details = exc_info.value.details
    assert details["agent_id"] == "agent-looper"
    assert "elapsed_s" in details
    assert details["call_count"] == 6

    guard2 = LoopGuard(velocity_window_seconds=30, velocity_call_limit=10, structural_call_limit=3)
    for i in range(3):
        guard2.check_before_call(_event("agent2", seconds_offset=i * 10, tool_call="search_web", span_id=f"t{i}"))
    with pytest.raises(LoopDetected) as exc_info2:
        guard2.check_before_call(_event("agent2", seconds_offset=40, tool_call="search_web", span_id="t4"))
    details2 = exc_info2.value.details
    assert details2["agent_id"] == "agent2"
    assert details2["tool_call"] == "search_web"
    assert "tool_variants" in details2
    assert details2["call_count"] == 4


def test_fuzzy_threshold_boundary_with_genuine_partial_overlap():
    # "search_web" vs "search_web_v2" is NOT a valid pair for this: the v2
    # suffix is stripped by _tool_tokens() before Jaccard ever runs, so
    # those two are token-identical regardless of threshold (see
    # TestToolTokens.test_strips_v_suffix above). "search_web" vs
    # "web_lookup" share exactly one token ("web") out of three total ->
    # Jaccard = 1/3 ~= 0.33, a genuine partial overlap to test a threshold
    # boundary against.
    tools = ["search_web", "web_lookup", "search_web", "web_lookup"]

    guard_loose = LoopGuard(
        velocity_window_seconds=30, velocity_call_limit=10,
        structural_call_limit=3, tool_fuzzy_similarity_threshold=0.30,
    )
    for i, t in enumerate(tools):
        guard_loose.record(_event("agent1", seconds_offset=i * 10, tool_call=t, span_id=f"s{i}"))
    assert any(i["type"] == LoopType.STRUCTURAL for i in guard_loose.check())  # 0.33 >= 0.30: clusters

    guard_strict = LoopGuard(
        velocity_window_seconds=30, velocity_call_limit=10,
        structural_call_limit=3, tool_fuzzy_similarity_threshold=0.70,
    )
    for i, t in enumerate(tools):
        guard_strict.record(_event("agent1", seconds_offset=i * 10, tool_call=t, span_id=f"s{i}"))
    assert all(i["type"] != LoopType.STRUCTURAL for i in guard_strict.check())  # 0.33 < 0.70: stays separate
