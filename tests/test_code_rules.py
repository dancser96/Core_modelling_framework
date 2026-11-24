"""Code rules that ruff can't check: every function, private ones included, has a docstring;
the framework never reads a trap's name; notebooks are committed without outputs; a run folder
is read without Training's code or FLAML."""

import ast
import json
import subprocess
import sys
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


def test_notebooks_are_committed_without_outputs() -> None:
    """A notebook's outputs can hold data, a machine's name or a home path, so only
    `00_synthetic_data`, which shows synthetic data alone, keeps them (D-064,
    `notebooks/README.md`)."""
    root = Path(__file__).resolve().parents[1]
    with_outputs = [
        path.name
        for path in sorted((root / "notebooks").glob("*.ipynb"))
        if path.name != "00_synthetic_data.ipynb"
        and any(cell.get("outputs") for cell in json.loads(path.read_text())["cells"])
    ]
    assert not with_outputs, f"clear the outputs of {with_outputs} before committing"


def _imported_modules(path: Path) -> list[str]:
    """Every module a source file imports by name, `from x import y` as `x.y` and `x`."""
    names = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names += [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
    return names


def _offenders(paths: list[Path], package: str, allowed: set[str]) -> list[str]:
    """The files among `paths` that import from `package`, with what they import, beyond the
    `allowed` names."""
    root = Path(__file__).resolve().parents[1]
    found = []
    for path in paths:
        bad = [
            name
            for name in _imported_modules(path)
            if (name == package or name.startswith(f"{package}.")) and name not in allowed
        ]
        found += [f"{path.relative_to(root)}: {name}" for name in bad]
    return found


def test_a_run_folder_is_read_without_training_code() -> None:
    """Evaluation, reporting and the run folder's readers never import Training, and `run` only
    its stage function, so register, Inference and Monitoring can read a run folder alone;
    neither Evaluation nor Training imports EDA."""
    package = Path(__file__).resolve().parents[1] / "src/core_modelling"
    readers = [
        *sorted((package / "evaluation").rglob("*.py")),
        *sorted((package / "reporting").rglob("*.py")),
        package / "runs.py",
        package / "run_artifacts.py",
    ]
    training = {"core_modelling.training", "core_modelling.training.run_training"}
    offenders = _offenders(readers, "core_modelling.training", set())
    offenders += _offenders([package / "run.py"], "core_modelling.training", training)
    modellers = sorted((package / "evaluation").rglob("*.py"))
    modellers += sorted((package / "training").rglob("*.py"))
    offenders += _offenders(modellers, "core_modelling.eda", set())
    assert not offenders, "imports across the run folder's boundary:\n" + "\n".join(offenders)


def test_importing_evaluation_leaves_flaml_unimported() -> None:
    """Evaluation's import chain holds no FLAML, checked in a fresh interpreter (the package's
    compat shim runs first, as in any import of it)."""
    check = "import sys, core_modelling.evaluation; assert 'flaml' not in sys.modules"
    result = subprocess.run(  # noqa: S603  (this interpreter, a fixed command)
        [sys.executable, "-c", check], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
