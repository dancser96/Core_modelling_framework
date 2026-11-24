"""The model card's page (reporting.md "The model card"): the card's facts as tables only.

`render_card` takes the card dict alone (`evaluation/card.py` builds it), so it renders a card
read back from `model_card.json`. Per section a table of its single facts and one table per list
of records, through the shared renderer without plotly.js: a small page with no script. This
module owns the card's `schema_version` and section order, which the builder imports (the lower
module), and the renderer refuses a card of another version.
"""

import json
import math

import pandas as pd
from pandas.io.formats.style import Styler

from core_modelling.reporting.formats import plain_number
from core_modelling.reporting.html import render_report, style_table

# 2: `data.rows_per_period` per period only, beside `data.rows_pooled` and
# `data.rows_validation_test_clients`; `details.framework_versions.card` is the version writing
# the card; `training.calibration_methods` holds the calibration table's `oof_loss`
CARD_SCHEMA_VERSION = 2
# The card's sections in order, after its `schema_version`; `evaluation/card.py` writes them.
CARD_SECTIONS = ("details", "intended_use", "data", "features", "training", "performance",
                 "considerations", "sign_off", "lifecycle")  # fmt: skip


def render_card(card: dict) -> str:
    """The card as one small self-contained page, tables only: per section in `CARD_SECTIONS`
    order a table of its single facts (a nested key dotted) and one table per list of records;
    the schema version opens the details. A card of another `schema_version` is refused."""
    if card.get("schema_version") != CARD_SCHEMA_VERSION:
        raise ValueError(
            f"the card has schema_version {card.get('schema_version')}; this renderer reads "
            f"version {CARD_SCHEMA_VERSION}: render it with the framework version that wrote it"
        )
    details = card["details"]
    title = f"Model card: {details['use_case']} {details['run_id']} on {details['entity']}"
    contents = {**card, "details": {"schema_version": card["schema_version"], **details}}
    sections = [
        (name.replace("_", " ").capitalize(), _section_blocks(contents[name]))
        for name in CARD_SECTIONS
    ]
    return render_report(title, sections, plotly=False)


def _section_blocks(content: dict | list) -> list:
    """One section's tables: a list of records is one table; a dict gives its single facts in
    one table, then each list of records in its own, captioned by its key; empty gives `none`."""
    if not content:
        return ["<p>none</p>"]
    if isinstance(content, list):
        return [_records_table(content, None)]
    facts, lists = _flatten(content, "")
    blocks = [_facts_table(facts)] if facts else []
    return blocks + [_records_table(records, key) for key, records in lists.items()]


def _flatten(content: dict, prefix: str) -> tuple[dict, dict[str, list[dict]]]:
    """A section's single facts by dotted key (a nested dict opened, an empty one kept as a
    value) and its lists of records by key."""
    facts, lists = {}, {}
    for key, value in content.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict) and value:
            inner_facts, inner_lists = _flatten(value, f"{name}.")
            facts |= inner_facts
            lists |= inner_lists
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            lists[name] = value
        else:
            facts[name] = value
    return facts, lists


def _cell(value: object) -> str:
    """One value as a table cell reads it: blank for None and NaN (a key a record lacks, a null
    number once in a frame), an integer as it is (a seed is no quantity), a float through
    `plain_number`, a list or mapping as compact JSON."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, bool | int | str):
        return str(value)
    if isinstance(value, float):
        return plain_number(value)
    return json.dumps(value)


def _facts_table(facts: dict) -> Styler:
    """Single facts as a two-column table (fact, value)."""
    frame = pd.DataFrame({"fact": list(facts), "value": [_cell(v) for v in facts.values()]})
    return style_table(frame)


def _records_table(records: list[dict], caption: str | None) -> Styler:
    """A list of records as a table, a column per key in first-seen order."""
    return style_table(pd.DataFrame(records).astype(object).map(_cell), caption=caption)
