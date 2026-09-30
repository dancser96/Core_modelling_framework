# retail.core_modelling

A config-driven modelling framework. It makes low- and medium-value use cases deliverable in
weeks, and keeps a large estate of live models maintainable. Package: `core_modelling`.

**Status:** Phase 2 has started. The package is a skeleton; the working crunch implementation is
in `legacy/propensity_crunch/` (reference only).

## Start here
- New machine: [Windows 11 / WSL2](docs/guides/setup_windows_wsl2.md) or
  [macOS](docs/guides/setup_macos.md).
- How we work with Claude Code: [workflow](docs/guides/claude_code_workflow.md) and
  [skills & agents](docs/guides/skills_and_agents.md).
- What this is and why: [project context](docs/context/project.md) →
  [architecture](docs/architecture.md) → [components](docs/components/README.md).
- Where things stand: [UPDATES](docs/UPDATES.md).
- Rules for code: [CLAUDE.md](CLAUDE.md). They apply to humans too.

## Quick start (after machine setup)
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
