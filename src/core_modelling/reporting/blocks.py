"""The blocks every report shares: the choices table, headline numbers, warnings, "not
available" lines and the appendix.

`CHOICES` is plain data, one row per decision a report states up front (D-032): its label, the
dotted config path its value is read from and the alternatives. When to move to one is the config
template's (`conf/base/TEMPLATE.yml`) and the component docs' to explain, not the report's. A row
without a path (a count, a hash, a cap) gets its value from the stage that computed it. Each
function returns what `render_report` takes as a block (`appendix` a dict of them by view key).
"""

from collections.abc import Callable
from html import escape

import pandas as pd
from pandas.io.formats.style import Styler

from core_modelling.config.identities import short
from core_modelling.config.replay import dump_resolved, get_at
from core_modelling.config.schema import UseCaseConfig
from core_modelling.reporting.html import paragraph, preformatted, style_table

STAT_STYLE = "display: inline-block; margin: 4px 16px 4px 0"  # a headline figure
VALUE_STYLE = "display: block; font-weight: 600"  # its value on one line, its label below
STEP_THRESHOLDS = "each threshold a config leaf; a step left out of the mapping is skipped"

CHOICES: dict[str, dict] = {
    "automation_level": {
        "label": "Automation level",
        "path": "automation_level",
        "alternatives": "autonomous | assisted",
    },
    "task": {
        "label": "Task",
        "path": "task",
        "alternatives": "binary (0/1 outcome) | regression (amount)",
    },
    "decision": {
        "label": "Decision",
        "path": "decision.type",
        "alternatives": "top_n | threshold | ranking | probability",
    },
    "metric": {
        "label": "Metric derived from the decision",
        "path": None,
        "alternatives": "decision.metric overrides it with a FLAML metric name",
    },
    "period": {
        "label": "Period (unit of analysis)",
        "path": "time.period",
        "alternatives": "month | week | day",
    },
    "observation_window": {
        "label": "Observation window",
        "path": "time.observation_window",
        "alternatives": "any run of periods t1 … tk",
    },
    "target_window": {
        "label": "Target window w",
        "path": "time.target_window",
        "alternatives": "w periods, t+1 … t+w",
    },
    "validation_period": {
        "label": "Validation period (shown, never used)",
        "path": "time.validation_period",
        "alternatives": "any period at least w periods after the window's last",
    },
    "eligibility_analysis": {
        "label": "Eligibility: analysis steps",
        "path": "data.eligibility.analysis",
        "alternatives": "[] (every row of the spine reaches EDA) | define and filter steps",
    },
    "eligibility_modelling": {
        "label": "Eligibility: modelling steps",
        "path": "data.eligibility.modelling",
        "alternatives": "[] (every row that reaches EDA is modelled) | filter steps",
    },
    "candidate_count": {
        "label": "Candidate features",
        "path": None,
        "alternatives": "narrow features.candidates",
    },
    "candidate_patterns": {
        "label": "Candidate patterns",
        "path": "features.candidates",
        "alternatives": "glob patterns over the feature sources' columns, include and exclude",
    },
    "kinds_summary": {
        "label": "Kinds detected",
        "path": None,
        "alternatives": "numeric | categorical per column",
    },
    "kind_overrides": {
        "label": "Kind overrides",
        "path": "features.kinds",
        "alternatives": "{column: numeric | categorical}",
    },
    "snapshot": {
        "label": "Snapshot period",
        "path": "eda.snapshot",
        "alternatives": "last | a period inside the window",
    },
    "bins": {
        "label": "Quantile bins per numeric (eda.bins)",
        "path": "eda.bins",
        "alternatives": "an integer of at least 2 | null",
    },
    "key_features": {
        "label": "Key-feature rule",
        "path": "eda.key_features",
        "alternatives": "top_n 0 deep-dives only the listed ones; include lists candidates "
        "always deep-dived; max_correlation 1 skips none",
    },
    "slices": {
        "label": "Decision slices",
        "path": "evaluation.slices",
        "alternatives": "any shares in (0, 1] and list sizes",
    },
    "strata": {
        "label": "Strata variables",
        "path": "strata.variables",
        "alternatives": "any categorical columns",
    },
    "pairwise_cap": {
        "label": "Pairwise association cap (rows)",
        "path": None,
        "alternatives": "fixed by the framework",
    },
    "replayed_to": {
        "label": "Audit log replayed to",
        "path": None,
        "alternatives": "an earlier entry reproduces an earlier run",
    },
    "config_hash": {
        "label": "Config hash",
        "path": None,
        "alternatives": "-",
    },
    "data_definition_hash": {
        "label": "Data-definition hash",
        "path": None,
        "alternatives": "-",
    },
    "min_events": {
        "label": "Support rule (strata.min_events)",
        "path": "strata.min_events",
        "alternatives": "any count of at least 1; a period below it is greyed, still tested",
    },
    "quality": {
        "label": "Quality thresholds",
        "path": "feature_checks.quality",
        "alternatives": STEP_THRESHOLDS,
    },
    "leakage": {
        "label": "Leakage thresholds",
        "path": "feature_checks.leakage",
        "alternatives": STEP_THRESHOLDS,
    },
    "time_alignment": {
        "label": "Time-alignment thresholds",
        "path": "feature_checks.time_alignment",
        "alternatives": STEP_THRESHOLDS,
    },
    "stability": {
        "label": "Stability thresholds",
        "path": "feature_checks.stability",
        "alternatives": STEP_THRESHOLDS,
    },
    "redundancy": {
        "label": "Redundancy thresholds",
        "path": "feature_checks.redundancy",
        "alternatives": STEP_THRESHOLDS,
    },
    "skipped_steps": {
        "label": "Steps skipped",
        "path": None,
        "alternatives": "list the step in feature_checks; the section left out runs all five",
    },
    "compared_periods": {
        "label": "Compared periods",
        "path": None,
        "alternatives": "set by the window and the validation period; never the validation period",
    },
}


def _show(value: object) -> str:
    """A config value as readable text: lists one item per line, dicts as `key: value` pairs, a
    mapping inside a mapping in braces."""
    if value is None:
        return "null"
    if isinstance(value, dict):
        shown = {key: f"{{{_show(item)}}}" if isinstance(item, dict) else _show(item)
                 for key, item in value.items() if item is not None}  # fmt: skip
        pairs = [f"{key}: {item}" for key, item in shown.items()]
        return ", ".join(pairs) or "none"
    if isinstance(value, list):
        return "\n".join(_show(item) for item in value) or "none"
    return str(value)


def _choice_value(name: str, values: dict[str, object], raw: dict) -> object:
    """A choice's value: the caller's, else the config's at its path; no path, no value fails."""
    if name in values:
        return values[name]
    choice = CHOICES[name]
    if choice["path"] is None:
        raise ValueError(f"choice {choice['label']!r} has no config path: pass its value")
    return get_at(raw, choice["path"])


def choices_block(resolved: UseCaseConfig, names: list[str], values: dict[str, object]) -> Styler:
    """The choices table: what was chosen, its value and the alternatives (D-032).

    `names` are the `CHOICES` rows in the report's order; `values` holds the value of each row
    the stage computed (every row without a config path), a value for a row not shown fails.
    When to move to an alternative is the config template's and the component docs' to explain.
    """
    unshown = [name for name in values if name not in names]
    if unshown:
        raise ValueError(f"choices_block: values for rows not in names: {unshown}")
    raw = resolved.model_dump(mode="json")
    rows = [
        {
            "Choice": CHOICES[name]["label"],
            "Value": _show(_choice_value(name, values, raw)),
            "Alternatives": CHOICES[name]["alternatives"],
        }
        for name in names
    ]
    styler = style_table(pd.DataFrame(rows))
    return styler.set_properties(subset=["Value"], **{"white-space": "pre-line"})


def identity_values(meta: dict) -> dict[str, object]:
    """The identity rows' values every report shows, from a stage's meta: the audit-log entry
    replayed to and the short config and data-definition hashes."""
    return {
        "replayed_to": meta["replayed_to"],
        "config_hash": short(meta["config_hash"]),
        "data_definition_hash": short(meta["data_definition_hash"]),
    }


def _headline_text(value: object, number_format: str | Callable[[float], str]) -> str:
    """A headline value in its format; `n/a` for a missing value (None, as a stage's meta stores
    it, or NaN)."""
    if value is None or pd.isna(value):
        return "n/a"
    return number_format(value) if callable(number_format) else number_format.format(value)


def headline(numbers: dict[str, object], formats: dict[str, str | Callable[[float], str]]) -> str:
    """The headline numbers as a row of labelled figures, each name read with spaces for its
    underscores.

    `formats` gives each number the format its table column uses (`formats.format_of`'s, the
    task's estimate format for a rate or a mean, the share format for a share), so the headline
    reads like the tables below it; a number without a format fails.
    """
    unformatted = [name for name in numbers if name not in formats]
    if unformatted:
        raise ValueError(f"headline: no format for {unformatted}: pass one per number")
    # Inline layout, no colours: a notebook shows the block without the report's CSS, on a light
    # or a dark page.
    cells = "".join(
        f'<div class="stat" style="{STAT_STYLE}">'
        f'<span class="value" style="{VALUE_STYLE}">'
        f"{escape(_headline_text(value, formats[name]))}</span>"
        f'<span class="label">{escape(name.replace("_", " "))}</span></div>'
        for name, value in numbers.items()
    )
    return f'<div class="headline">{cells}</div>'


def warnings_block(items: list[str]) -> str:
    """The warnings as a numbered list; 'No warnings.' when there are none."""
    if not items:
        return paragraph("No warnings.")
    return "<ol>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ol>"


def not_available(reason: str) -> str:
    """A view declared incompatible up front as one line, "Not available: <reason>." (D-035)."""
    return paragraph(f"Not available: {reason}.")


def appendix(
    resolved: UseCaseConfig, decisions: pd.DataFrame, seconds: dict[str, float], caption: str
) -> dict[str, str | Styler]:
    """The appendix every report holds, by view key: the resolved config, the audit log's
    entries (`show_decisions`' table) and the seconds per phase at one decimal under `caption`;
    a stage adds its own parts beside them."""
    timings = pd.DataFrame({"phase": list(seconds), "seconds": list(seconds.values())})
    return {
        "resolved_config": preformatted(dump_resolved(resolved)),
        "decisions": style_table(decisions, caption="The audit log's entries, replayed in order"),
        "timings": style_table(timings, {"seconds": "{:.1f}"}, caption=caption),
    }
