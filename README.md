# savi-loop-guard

A zero-dependency Python library that detects when an AI agent is stuck in a
loop: calling the same tool over and over, or firing calls far faster than
any real workflow would. Drop it into your own agent code. No account, no
API key, no network call, ever.

Built by [SAVI](https://datagras.com) as a standalone, dependency-free
package, so you can detect these patterns in your own agent code without
an account, an API key, or a dependency on SAVI's platform.

---

## Install

```bash
pip install savi-loop-guard
```

No dependencies. Nothing else gets installed alongside it.

---

## Quick start

Record each call as your agent makes it, then check for loops whenever you
want (after every call, on a timer, whatever fits your loop):

```python
from loop_guard import LoopGuard, CallEvent
from datetime import datetime, timezone

guard = LoopGuard()

guard.record(CallEvent(
    span_id="call_1",
    agent_id="doc-extractor",
    timestamp=datetime.now(timezone.utc),
    tool_call="search_web",
))

issues = guard.check()
for issue in issues:
    print(issue["type"], issue["agent_id"])
```

An `issue` looks like:

```python
{"type": LoopType.VELOCITY, "agent_id": "doc-extractor", "elapsed_s": 12.4, "call_count": 6}
# or
{"type": LoopType.STRUCTURAL, "agent_id": "doc-extractor",
 "tool_call": "search_web", "tool_variants": ["search_web", "search_web_v2"], "call_count": 7}
```

### Prevent the call instead of just observing it

`check_before_call()` records the event and raises immediately if it would
trip a threshold, for callers who want to stop the loop rather than find
out about it afterwards:

```python
from loop_guard import LoopGuard, CallEvent, LoopDetected

guard = LoopGuard()

try:
    guard.check_before_call(event)
except LoopDetected as e:
    print(f"Blocked: {e.loop_type}")  # "velocity_loop" or "structural_loop"
    print(e.details)                  # the same dict check() would have returned
```

---

## What it detects

Two independent checks:

- **Velocity loop**: more than 5 calls from the same `agent_id` within a
  30-second window.
- **Structural loop**: the same tool called more than 5 times, with fuzzy
  matching so a broken agent can't dodge detection by alternating between
  near-identical tool names (`search_web` vs `search_web_v2` vs `web_search`
  count as the same tool if their name tokens overlap enough).

All four numbers are configurable:

```python
guard = LoopGuard(
    velocity_window_seconds=30,
    velocity_call_limit=5,
    structural_call_limit=5,
    tool_fuzzy_similarity_threshold=0.70,
)
```

---

## How this compares

A few other standalone Python packages exist for this: `agent-loop-detector`,
`agent-loop-guard`, `agentguard-kit`. All of them, like `savi-loop-guard`'s
`record()`/`check()` API, are post-hoc/observational; they analyze calls
after they happen. `savi-loop-guard` adds `check_before_call()` on top for
callers who want to prevent the call rather than just observe it, which none
of those currently offer.

---

## Known limitations

`LoopGuard` keeps every recorded event in memory for the life of the
instance; nothing is ever pruned automatically. That's deliberate:
structural-loop detection is a *total* call count with no time bound by
design (a tool called 6 times over 3 hours is still a loop, not just a
tool called 6 times in 30 seconds), so silently dropping "old" events
would blind it to exactly the slow, steady loops it exists to catch.

In practice this means: for a short-lived task, a single `LoopGuard()`
is fine as-is. For a long-running process, create a fresh `LoopGuard()`
per logical unit of work (e.g. per agent run) rather than holding one
open indefinitely, so memory doesn't grow without bound.

---

## License

MIT. See [LICENSE](LICENSE).
