# Project agent guidance

## Git workflow

- Commit and push directly to `main` by default for this repository.
- Use a feature branch or pull request only when the user explicitly requests
  one.

## Find and keep the DVD Maker skill current

- For DVD authoring work, read
  `~/src/agent-skills-public/dvdmaker-cli/SKILL.md` before acting, even when the
  skill is not listed in the active session registry.
- When CLI options, defaults, setup steps, authoring behavior, output layout, or
  verification procedures change, update
  `~/src/agent-skills-public/dvdmaker-cli/SKILL.md` in the same task.
- Keep the skill concise and consistent with `python -m src.main --help` and
  `README.md`.
- Validate skill changes with the `skill-creator` `quick_validate.py` script. If
  the skill or validator is unavailable, say so in the handoff.

## Verify repository changes

- Add focused regression tests for behavior changes and run `make check` before
  pushing.
- Keep generated media in the ignored `output/` directory and never commit DVD
  trees, ISO images, caches, or source media.
