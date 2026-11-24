# Hashes, seeded draws and compatibility across releases

**Verdict:** the framework computes nine content hashes and nine seeded or hash-based draws, and
inside one pinned version all of them are stable and loud on a mismatch. Across versions they
are not ready for 1.0: adding one config field with a default moves the identity hashes, one
global `HASH_VERSION` guards unrelated things by strict equality, and no reader accepts an older
version. Nothing is wrong today, because 0.x promises nothing and every guard refuses loudly.
Three design choices are proposed for the 1.0 hardening (§6, Q687 to Q689); nothing here is
built.

**Related:** [`audit_steps_2_3.md`](audit_steps_2_3.md) item 30, [`audit_answers.md`](audit_answers.md)
Q684, `docs/components/config.md` → Identities, `docs/roadmap.md` → OD-29.

_Written 2026-11-23 from a read of the code with small probes; no Spark was run. Spark's hash
behaviour is taken from the 3.4.3 source._

## 1. The content hashes

All are sha256 over the canonical JSON (`sort_keys`, no spaces) of a pydantic
`model_dump(mode="json")`. The dump includes every field left at its default.

| Hash | Identifies | Covers | Compared by; on a mismatch |
|---|---|---|---|
| Config hash | The use-case definition | The whole config after level and task fill, without housekeeping and the kept, held and excluded lists; `schema_version` is in it | The card against the evaluation; refuses |
| Data-definition hash | The data a model is built on | Entity, task, sources, keys, eligibility, target, period, observation and target windows, candidates | It names the folder `04_feature/<hash>/`; the audit log, `check_upstream`, the ledger, `find_run`, `sign_off` and `compare_runs` compare it; refuse or skip |
| Target-spec hash | One saved target | Task, the target block, keys, the window, the target source | The model input's sidecar; refuses ("rebuild") |
| Resolved-input hash | The config with the replayed decisions | The resolved config without housekeeping; `schema_version` is in it | `check_resolved`; refuses |
| Feature signature | The final feature list | The list, in order | The sign-off entry and the bundle manifest; refuses |
| Recipe hash | How a model was fitted | Parameters, the fitted encoder, sampling, the split and the data-definition hash | Stored in the manifest and the card; nothing compares it yet |
| Model hash | One fitted model | The bytes of `bundle.json` and the model file | `build_bundle` and the card; refuses |
| Settings digest | A stage's settings | The config sections each stage owns (12 hex characters) | `check_upstream` refuses, `find_run` skips the run |
| Sources digest | The physical sources | The environment file's source entries | Refuses, or `find_run` skips |

Code: `config/identities.py`, `model/bundle.py` → `_model_hash`, `artifacts.py` →
`settings_digest`.

## 2. The seeded and hash-based draws

| Draw | How | Same on another machine or layout? |
|---|---|---|
| Client split | Spark `xxhash64` of a salt, the client id and `data.split.seed` | Yes, per row. The value is pinned by a test under Spark 3.4.3 |
| Train sampling | The same with the salt `sample` and `training.seed` | Yes, per row |
| Folds | The same with the salt `fold_<k>`; binary's converting clients are dealt in rank order | Per row for the plain folds. The dealt folds depend on which clients are in train, so another window or eligibility deals again |
| Encoding folds of EDA and Feature Checks | `xxhash64` of the client id, no salt, no seed | Yes, per row |
| Bootstrap weights of Evaluation | `xxhash64` of the client id, the replicate and a salt | Yes, per row; no pinned value |
| Level-factor bootstrap of Training | pandas `hash_pandas_object` of the client's text | pandas makes no stability promise for it |
| Explanation sample of Evaluation | `xxhash64` of the keys and `training.seed`, then an ordered limit | Yes, for one set of rows |
| Train explanation sample, the beeswarm, the selection's noise columns | numpy `default_rng(seed)` by row position | numpy may change the stream in a minor release |
| The association's row cap | pandas `sample(random_state=0)` | Yes, the legacy stream is frozen |

Every Spark draw is keyed on the client id as text. An upstream type change, such as an
integer id arriving as a decimal, changes that text and with it every draw.

## 3. What moves a hash

| Change | Hashes that move |
|---|---|
| A new config field with a default | Config and resolved-input always; data-definition, target-spec or settings digest when the field is in their sections |
| A renamed field | The same: the key's name is in the JSON |
| A changed default, or a changed level fill | Every config that leaves the field unset |
| A migration from an older `schema_version` | Config and resolved-input always, since `schema_version` is hashed; the others when the migrated section dumps differently |
| `1` written as `1.0` in the YAML | Any hash over a field typed as either |
| A patch release of a model library | The model hash of a new fit, because the model files embed the library version. A stored bundle still verifies, and loading it under another version warns |
| Another Python | None: `json` and the float text form are stable |
| Another pydantic | Unverified beyond the pinned 2.12.5 |

## 4. What a moved hash breaks

- **The data-definition hash.** The folder of the old hash is simply not found. Its audit log,
  EDA, Feature Checks and ledger are orphaned, and the gate says "holds none", not "the hash
  changed". The use case's runs still appear in `list_runs`, but `find_run` skips them and
  `sign_off` refuses them. Bundles stay loadable.
- **A settings digest.** `check_upstream` refuses the EDA and Feature Checks artifacts, and
  `find_run` skips the earlier runs.
- **The config hash.** The card refuses the earlier evaluation.
- **`HASH_VERSION`.** One bump makes every stored bundle, model input and sign-off check refuse
  with "train again", whatever the reason for the bump was.

## 5. Potential issues, by when they bite

1. **The first minor release after 1.0 that adds a field to a hashed section** orphans every
   use case's Stage 2 folder and audit log when the pin is raised. This will happen: fields
   are added in most releases.
2. **One version number for unrelated recipes.** `config.md` says a change to a hashed section
   bumps `HASH_VERSION`, and the same number guards the feature signature, the recipe hash and
   the bundle. Fixing issue 1 by a bump would make every bundle unloadable (item 30's second
   bullet).
3. **The promised message does not exist.** D-088 (the identities; `hash_version` should let
   the gate tell a schema change from a data change) is not implemented: no Stage 2 or audit-log
   reader looks at the stored version, and the hash-named folder leaves nothing to compare.
4. **A migration moves the config hash**, because `schema_version` is hashed. A migrated config
   can never match what its older form wrote.
5. **A sign-off entry is re-checked with today's signature code**, whatever version wrote it. A
   changed signature recipe would make every earlier log unreadable.
6. **No reader accepts an older version** (item 25). D-007 (what a version writes stays
   readable across versions within a major) and D-047 (each use case pins its version and must
   still load and score its production model after raising the pin) need one from the first
   bump after 1.0.
7. **Draws outside the framework's control.** Only the split is pinned by a test. The numpy
   stream, the pandas hash and Spark's `xxhash64` on the bank's build are unverified; a change
   would silently deal other folds or weights, moving numbers inside the bootstrap's noise.
8. **The client id's text form** is part of every draw and is not checked anywhere.

Smaller: two sha256 helpers (one of them not namespaced), two client-fold hashes (the unsalted
one in the counts, the salted one in the folds), two client-bootstrap generators (Spark for
Evaluation, pandas for the level factor), and no golden test for six of the nine hashes.

## 6. How compatibility across non-major releases is handled

**Today.**
- **Pinning.** A use case runs one framework version (D-047), so inside a pin no hash recipe
  changes. Every issue above appears only when a pin is raised.
- **`schema_version` and migrations** for configs: the mechanism and its test exist, the list
  of migrations is empty.
- **A version field on every artifact, read strictly.** Another version is refused with the
  fix named ("train again", "rebuild"). That is safe in both directions: an older framework
  never misreads a newer artifact, and a newer one never misreads an older.
- **0.x promises nothing**; shared formats freeze at 1.0's first row in the bank.

So today the answer to "can version n+1 read what n wrote" is a loud no. That is the right
answer for a pre-release and the wrong one from 1.0 on.

**Proposed for the 1.0 hardening** (a proposal, recorded as OD-29; not built).

1. **A field added within a major enters a hash only when it is set.** The hashes are taken
   over the dump without fields at their default, so a new field with a default leaves every
   existing hash where it was, and setting it moves the hash, as it should. Two rules keep
   this honest, each with a test: a default and a level fill never change within a major (one
   golden file of every default), and a rename waits for a major or comes with a migration.
   `schema_version` leaves the hashed dump, so a migrated config hashes like its new form.
   - Rejected: keep hashing defaults and carry stored hashes forward with an alias per
     use case. The shared tables are keyed by the old hashes and cannot be rewritten, so the
     aliases would live forever.
   - Rejected: no new field in a hashed section within a major. Too tight: most features add
     one.
2. **A version per family of hashes** in place of the global one: the config identities, the
   feature signature and the recipe hash each carry their own. The model hash is over bytes
   and needs none. A reader that compares a hash reads its version first and can then say "the
   recipe changed, not your data", which is the message D-088 promises; an audit-log entry is
   checked under the version that wrote it.
3. **Readers accept every version of their major** (item 25, already approved): a committed run
   folder that each release must load and score comes with this build; a reader per version
   starts at the first bump.
4. **The draws are pinned.** One test per draw fixes its value under the pinned Spark, numpy
   and pandas; the level-factor bootstrap takes a hash the framework owns in place of the
   pandas one; the Spark values are checked once on the bank's build. The contract states that
   the client id's text form is part of the identity.

## 7. Questions

**Q687. Hashes over set fields only, with frozen defaults (proposal 1)?** It changes every
stored hash once, so it must land before 1.0's first row in the bank. *Default:* yes, built in
the 1.0 hardening; until then OD-29 holds it.

**Q688. A version per hash family, and the "recipe changed, not your data" message
(proposal 2)?** *Default:* yes, in the same change as Q687, since both rewrite
`config/identities.py` and its readers.

**Q689. When are the draws pinned (proposal 4)?** The pinned values need a Spark run, and the
bank's build has to be checked on a bank trip anyway. *Default:* the tests come with the test
hardening before the December move into the bank, and the level-factor hash changes then too.
