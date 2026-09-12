---
name: Bug report
about: Something isn't detecting a loop, or is detecting one that isn't there
title: ""
labels: bug
---

**What happened**
A clear description of the incorrect behavior, a missed detection, a false
positive, a crash, or something else.

**Minimal repro**
The smallest `CallEvent` sequence (or code snippet) that reproduces it:

```python
from loop_guard import LoopGuard, CallEvent
# ...
```

**Expected vs. actual**
What `check()` (or `check_before_call()`) returned, and what you expected
instead.

**Environment**
- `savi-loop-guard` version:
- Python version:
- OS:
