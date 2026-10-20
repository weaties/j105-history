# Contributing

Thanks for helping build the J/105 class's results history. Questions are welcome too: open an issue.

## Ways to help

- **Report a source:** a website with J/105 results we don't have yet (fleet sites, club
  archives, old regatta pages). Open an issue with links.
- **Report a mistake:** include the event, the official results link, and what's wrong.
- **Identity:** tell us when two sail numbers are the same hull, or one number is two boats,
  with evidence (event links, boat names, skippers).
- **Code:** a new source, a parser fix, or site improvements.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

- Python 3.12, line length 100, `ruff` for lint and format.
- All HTTP goes through `src/j105/http.py`: be polite to every server (≤4 concurrent requests,
  backoff) and cache raw replies under `data/raw/cache/`.
- New sources follow `.claude/skills/add-source/SKILL.md`, including a terms-of-use check.
- Parser tests use small synthetic pages, not copies of third-party pages.
- Never hand-edit results in `data/raw/*_events.json`. Fix the parser, or record a reviewed
  correction (an alias, nickname or opt-out) with a reason.
- Follow the privacy rules in `README.md`: no membership numbers, contact details or crew lists.

## Commits and pull requests

Small, focused commits with clear messages. When a collector run changes data, include the
new counts in the commit message.
