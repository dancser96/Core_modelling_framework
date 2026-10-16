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
