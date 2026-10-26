# Handover: synthetic_build
_Written: 2026-10-26 · branch: main · last commit: 0fec6de ("Doc changes", 2026-10-25); the 0.5.0
build below is uncommitted. The M1 build plan that used to live here is history (git); the code
map is `docs/components/test_harness.md` → Level 3 → Code map._

## Goal
Keep the dev-only `synthetic/` package the trustworthy ground truth every framework stage is tested
against. The current thread is the LDS's to-dos from accepting M1 (2026-10-21): "Add noisy
(univariate, random etc) which further makes sure checks work · Maybe very low fillrates for
testing · All of them like traps have to have it in their name". They are built for the first
target build and run-through, **credit-card acquisition**. The SDS's words on 10-25: build them now
(Stage 1, not M4); "move everything to 0.5.0, assume we'll have the dev with 20k rows"; the package
"will travel as code, but definitely not travel as data"; "no need to split the traps".

## State
**Done (2026-10-25), verified:**
- `synthetic` 0.5.0: ten trap columns, on in every preset (147 → 157 columns). The list, the
  constructions and the expected behaviour are in `test_harness.md` → Trap summary.
  - Kinds: a random flag (`null_control`), a 300-level code (`high_cardinality`), two
    `constant`s (the LDS's "univariate"), a `redundant` tenure column, two `low_fill` columns, a
    `missing_leak` (the offer code) and the card twins of `shifted` and `process_leak`.
  - Two new random streams, appended last: `noise` (per-client and per-month columns) and
    `card_leaks` (the new look-ahead draws). Every 0.4.0 column is byte-identical at the same seed.
- A `dev` preset (20k × 24) in `spec/presets.py`. The local source mapping and its example in
  `conf/base/sources.example.yml` point at `data/01_raw/synthetic_dev/mart`.
- Datasets regenerated at 0.5.0:
  - `synthetic_dev`: 20k, 68 s, 1,301 of 1,305 rows pass (the four are size-bound, see Gotchas);
  - `synthetic_canonical`: 100k, 328 s, 1,309 of 1,309 pass. The 0.4.0 copy is deleted.
- Checks: the traps family has 103 rows; the mart family's type and null lists are extended.
- Tests: the snapshot has 157 names; the look-ahead list has 8 columns; the Spark trap types are a
  name-keyed table; a code rule asserts `src/core_modelling/` never contains `_trap_`.
  Fast suite: 47 passed; `ruff check .` clean (10-25, final state).
- Notebook `00_synthetic_data.ipynb`, rerun:
  - section 6 screens the categorical trap columns by whether they are filled, and explains the
    card twins;
  - appendix A6's filter covers the new check rows;
  - first cell: 0.5.0, 1,309 of 1,309.
- Reviews: simplicity clean. The code reviewer approved; 4 of 7 suggestions taken, the 3 declined
  ones logged. The ML auditor: safe; 2 low findings taken.
- Docs: `test_harness.md`, `synthetic/REVIEW.md`, `tests/README.md`, the roadmap's backlog and M1
  row, the timeline's depth row, `UPDATES.md`, D-064 and D-041, the sync page, the log.

**In progress elsewhere (not this topic's to build):** the Stage 1 chat's plan
(`worknotes/m2_1_foundation/plan.md` §6, step 2.1, due 10-28) adds the slim `holdings` table to
`synthetic/output.py`. That makes 0.5.1, and it regenerates `dev` and `canonical` once. The dev
preset it originally planned is already here.

**Not started:** the `unstable` trap kind (M4, with Feature Checks' stability). The acceptance
test mapping each trap kind to the Feature Checks step that must flag it belongs to M2.2, in
`tests/`, written when Feature Checks is built.

**Uncommitted, this topic's files:**
- `synthetic/src/synthetic/`: `__init__.py`, `spec/{traps,presets}.py`,
  `mechanisms/{traps,clients}.py`, `generate.py`, `checks/{traps,mart}.py`;
- `tests/`: `README.md`, `data/synthetic_mart_columns.txt`, `test_code_rules.py`,
  `test_synthetic_mart.py`, `test_synthetic_population.py`;
- `notebooks/00_synthetic_data.ipynb`, `synthetic/REVIEW.md`, `docs/components/test_harness.md`,
  `conf/base/sources.example.yml`.

Shared with the Stage 1 chat's uncommitted hunks: `docs/{UPDATES,decisions,roadmap}.md`,
`worknotes/{log,sync,timeline_proposal}.md`. `worknotes/synthetic_questions.md` was deleted after
step 2c (its README row too); its outcomes are in D-064, D-041, `test_harness.md` and the log.

## Decisions in that chat
- All are in `docs/decisions.md`:
  - D-064 extended: the trap columns and kinds, the card twins, the trap list as the acceptance
    list, the framework stays name-blind, `unstable` deferred;
  - D-041 extended: the package goes into the bank as code, never as data; tests generate their
    data from a seed; this closed OD-29.
- Smaller choices, recorded in the log only:
  - the `card_leaks` stream separate from `noise`;
  - no split of `checks/traps.py` (518 lines) or `mechanisms/traps.py` (the SDS, 10-25);
  - three declined review suggestions: descriptive spec parameters the code doesn't read follow
    the existing rows; `relationship_days` is computed twice a month; the module sizes.

## Open questions (with the user's latest leaning)
- The LDS's feedback on reading "univariate" as a one-value column (sync page review item, for
  information). The SDS keeps both definitions: constant and redundant.
- Commit: nothing is committed. Commit only when the SDS asks, with a message (memory: git).

## Next steps
1. **On the SDS's request, commit the 0.5.0 build.** Use the file list above. The shared docs
   carry the Stage 1 chat's hunks too, and `git add -p` is interactive (not available), so ask the
   SDS whether to commit them whole or leave them to that chat.
2. **After the Stage 1 chat's step 2.1 (0.5.1, holdings table), verify the regeneration:**
   - every 0.5.0 mart column byte-identical, since the change is additive;
   - 1,309 of 1,309 rows at 100k;
   - the notebook rerun, its first cell printing 0.5.1 (see the runner in Gotchas).
3. **M2.2, with Feature Checks:** the acceptance test in `tests/`. It runs on the `unit` preset
   generated in the test, loops over `truth["spec"]["traps"]`, and holds the kind → step mapping:
   - quality ← constant, near_constant, all_null, low_fill, high_cardinality;
   - leakage ← leak, missing_leak, process_leak, upstream_target;
   - time alignment ← shifted; redundancy ← redundant;
   - the null controls in the bottom decile of EDA's ranking.

## Gotchas
- **Never add draws to an existing stream.** Append a new one to `generate.STREAMS`. The first
  build drew the card twins from `leaks`; that shifted the stream for every later month and changed
  three 0.4.0 columns. Prove byte-identity on `unit`: pickle HEAD's mart and oracle, then
  `assert_frame_equal` on the old columns.
- **Two expressions must stay identical:** the redundant column is
  `np.floor(relationship_days / 30.44)` (true division), and the check restates exactly that.
- **Leaks count a non-holder who takes the card and then leaves** as an acquirer, like the 0.4.0
  leaks, while D-029's target nulls leavers. The checks only use known-target rows.
- **Fading tells:** the offer code's fill falls to the 1% floor in the panel's last 3 months, as
  the windows truncate; the shifted columns are null in the last month.
- **`--checks` on `dev` exits 1 by design.** Four statistical rows need 100k: the 6-month opening
  floors for auto and home loans, the digital share rise, and a Private-profile login ratio.
- **Canonical `--checks` takes 10–15 min.** Run `write_checks(out, families)` in two halves as
  background jobs. Write into a fresh folder and swap only after every row passes (`load_truth`
  refuses a stale version). One memory-heavy job at a time on the 8 GB Mac.
- **The venv has no `nbconvert` or `nbclient`;** adding one needs the SDS's approval. The notebook
  was rerun with a small `jupyter_client` script (scratchpad, not in the repo; rewrite it if
  needed). It must:
  - write the file back in VS Code's layout: `json.dumps(nb, indent=1, ensure_ascii=True)`, no
    `sort_keys` (outputs keep insertion order), no trailing newline;
  - set `PLOTLY_RENDERER=vscode`, so outputs stay the `application/vnd.plotly.v1+json` type.

  Ruff lints notebook cells at 100 characters. Plotly 6 saves arrays as base64
  `{"dtype", "bdata"}`, so decode them when inspecting a figure.
- **The low-fill bar in section 6 (0.56) is noise:** about 190 filled clients in the 20% sample.
  On all 100k clients its AUC is 0.47; the notebook text says so.
- **Still valid from M1:**
  - flags are int 0/1, so cast to bool for masks;
  - pyarrow can't cast NaN to decimal (`cc_limit` is 0 without a card);
  - month folders `YYYY-MM-DD` (T18);
  - the oracle's row `t` is the chance of the move into `t`;
  - the mart check family runs on a client sample at 100k;
  - test functions need docstrings and type hints.
- **Process:** questions for a new topic go in their own `worknotes/` file, never into another
  chat's active file. Re-read the highest Q- and D-number right before numbering; another chat
  numbers too.

## Read first
1. `docs/components/test_harness.md`: Level 1–2, then Level 3 → Trap summary, Interface and
   presets.
2. `docs/decisions.md`: D-064, D-041 (and D-029 for event semantics).
3. `worknotes/log.md`: the entry "Synthetic data: the LDS's to-dos reviewed and planned".
4. `worknotes/m2_1_foundation/plan.md` §6, step 2.1 (the holdings table, 0.5.1).
5. `synthetic/REVIEW.md` §1–2, then the code: `spec/traps.py`, `mechanisms/traps.py`
   (`noise_columns`, `finalize_lookahead`, `_applications`), `checks/traps.py`.
