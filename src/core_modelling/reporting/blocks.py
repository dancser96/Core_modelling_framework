"""The blocks every report shares: the choices table, headline numbers, warnings, reading notes.

`CHOICES` is plain data, one row per decision a report states up front (D-032): its label, the
dotted config path its value is read from and the alternatives. When to move to one is the config
template's (`conf/base/TEMPLATE.yml`) and the component docs' to explain, not the report's. A row
without a path (a count, a hash, a cap) gets its value from the stage that computed it. Each
function returns what `render_report` takes as a block.
"""

from html import escape
from numbers import Integral, Real

import numpy as np
import pandas as pd
from pandas.io.formats.style import Styler

from core_modelling.config.replay import get_at
from core_modelling.config.schema import UseCaseConfig
from core_modelling.reporting.html import paragraph, style_table

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


def _choice_value(choice: dict, raw: dict) -> object:
    """A choice's value: the caller's, else the config's at its path; no path, no value fails."""
    if "value" in choice:
        return choice["value"]
    if choice["path"] is None:
        raise ValueError(f"choice {choice['label']!r} has no config path: pass its `value`")
    return get_at(raw, choice["path"])


def choices_block(resolved: UseCaseConfig, choices: list[dict]) -> Styler:
    """The choices table: what was chosen, its value and the alternatives (D-032).

    Each choice is a `CHOICES` row, with a `value` key added where the stage computed it. When to
    move to an alternative is the config template's and the component docs' to explain.
    """
    raw = resolved.model_dump(mode="json")
    rows = [
        {
            "Choice": choice["label"],
            "Value": _show(_choice_value(choice, raw)),
            "Alternatives": choice["alternatives"],
        }
        for choice in choices
    ]
    styler = style_table(pd.DataFrame(rows))
    return styler.set_properties(subset=["Value"], **{"white-space": "pre-line"})


def _format_number(value: object) -> str:
    """A headline value as text: thousands separators for counts, four digits for fractions,
    `n/a` for a missing value (None, as the stage's meta stores it, or NaN)."""
    if value is None or (isinstance(value, Real) and np.isnan(value)):
        return "n/a"
    # Integral and Real take numpy's scalars too, which pandas aggregates return.
    if isinstance(value, bool | np.bool_) or not isinstance(value, Real):
        return str(value)
    if isinstance(value, Integral) or abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.4g}"


def headline(numbers: dict) -> str:
    """The headline numbers as a row of labelled figures."""
    # Inline layout, no colours: a notebook shows the block without the report's CSS, on a light
    # or a dark page.
    cells = "".join(
        f'<div class="stat" style="{STAT_STYLE}">'
        f'<span class="value" style="{VALUE_STYLE}">{escape(_format_number(value))}</span>'
        f'<span class="label">{escape(str(label))}</span></div>'
        for label, value in numbers.items()
    )
    return f'<div class="headline">{cells}</div>'


def warnings_block(items: list[str]) -> str:
    """The warnings as a numbered list; 'No warnings.' when there are none."""
    if not items:
        return paragraph("No warnings.")
    return "<ol>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ol>"


def how_to_read(
    bins: int | None, estimate_noun: str, support_name: str, group_support: int
) -> list[str]:
    """The five how-to-read notes of a report that shows concordance, lift and intervals
    (reporting.md req. 8).

    `bins` is `eda.bins`; with None every statistic is exact and the binning sentence is left
    out. `estimate_noun` and `support_name` are the task's words for its estimate (`rate`,
    `mean`) and its support; `group_support` is the support a key feature's group needs.
    """
    concordance = (
        "Concordance says how well a feature orders clients by the target: 0.5 is no better "
        "than chance, 1 a perfect ordering, whichever way round (the direction column says "
        "which). For a yes/no target it is the AUC of that feature alone."
    )
    if bins is not None:
        concordance += (
            f" Numerics are read on {bins} quantile bins; pairs inside one bin count half."
        )
    notes = [
        concordance,
        f"Lift is a group's {estimate_noun} divided by the snapshot's base {estimate_noun}: 1 is "
        "the base, 2 twice the base.",
        "Intervals are 95%: Wilson for a rate, Student t for a mean. On charts they are the "
        "error bars.",
        f"Grey means too little support, still shown: fewer than strata.min_events "
        f"{support_name} ({group_support} in a key feature's groups). Read the interval, not "
        "the point.",
        "null is the clients without a value: their own bar or level, always last.",
    ]
    return [paragraph(note) for note in notes]
