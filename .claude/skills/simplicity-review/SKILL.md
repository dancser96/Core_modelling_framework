---
name: simplicity-review
description: Review a code diff or new code against this repo's code-light rules (CLAUDE.md §1) before presenting it to the user. Use this whenever you have written or changed Python code in src/, tests/ or notebooks, before saying a task is done, when the user asks "is this simple enough", "review this", "can this be smaller", or whenever a change feels large, abstract or clever.
---

# Simplicity review

The user reviews every line. Code that is hard to read wastes their time and becomes the
unmaintainable pipeline this repo exists to prevent. Review as if you were the reviewer, not the
author.

## Steps

1. Get the diff (`git diff` / `git diff --staged`) and read it top to bottom.
2. Check every item below. For each finding, record: file:line, rule, and the concrete simpler
   alternative.
3. Classify each finding as **blocking** (violates a rule) or **suggestion** (taste). Fix the
   blocking ones, or justify each explicitly to the user.

## Checklist

- [ ] **Needed now?** Is every function, parameter and option used by the current task? Remove
      speculative ones.
- [ ] **Functions over classes.** Is every class justified by state and behaviour that travel
      together (Pydantic model, dataclass, scikit-learn-compatible wrapper, small `Protocol`)? Any
      inheritance beyond a library base class or one shallow level, and is it explained? Any ABC
      hierarchy, decorator registry, factory or manager class? (`CLAUDE.md` §1 rule 2)
- [ ] **Size.** Functions longer than ~50 lines, or modules longer than ~300 lines? Split them by
      responsibility.
- [ ] **Names.** Does each name say what it does (`verb_noun`)? Vague names (`process`, `handle`,
      `data2`, `utils`)?
- [ ] **Types and docstrings.** Does every function (public, private, test) have type hints and a
      docstring, and does every module open with a docstring that explains what it is for?
      (`CLAUDE.md` §1 rules 9–10; ruff and `tests/test_code_rules.py` catch most of it)
- [ ] **One job each.** Any function mixing IO, computation and reporting?
- [ ] **Duplication vs abstraction.** Copy-paste twice is fine. Abstracting after one use is not.
- [ ] **Errors.** Any `except Exception` / bare `except` / silent fallback? Errors must be loud
      and specific.
- [ ] **Comments.** Do they explain *why*? No commented-out code, dead code or unlogged TODOs.
- [ ] **Library first.** Is anything hand-rolled that pandas / PySpark / sklearn already does?
- [ ] **Dependencies.** Any new import outside `requirements.txt`? That needs approval.
- [ ] **Notebooks.** Any function definitions or logic in the framework's notebooks? Move them to
      the package. Does any production path depend on notebook code?
- [ ] **Failure policy.** Is anything skipped by catching an error? Only views declared incompatible
      up front may be skipped (`CLAUDE.md` §1 rule 8).
- [ ] **Generality.** Any binary-only assumption leaking into shared shapes (column names, schemas)?
      Conversely, any generic machinery built for a single task?

## Output format

```
Simplicity review — <n> blocking, <m> suggestions
BLOCKING
- src/…/x.py:42 — rule — simpler alternative
SUGGESTIONS
- …
Verdict: ready / needs changes
```
