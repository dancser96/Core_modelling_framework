"""Code rules that ruff can't check: every function, private ones included, has a docstring."""

import ast
from pathlib import Path

CODE_DIRS = [Path("src/core_modelling"), Path("synthetic/src/synthetic"), Path("tests")]


def test_every_function_has_a_docstring() -> None:
    """Ruff's docstring rules skip private functions; CLAUDE.md §1 rule 10 covers them too."""
    root = Path(__file__).resolve().parents[1]
    missing = [
        f"{path.relative_to(root)}:{node.lineno} {node.name}"
        for code_dir in CODE_DIRS
        for path in sorted((root / code_dir).rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not ast.get_docstring(node)
    ]
    assert not missing, "functions without a docstring:\n" + "\n".join(missing)


def test_framework_code_never_reads_trap_names() -> None:
    """The synthetic mart's planted columns carry `_trap_<kind>` names so people and tests can tell
    them apart; the framework must find them from their statistics alone, since real data has no
    such names."""
    root = Path(__file__).resolve().parents[1]
    offenders = [
        str(path.relative_to(root))
        for path in sorted((root / "src/core_modelling").rglob("*.py"))
        if "_trap_" in path.read_text()
    ]
    assert not offenders, "framework code mentions trap names:\n" + "\n".join(offenders)
