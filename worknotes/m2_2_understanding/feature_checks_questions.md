# Stage 2 Feature Checks (major step 3): questions for the SDS
_Updated 2026-11-09. Q532–Q545 are answered and recorded verbatim with their outcomes in
`answers.md` ("Feature Checks review 1" and "Feature Checks review 1, answers"). The decisions
the build made without a question are `plan.md` §9 V74–V103, to veto by number. The
synthetic-data to-do from Q545 is `worknotes/synthetic_trap_coverage.md`._

**Q546. Split `steps.py` now?** [Q538: one module, your default when it had about 700 lines.]
Answering Q539–Q544 added the null sets, the evidence phrase, Cohen's sides and the per-period
SEs: it now holds about 920 lines, three times the ~300-line guide. The five steps share only
their inputs and the frame builders, so they cut cleanly (D-003, role subfolders): a
`feature_checks/steps/` package with `inputs.py` (`CheckInputs`, `check_inputs`, the stale-EDA
refusals), `frames.py` (`_flagged`, `_unavailable`, `_result`, `stack_parts`, `_evidence`) and
one module per step, `STEPS` in its `__init__.py`. No behaviour changes; the tests move with it.
- (A) Keep one module, as built.
- (B) Split now, before your code review, so you read five modules of 100–250 lines.

**Default: (B)**, if you review the code next; (A) if you have started reading it.

**Q547. A floor on `concordance_unstable`'s relative range?** [Q544: the range at least
`concordance_range_min` × |`concordance_window` − 0.5|.] As a feature's window signal nears 0.5,
the required range nears 0 and Cochran's Q alone decides; on a large population (SE about 0.003)
a weak feature with a real 0.02 seasonal wobble is then held. Both reviews raised it, and the
canonical term-deposit config shows it: `ebanking_flag` and `digital_active_flag`, window
concordance 0.52 and 0.50 (no signal), range 0.043 and 0.046, Cochran's p 0.010 and 0.006 at 786
events in the thinnest period, are held as unstable; the old absolute 0.05 let them through.
- (A) As built: no floor (a weak feature held costs little, and you prefer too many flags).
- (B) A config leaf `stability.concordance_range_floor`, default 0.05 (the old absolute rule):
  the range must reach the larger of the floor and the relative bound, so a strong feature is
  judged on its own signal and a signal-less one needs a real swing; a flip (0.4 → 0.6) still
  fires.

**Default: (B):** a flag on a feature with no signal is noise for the reviewer, the kind a busy
reader learns to wave through.
