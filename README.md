# core_modelling

The unit's standard way to build, ship and maintain models: a versioned, config-driven Python library
used through guided notebooks, a CLI and a Python API. A use case goes from data to a monitored
production model in days to weeks (≈ 3 days on the hands-off profile, ≈ 3 weeks on the thorough
one), with one standard for correctness, reproducibility and maintainability across the whole
lifecycle. Package: `core_modelling` (the repo name `retail.core_modelling` may change; the framework
is domain-agnostic).

**Status:** Phase 2, design baseline done. The package is a skeleton; the working crunch
implementation is in `legacy/propensity_crunch/` (reference only).

## Start here
- New machine: [Windows 11 / WSL2](docs/guides/setup_windows_wsl2.md) or
  [macOS](docs/guides/setup_macos.md).
- **Reading order and which doc covers which stage: [docs guide](docs/README.md).**
- What this is and why: [project context](docs/context/project.md) →
  [architecture](docs/architecture.md) → [components](docs/components/README.md);
  vocabulary in the [glossary](docs/glossary.md).
- Where things stand: [UPDATES](docs/UPDATES.md). What's next and what's undecided:
  [roadmap](docs/roadmap.md). Why things are the way they are: [decisions](docs/decisions.md).
  For the daily sync with the Lead DS: [sync page](worknotes/sync.md).
- How we work with Claude Code: [workflow](docs/guides/claude_code_workflow.md) and
  [skills & agents](docs/guides/skills_and_agents.md).
- Rules for code and docs: [CLAUDE.md](CLAUDE.md). They apply to humans too.

## Quick start (after machine setup)
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
