"""The neutral report theme: palette, fonts and the colours charts and tables share.

One dict, so the writer's CSS, the chart primitives and the table styling agree. The bank's own
theme is read from `conf/local/` in M4; nothing here names a brand.
"""

THEME: dict = {
    "font": "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif",
    "mono_font": "ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace",
    "text": "#1f2933",
    "muted": "#616e7c",
    "background": "#ffffff",
    "surface": "#f5f7fa",
    "border": "#d9e2ec",
    "accent": "#2f6f9f",
    # Categorical sequence: one colour per segment, level or model across a whole report.
    "sequence": [
        "#2f6f9f",
        "#d9822b",
        "#4a9d6b",
        "#a8506f",
        "#7d6bb3",
        "#8a6d3b",
        "#3ea3a3",
        "#c0504d",
        "#6b7f8c",
        "#b5a13a",
    ],
    "insufficient": "#aeb6bf",  # too little support: greyed, never hidden
    "null": "#8c6b9e",  # the null bar, in its own colour
    "target_class": {"0": "#6b8fb3", "1": "#d9822b"},  # one colour per target class
    "lift_low": "#2f6f9f",  # lift below 1 (cell colouring)
    "lift_high": "#d9822b",  # lift above 1
    # In-cell bars of tables: the accent, translucent so text reads on a light and a dark page.
    "bar": "rgba(47, 111, 159, 0.45)",
    "heat_scale": [[0.0, "#f5f7fa"], [1.0, "#2f6f9f"]],  # association heatmap, 0 to 1
    "heat_scale_signed": [[0.0, "#d9822b"], [0.5, "#f5f7fa"], [1.0, "#2f6f9f"]],  # -1 to 1
}
