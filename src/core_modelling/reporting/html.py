"""The report renderer and table styling: sections of blocks in, one self-contained HTML page out.

`render_report` renders a table of contents, one anchor per section and subsection, the theme's
CSS and plotly.js once (no CDN: the bank has no internet, CLAUDE.md §5). Each figure is a
fragment with its own div id and each table carries its own uuid, both counted up from one
counter so a report is reproducible byte for byte. The stage writes the page with its artifacts
(`artifacts.write_stage`'s `texts`), so a render error, which a Styler raises only when rendered,
leaves the previous run's folder. `style_table` is the one place a DataFrame becomes a Styler:
formats, lift colouring, greyed insufficient rows or cells, an in-cell bar, a caption.
"""

import itertools
import math
from collections.abc import Iterator
from html import escape

import pandas as pd
import plotly.graph_objects as go
from pandas.io.formats.style import Styler
from plotly.offline import get_plotlyjs

from core_modelling.reporting.theme import THEME

MAX_LIFT_COLOUR = 0.55  # the opacity of the strongest lift colour: text stays readable
MAX_HEADING_LEVEL = 6


def paragraph(text: str) -> str:
    """The text escaped into a `<p>`."""
    return f"<p>{escape(text)}</p>"


def preformatted(text: str) -> str:
    """The text escaped into a `<pre>`."""
    return f"<pre>{escape(text)}</pre>"


def figure_html(fig: go.Figure, div_id: str) -> str:
    """A figure as an HTML fragment without plotly.js, which the report embeds once.

    Plotly does not deduplicate a repeated `div_id`, so the caller generates unique ones.
    """
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config={"displaylogo": False, "responsive": True},
    )


def table_html(styler: Styler, uuid: str) -> str:
    """A Styler as an HTML fragment; the uuid keeps its CSS ids apart from the other tables'."""
    return styler.set_uuid(uuid).to_html()


def _lift_css(lift: float) -> str:
    """One cell's CSS for its lift, diverging around 1 (a lift of 2 or 1/2 is the full colour)."""
    if pd.isna(lift) or lift < 0:
        return ""
    colour = THEME["lift_high"] if lift >= 1 else THEME["lift_low"]
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    # A lift of 0 (no event in the group) is the strongest below-base reading: the full colour.
    opacity = MAX_LIFT_COLOUR * (1.0 if lift == 0 else min(abs(math.log2(lift)), 1.0))
    return f"background-color: rgba({red}, {green}, {blue}, {opacity:.2f})"


def _greyed_mask(df: pd.DataFrame, greyed: pd.Series | pd.DataFrame) -> pd.DataFrame:
    """The greyed flags as a boolean frame shaped like `df`: a Series greys whole rows."""
    if not greyed.index.equals(df.index):
        raise ValueError("greyed must share the table's index")
    if isinstance(greyed, pd.Series):
        mask = pd.DataFrame({column: greyed for column in df.columns})
    else:
        extra = [column for column in greyed.columns if column not in df.columns]
        if extra:
            raise ValueError(f"greyed has columns the table lacks: {extra}")
        mask = greyed.reindex(columns=df.columns, fill_value=False)
    # Through the nullable boolean: a missing flag is not greyed, without pandas' downcasting.
    return mask.astype("boolean").fillna(False).astype(bool)


def _cell_styles(
    df: pd.DataFrame, lift: pd.DataFrame | None, greyed: pd.Series | pd.DataFrame | None
) -> pd.DataFrame:
    """CSS per cell: lift colours first, then grey on top for the insufficient ones."""
    css = pd.DataFrame("", index=df.index, columns=df.columns)
    if lift is not None:
        extra = [column for column in lift.columns if column not in df.columns]
        if extra or not lift.index.equals(df.index):
            raise ValueError(
                f"lift must share the table's index and use its columns only (not in it: {extra})"
            )
        css[list(lift.columns)] = lift.map(_lift_css)
    if greyed is not None:
        grey = f"color: {THEME['insufficient']}; font-style: italic"
        css = css.mask(_greyed_mask(df, greyed), grey)
    return css


def _escaped_name(name: object) -> str | None:
    """An axis name escaped for HTML; no name stays none."""
    return None if name is None else escape(str(name))


def style_table(
    df: pd.DataFrame,
    formats: dict[str, str] | None = None,
    lift: pd.DataFrame | None = None,
    greyed: pd.Series | pd.DataFrame | None = None,
    bar: str | None = None,
    caption: str | None = None,
    bar_min: float = 0.0,
) -> Styler:
    """A DataFrame as a Styler: formats, lift colouring, greyed rows or cells, a bar, a caption.

    `lift` holds lift values for some of `df`'s cells (same index, a subset of its columns); those
    cells are coloured diverging around 1. `greyed` is a boolean Series (whole rows) or DataFrame
    (single cells): the insufficient ones are greyed, never hidden. NaN shows as an empty cell.
    The bar on column `bar` starts at `bar_min` (a value below it draws none), so a statistic
    whose floor is not 0, such as a concordance's 0.5, spreads over the cell.
    """
    if not (df.index.is_unique and df.columns.is_unique):
        raise ValueError("a styled table needs a unique index and unique column names")
    # The axes' names render unescaped (pandas 2.2 has no `format_index_names`); the labels
    # stay, so `lift` and `greyed` still align.
    df = df.rename_axis(index=_escaped_name, columns=_escaped_name)
    styler = df.style.format(na_rep="", escape="html")
    styler = styler.format_index(escape="html").format_index(escape="html", axis=1)
    if formats:
        styler = styler.format(formats, na_rep="", escape="html")
    if lift is not None or greyed is not None:
        styler = styler.apply(lambda _: _cell_styles(df, lift, greyed), axis=None)
    if bar is not None:
        styler = styler.bar(subset=[bar], color=THEME["bar"], vmin=bar_min)
    if caption:
        styler = styler.set_caption(escape(caption))
    if isinstance(df.index, pd.RangeIndex):
        styler = styler.hide(axis="index")
    return styler


def _report_css() -> str:
    """The report's CSS, built from the theme."""
    t = THEME
    return f"""
body {{ font-family: {t["font"]}; color: {t["text"]}; background: {t["background"]};
  margin: 0 auto; max-width: 1100px; padding: 0 16px 48px; line-height: 1.45; }}
h1 {{ font-size: 1.6rem; margin: 24px 0 8px; }}
h2 {{ font-size: 1.3rem; margin-top: 40px; padding-bottom: 4px;
  border-bottom: 2px solid {t["accent"]}; }}
h3, h4, h5, h6 {{ margin-top: 28px; }}
nav.toc {{ background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 6px;
  padding: 8px 16px; font-size: 0.9rem; }}
nav.toc ul {{ margin: 2px 0; padding-left: 20px; }}
a {{ color: {t["accent"]}; }}
.table-scroll {{ overflow-x: auto; margin: 12px 0; }}
.table-scroll table {{ border-collapse: collapse; font-size: 0.85rem; }}
.table-scroll th, .table-scroll td {{ border-bottom: 1px solid {t["border"]}; padding: 4px 8px;
  text-align: left; vertical-align: top; }}
.table-scroll th {{ background: {t["surface"]}; }}
.table-scroll caption {{ caption-side: top; text-align: left; font-weight: 600;
  padding: 4px 0; color: {t["muted"]}; }}
dl.kv {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; }}
dl.kv dt {{ font-weight: 600; color: {t["muted"]}; }}
dl.kv dd {{ margin: 0; }}
div.headline {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0; }}
div.headline .stat {{ background: {t["surface"]}; border: 1px solid {t["border"]};
  border-radius: 6px; padding: 8px 16px; min-width: 120px; }}
div.headline .value {{ display: block; font-size: 1.4rem; font-weight: 600; }}
div.headline .label {{ color: {t["muted"]}; font-size: 0.85rem; }}
pre {{ background: {t["surface"]}; font-family: {t["mono_font"]}; padding: 8px 12px;
  overflow-x: auto; }}
"""


def _render_block(block: object, counter: Iterator[int]) -> str:
    """One block as an HTML fragment; an unknown type fails naming it."""
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        items = "".join(
            f"<dt>{escape(str(key))}</dt><dd>{escape(str(value))}</dd>"
            for key, value in block.items()
        )
        return f'<dl class="kv">{items}</dl>'
    if isinstance(block, Styler):
        return f'<div class="table-scroll">{table_html(block, f"t{next(counter)}")}</div>'
    if isinstance(block, go.Figure):
        return figure_html(block, f"fig{next(counter)}")
    raise TypeError(
        f"a report block must be a Styler, a plotly figure, a str, a dict or a (heading, blocks) "
        f"subsection; got {type(block).__name__}"
    )


def _heading_and_blocks(section: object, where: str) -> tuple[str, list]:
    """A section's or subsection's heading and blocks; any shape but a `(heading, [blocks])`
    2-tuple fails naming what it got."""
    if not isinstance(section, tuple) or len(section) != 2:
        shape = f"a {len(section)}-tuple" if isinstance(section, tuple) else type(section).__name__
        raise TypeError(f"{where}: a section is a (heading, [blocks]) 2-tuple; got {shape}")
    heading, blocks = section
    if not isinstance(blocks, list):
        raise TypeError(
            f"{where} {heading!r}: the blocks must be a list; got {type(blocks).__name__}"
        )
    return heading, blocks


def _render_section(
    heading: str, blocks: list, anchor: str, level: int, counter: Iterator[int]
) -> tuple[str, str]:
    """A section's HTML and its table-of-contents entry; a tuple block is a subsection."""
    level = min(level, MAX_HEADING_LEVEL)
    body = [f'<h{level} id="{anchor}">{escape(heading)}</h{level}>']
    children = []
    for block in blocks:
        if isinstance(block, tuple):
            sub_heading, sub_blocks = _heading_and_blocks(block, f"a subsection of {heading!r}")
            sub_body, sub_toc = _render_section(
                sub_heading, sub_blocks, f"{anchor}-{len(children) + 1}", level + 1, counter
            )
            children.append(sub_toc)
            body.append(sub_body)
        else:
            body.append(_render_block(block, counter))
    nested = f"<ul>{''.join(children)}</ul>" if children else ""
    toc = f'<li><a href="#{anchor}">{escape(heading)}</a>{nested}</li>'
    return "\n".join(body), toc


def render_report(title: str, sections: list[tuple[str, list]]) -> str:
    """The sections as one self-contained HTML page; the caller writes it with its artifacts.

    A block is a Styler, a plotly figure, a str (an HTML fragment, inserted as is), a dict (a
    key-value list) or a `(heading, blocks)` tuple (a subsection with its own anchor).
    """
    counter = itertools.count(1)
    bodies, tocs = [], []
    for number, section in enumerate(sections, start=1):
        heading, blocks = _heading_and_blocks(section, f"section {number}")
        body, toc = _render_section(heading, blocks, f"s{number}", 2, counter)
        bodies.append(body)
        tocs.append(toc)
    return (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_report_css()}</style>"
        f'<script type="text/javascript">{get_plotlyjs()}</script></head><body>\n'
        f'<h1>{escape(title)}</h1>\n<nav class="toc"><ul>{"".join(tocs)}</ul></nav>\n'
        + "\n".join(bodies)
        + "\n</body></html>\n"
    )
