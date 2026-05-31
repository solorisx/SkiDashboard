# SlopeLog — Internal Technical Documentation

Confluence-style engineering reference for SlopeLog internals. **Local only:**
this `docs/` tree is not served by the web app (it lives outside `templates/`
and `static/`, has no URL route) and is intended for developers reading the
repository. It assumes high technical fluency — it is **not** user-facing
documentation.

Each document references the implementing commit(s) and concrete code paths so
it can be cross-checked against the source.

## Index

| Document | Topic | Implementing commit |
|----------|-------|---------------------|
| [`summer-activities.md`](./summer-activities.md) | Manual summer-activity tracking & season-pass costing (summer vs winter days) | `d292e38` |

## Conventions

* Reference code as `path/to/file.py` and, where helpful, symbol names.
* Cite the commit (short SHA + subject) that introduced or last materially
  changed the behaviour being described.
* Keep these docs in sync with `CLAUDE.md` (the agent/developer quick-reference
  at the repo root) when models, routes or workflows change.
