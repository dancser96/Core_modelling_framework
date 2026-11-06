# Stage 2 (M2.2 Understanding): design questions
_Every earlier round is answered and recorded verbatim with its outcome in `answers.md` beside
this file (rounds 1–4 Q418–Q493, the remarks R1–R28, reviews 1 and 2, Q494–Q522). The review-2
build is done (`review2_spec.md`); these two arose from its 100k report. Defaults in brackets._

- **Q523.** Rate axes show fractions (`0.03`) while the tables show percentages (`2.93%`). A
  per-task axis format in `TASK_SPECS` (binary `.1%`, regression plain), applied by the views to
  the estimate axes, would make them match; the lift and concordance axes stay plain. [yes, in
  major step 3's first minor step: one spec entry and one argument]
- **Q524.** In a strata chart (one line per stratum level over a key feature's groups), a thin
  level whose every point is grey sets the axis: on the 100k card data, Priority and Private spike
  to a lift of 8–11 and flatten the main segment's line, which carries the reading. Options:
  (a) keep: every point in view; (b) the axis follows the supported points only, a grey point may
  run off the top as an insufficient bar's interval already does (the pivot table below holds the
  number); (c) draw a level without any supported point dotted and thin, axis unchanged.
  [(b): the chart answers "does the shape hold in each segment", which only supported levels can
  tell]
