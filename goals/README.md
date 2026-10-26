# Goals schema

Each goal is one YAML item in goals.md. Scheduled workers parse these.

```yaml
- id: G-001                # stable, never reused
  goal: ""                 # one sentence
  why: ""                  # why it matters to Jo
  metric: ""               # what gets measured
  target: ""               # a number or a clear end state
  deadline: YYYY-MM-DD
  status: not_started      # not_started | on_track | at_risk | behind | done | dropped
  owner: Jo
  source: jo               # jo = Jo set it; inferred = proposed, needs Jo's OK
  business: ""             # a file in businesses/
  last_checked: YYYY-MM-DD
  notes: ""
```

Only Jo changes source, target or deadline. The evening worker updates status, last_checked and notes.
