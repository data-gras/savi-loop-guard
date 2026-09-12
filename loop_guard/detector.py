"""
loop_guard/detector.py, the detection logic itself.

Two independent checks, run per agent_id over that agent's own call history:

  Velocity loop:   more than `velocity_call_limit` calls from the same
                    agent_id within a `velocity_window_seconds` sliding
                    window.
  Structural loop: the same tool (or a fuzzy-matched variant, see
                    _tool_tokens/_jaccard/_canonical_tool below) called more
                    than `structural_call_limit` times total for one
                    agent_id.

record() and check() are passive - they never pause or block anything.
check_before_call() is a thin convenience wrapper for callers who want to
prevent a call rather than just observe it afterwards: record()+check()
in sequence, with a raise instead of a silent return.

A LoopGuard instance keeps every recorded event for its own lifetime,
nothing is pruned, since structural-loop detection is a total count with
no time bound by design - a slow, steady repeat-tool-call loop spread
over hours should still trip it. Create a fresh LoopGuard per logical
unit of work (e.g. per agent run) if unbounded memory growth matters for
your use case.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class LoopType(str, Enum):
    VELOCITY   = "velocity_loop"
    STRUCTURAL = "structural_loop"


class LoopDetected(Exception):
    """Raised by check_before_call() when recording an event would trip
    either the velocity or structural threshold for its agent_id."""

    def __init__(self, loop_type: str, details: dict):
        self.loop_type = loop_type
        self.details = details
        super().__init__(f"Loop detected: {loop_type} - {details}")


@dataclass(slots=True)
class CallEvent:
    """One agent/tool call. Nothing here requires a SAVI account or reads
    from SAVI in any way.

    Only agent_id and timestamp are actually consumed by the detection
    checks; the rest exist for the call-tree (children) that record()
    builds, even though check() doesn't walk it today.

    `timestamp` must be timezone-aware (e.g. datetime.now(timezone.utc)).
    Mixing a naive and an aware timestamp across events for the same
    agent_id raises TypeError rather than silently guessing a timezone.
    """
    span_id: str
    agent_id: Optional[str]
    timestamp: datetime
    parent_span_id: Optional[str] = None
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    tool_call: Optional[str] = None
    children: list = field(default_factory=list)


def _tool_tokens(tool_name: str) -> "set[str]":
    """Split a tool name into tokens for fuzzy matching.

    Splits on underscores and strips version suffixes (v1, v2, ...).
    Example: 'search_web_v2' -> {'search', 'web'}
    """
    parts = tool_name.lower().split("_")
    return {p for p in parts if p and not re.fullmatch(r"v\d+", p)}


def _jaccard(set_a: set, set_b: set) -> float:
    """Token-level Jaccard similarity."""
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def _canonical_tool(tool_name: str, seen: "dict[str, set]", threshold: float) -> str:
    """Return the canonical representative for tool_name given already-seen
    tools - clusters near-duplicate tool names (Jaccard >= threshold)
    together so a broken agent can't dodge detection just by using a
    slightly different tool variant on each call."""
    tokens = _tool_tokens(tool_name)
    for canonical, canon_tokens in seen.items():
        if _jaccard(tokens, canon_tokens) >= threshold:
            return canonical
    seen[tool_name] = tokens
    return tool_name


class LoopGuard:
    def __init__(
        self,
        velocity_window_seconds: float = 30,
        velocity_call_limit: int = 5,
        structural_call_limit: int = 5,
        tool_fuzzy_similarity_threshold: float = 0.70,
    ):
        self.VELOCITY_WINDOW_SECS  = velocity_window_seconds
        self.VELOCITY_CALL_LIMIT   = velocity_call_limit
        self.STRUCTURAL_CALL_LIMIT = structural_call_limit
        self.FUZZY_THRESHOLD       = tool_fuzzy_similarity_threshold
        self._events:  "dict[str, CallEvent]"      = {}
        self._orphans: "dict[str, list[CallEvent]]" = defaultdict(list)

    def record(self, event: CallEvent) -> None:
        """Store `event` for later loop detection and link it into the
        call tree by parent_span_id (out-of-order arrival is handled - an
        event can arrive before its parent and gets attached once the
        parent shows up). Never raises, never blocks - purely bookkeeping."""
        self._events[event.span_id] = event
        if event.parent_span_id and event.parent_span_id in self._events:
            self._events[event.parent_span_id].children.append(event)
        elif event.parent_span_id:
            self._orphans[event.parent_span_id].append(event)
        for orphan in self._orphans.pop(event.span_id, []):
            event.children.append(orphan)

    def check(self) -> "list[dict]":
        """Run both detectors (velocity, structural) over every event
        recorded so far, grouped and evaluated independently per agent_id.
        Returns a list of issue dicts - empty if nothing trips. Velocity
        issues carry {type, agent_id, elapsed_s, call_count}; structural
        issues carry {type, agent_id, tool_call, tool_variants, call_count}.
        Safe to call repeatedly - it re-evaluates from scratch each time
        rather than tracking incremental state."""
        issues: "list[dict]" = []
        by_agent: "dict[str, list[CallEvent]]" = defaultdict(list)
        for e in self._events.values():
            if e.agent_id:
                by_agent[e.agent_id].append(e)

        for agent_id, events in by_agent.items():
            events.sort(key=lambda e: e.timestamp)

            # ── Velocity loop (time-window burst) ──────────────────────────
            for i in range(len(events) - self.VELOCITY_CALL_LIMIT):
                window  = events[i : i + self.VELOCITY_CALL_LIMIT + 1]
                elapsed = (window[-1].timestamp - window[0].timestamp).total_seconds()
                if elapsed <= self.VELOCITY_WINDOW_SECS:
                    issues.append({
                        "type": LoopType.VELOCITY,
                        "agent_id": agent_id,
                        "elapsed_s": elapsed,
                        "call_count": len(window),
                    })
                    break

            # ── Structural loop (repeated tool calls, fuzzy-matched) ───────
            seen_canonicals: "dict[str, set]" = {}
            tool_counts: "dict[str, int]" = defaultdict(int)
            tool_canonical_map: "dict[str, str]" = {}

            for e in events:
                if not e.tool_call:
                    continue
                canonical = _canonical_tool(e.tool_call, seen_canonicals, self.FUZZY_THRESHOLD)
                tool_counts[canonical] += 1
                tool_canonical_map[e.tool_call] = canonical

            for canonical, count in tool_counts.items():
                if count > self.STRUCTURAL_CALL_LIMIT:
                    members = sorted({
                        orig for orig, can in tool_canonical_map.items()
                        if can == canonical
                    })
                    issues.append({
                        "type": LoopType.STRUCTURAL,
                        "agent_id": agent_id,
                        "tool_call": canonical,
                        "tool_variants": members,
                        "call_count": count,
                    })

        return issues

    def check_before_call(self, event: CallEvent) -> None:
        """Record `event`, then raise LoopDetected if it would trip either
        threshold for its agent_id - a convenience for callers who want to
        prevent the call rather than just observe it after the fact. Not a
        separate detection engine: exactly the same record()+check() calls,
        with a raise instead of a silent return."""
        self.record(event)
        for issue in self.check():
            if issue["agent_id"] == event.agent_id:
                raise LoopDetected(issue["type"].value, issue)
