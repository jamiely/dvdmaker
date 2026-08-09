# Project agent guidance

## Keep the DVD Maker skill current

- When CLI options, defaults, setup steps, authoring behavior, output layout, or
  verification procedures change, update
  `~/.codex/skills/dvdmaker-cli/SKILL.md` in the same task when that skill is
  available.
- Keep the skill concise and consistent with `python -m src.main --help` and
  `README.md`.
- Validate skill changes with the `skill-creator` `quick_validate.py` script. If
  the skill or validator is unavailable, say so in the handoff.

## Verify repository changes

- Add focused regression tests for behavior changes and run `make check` before
  pushing.
- Keep generated media in the ignored `output/` directory and never commit DVD
  trees, ISO images, caches, or source media.
