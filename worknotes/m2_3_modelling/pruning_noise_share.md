# Importance pruning at a noise share of zero: how likely, what it costs, what to do

**Verdict:** it matters, and it is the common case, not an edge case. On simulated data the best
noise share was exactly 0 in 57 to 96% of the cases with 1,000 or more events, from 20 columns
up. The harm grows with the column count: a few real features lost at 50 columns, a quarter to
a half at 200, about two thirds at 400, for up to 0.028 of AUC. The default you approved
("a noise share of 0 prunes nothing and warns") would on its own have switched pruning off in
about 60% of runs and caught only three quarters of the wrong drops. The sizing of the pruning
model is what fixes it: with the sizing now being built the zero case did not occur once in 31
cases, so the fallback you do not love should almost never fire. The weak part turned out to be
the undo check, not the fallback: as first built in this round it kept junk by chance, it is
corrected, and measured after the correction it is a safety net that rarely fires (§6, Q692).

**Related:** [`audit_steps_2_3.md`](audit_steps_2_3.md) item 3, [`audit_answers.md`](audit_answers.md)
Q677, `docs/components/training.md` → selection.

_Written 2026-11-23. §1 to §4 were measured with the real `prune_by_importance` of commit
`38e2ce3`, §5 and §6 with this round's, on simulated frames; no Spark and no real or
synthetic-mart data. One seed per case unless said. Limits in §7._

## 1. The mechanism in short

Five noise columns are added and a small LightGBM (50 trees of 4 leaves) is fitted on the
folds. A feature whose share of the out-of-fold contributions is no larger than the best noise
column's is dropped, unless the same small model's loss rises without it. The small model makes
at most 150 splits per fold. When the real features win every one of them, no noise column is
split, the threshold is 0, and every real feature that got no split is dropped. The undo check
cannot notice, because the small model never used those features.

## 2. What was simulated

One row per client, features independent given the target, each with a set single-feature
concordance. Four signal profiles:

| Profile | Features |
|---|---|
| a | 3 strong (0.65), the rest weak (0.53) |
| b | all medium (0.56) |
| c | half weak (0.53), half pure noise (0.50) |
| d | 10 strong, the rest pure noise |

Rows of 10,000, 45,000 and 150,000 at a 10% rate, 45,000 at 2%; 20 to 400 columns reaching
pruning; 204 cases.

## 3. How likely, by data size, column count and signal strength

**Data size.** More events make it more likely, not less: the real features then win every
split and noise never gets one.

| Rows, rate (events) | Cases with a best noise share of exactly 0 |
|---|---|
| 10,000 at 10% (1,000) | 57% |
| 45,000 at 2% (900) | 22%, mostly from 200 columns |
| 45,000 at 10% (4,500) | 88%, from 20 columns |
| 150,000 at 10% (15,000) | 96% |

So the bank's large tables are the most exposed.

**Column count.** The zero case needs few columns; the harm needs more columns than the fold
models can split. Real features dropped in profile a, on average:

| Rows, rate | 50 columns | 100 | 200 | 400 |
|---|---|---|---|---|
| 10,000 at 10% | 3 | 17 | 73 | 228 |
| 45,000 at 2% | 7 | 13 | 65 | 142 |
| 45,000 at 10% | 7 | 31 | 98 | 258 |
| 150,000 at 10% | 5 | 28 | 97 | 267 |

**Signal strength.** The rule is blind to weak real features on a wide frame, and right where
the signal is concentrated.
- Profile a (weak signal spread wide) is the worst, as above.
- Profile b (all medium): 0, 3, 39 and 158 real features lost at 50, 100, 200 and 400 columns.
- Profile c (weak and junk mixed): 1, 8 and 45 real features lost at 100, 200 and 400, with
  nearly all junk dropped.
- Profile d (strong and junk): no real feature lost and all junk dropped. Here pruning does
  what it is for, including at a threshold of 0.

**Two findings beyond the audit.**
- The undo check fired in none of the 123 zero cases.
- A quarter of all wrong drops (1,534 of 6,229) came from cases where one noise column got one
  lucky split, so the threshold was just above 0. A guard on "exactly 0" misses those.

## 4. What it costs

A model of realistic size (400 trees, 31 leaves), grouped 5-fold, on all features against the
features pruning kept; 45,000 rows at 10%:

| Profile, columns | Real features dropped | Log loss | AUC |
|---|---|---|---|
| a, 50 | 8 | +0.0019 | −0.0040 |
| a, 100 | 33 | +0.0057 | −0.0121 |
| a, 200 | 91 | +0.0094 | −0.0237 |
| a, 400 | 263 | +0.0086 | −0.0283 |
| b, 200 | 35 | +0.0033 | −0.0095 |
| b, 400 | 166 | +0.0030 | −0.0125 |
| c, 200 | 9 | −0.0026 | +0.0044 |
| c, 400 | 54 | −0.0021 | −0.0091 |

Below about 50 columns the cost is small. From 100 columns of spread-out signal it is one to
three points of AUC, more than most tuning gains. In profile c the junk that goes outweighs the
weak features lost at 200 columns.

## 5. What is being built, and why this sizing

Seven sizings were compared on the same cases (45,000 rows at 10%, 50 to 400 columns, all four
profiles). P is the column count with the noise columns.

| Sizing | Zero cases | Real features dropped | Junk kept | Seconds |
|---|---|---|---|---|
| Today: 50 trees, every column offered | 10 of 11 | 626 of 1,645 | 4 of 555 | 9 |
| Trees for 2 splits per column, every column offered | 8 of 11 | 51 | 40 | 18 |
| The same, half the columns per tree | 9 of 11 | 65 | 32 | 11 |
| The same, 5 columns per tree (about 3 offers each) | 4 of 11 | 76 | 23 | 7 |
| Twice the trees, 5 columns per tree (about 7 offers) | 3 of 11 | 4 | 31 | 10 |
| **10·P/3 trees, 3 columns per tree (about 10 offers)** | **0 of 12** | **0 of 1,655** | 63 of 555 | 11 |

"About twice", the default as I worded it in Q677, is not enough: at two to three offers a weak
column is still crowded out. Ten offers with three columns per tree is the first sizing where
noise always gets its turn. Over every case run with it (31, including 10,000 rows, the 2% rate
and 150,000 rows), the best noise share was never 0 and no feature had a share of 0.

**Built with this round:**
1. The pruning model has its own size: 4 leaves, 10·P/3 trees, 3 columns per tree.
2. A best noise share of exactly 0 prunes nothing and warns (your default). With the new size
   it is a safety net.
3. The undo check compares two fits without the noise columns, with and without the
   candidates, and any rise in the loss undoes the drop. Both fits offer every column to every
   tree, at the yardstick's tree count and at most 300 trees (§6).

**The price.** Pruning becomes less sharp at its own job: about 13% of pure-noise columns
survive it (403 of 3,035 over the 31 cases), against about 1% before. In a real run the floor
removes most junk before pruning, which the simulation did not include.

## 6. The undo check, measured

**The first version kept junk by chance.** It fitted both comparison fits at three columns a
tree, like the yardstick. A frame with and a frame without the candidates then draw different
columns for every tree, and that draw alone moved the loss: a test on real data showed a
pure-noise candidate "undone" in all three tasks. Over the 31 cases:

| Undo check | Cases undone | Noise columns kept by an undo | Real features dropped (of 5,245) |
|---|---|---|---|
| Three columns a tree (first version) | 4 | 199 | 67 |
| Every column offered (now) | 0 | 0 | 217 |

Two of the four undos kept pure noise; the other two kept 150 weak real features, also by the
draw. With every column offered the two fits differ only by the candidates, and a candidate no
tree uses changes nothing.

**The 217 drops that now stand did no harm.** They sit in four cases at about 1,000 events and
400 columns, features with a concordance of 0.53. A model of realistic size (400 trees, 31
leaves) on all features against the features left:

| Case (real / junk dropped) | Log loss | AUC |
|---|---|---|
| 10,000 rows at 10%, profile a (63 / 0) | 0.3459 to 0.3420 | 0.862 to 0.864 |
| 10,000 rows at 10%, profile c (29 / 167) | 0.4041 to 0.3720 | 0.752 to 0.787 |
| 45,000 rows at 2%, profile a (87 / 0) | 0.1125 to 0.1097 | 0.864 to 0.870 |
| 45,000 rows at 2%, profile c (38 / 176) | 0.1224 to 0.1150 | 0.744 to 0.766 |

Each got better without them. On that much data such a feature costs a model more than it
gives, so the check is right not to fire.

**How many trees for the comparison.** Three counts, every column offered, on the four cases
above and six junk-only cases:

| Trees | False undo on junk | Fired on the four cases | Seconds, both fits, 45,000 and 150,000 rows at 400 columns |
|---|---|---|---|
| The yardstick's (1,350 at 400 columns) | 0 of 6 | 0 | 61 and 144 |
| 100 | 1 of 6 | 2, by the fifth decimal | 10 and 29 |
| 300 | 0 of 6 | 0 | 17 and 48 |

With the yardstick's count the comparison model overfits at about 1,000 events (its log loss
is 0.47 where 0.36 to 0.40 is reachable, the ML audit's run), and with 100 trees it fires on
noise. Built: the yardstick's count, at most 300. Below 90 columns nothing changes. The seconds
were taken on a loaded machine and are upper bounds.

**What the check does not catch.**
- **A feature that only works together with another.** Two features, each at 0.50 alone and
  0.60 as a pair: the yardstick, at three columns a tree, nominated both in two of four cases
  and one in a third. Dropping them cost a realistic model 0.001 to 0.005 of AUC. The
  comparison fits caught it in 2 of 9 tries, by margins at noise level: a small greedy tree
  finds no split whose gain shows only after the next one. A `keep` is the answer for a known
  interaction.
- **It judges the set.** One needed feature keeps every candidate, and many weak ones go
  together. The ML audit's run on wide frames with few events: real features about 2 standard
  errors from noise were nominated 115 times in 200 and dropped; about 4, 20 in 120; about 6,
  1 in 120.
- **On a narrow frame pruning often does nothing.** At 41 columns the best noise share was
  about the mean share (0.025), 21 of 36 features were nominated and the check undid them all.
  That is the designed outcome, and the run says so.

**On the synthetic marts, after the correction.** The check undid every pruning:
- the `dev` preset's three acceptance runs: 5, 5 and 14 candidates of 37 or 38 features;
- the canonical preset (257,338 train rows, 50 features): 8 candidates at a threshold of
  0.0045; the comparison's log loss was 0.110852 with them and 0.110901 without, a rise in the
  fifth decimal. The final model then gave two of its 50 features no split.

So on these frames "any rise" keeps features on margins far below what a person would act on,
which is the case for Q692.

## 7. What stays open, and how to mitigate it later

- **Correlated features.** The simulated features are independent. On real data an unused
  feature is often redundant with a used one, and dropping it is partly right, so the real
  cost is below §4's. Not measured.
- **The lucky noise split.** With five noise columns the threshold is the best of five draws.
  More noise columns with a quantile for the threshold would steady it and soften the "about
  4 standard errors" misses above. Not evaluated.
- **Each feature against its own shuffled copy** (the Boruta idea) is the sturdier design: it
  compares like with like, judges each feature alone and needs no shared threshold. It doubles
  the columns of the pruning fit. Not evaluated.
- **How to see it on a real run.** The selection table's `prune` rows carry the threshold: a
  threshold of 0 with dropped features is the zero case, and it can no longer happen silently.
  A Training warning names the fallback and the undo when they fire.
- **Not run:** more than one seed per case.

## 8. Questions

**Q690. The size is "about ten offers per column", not "about twice".** The measurement, not
the wording of Q677, set it. *Default:* accepted and built; say so if you want the smaller one.

**Q691. A follow-up on the threshold (more noise columns, or each feature against its shuffled
copy)?** *Default:* not now. It is revisited if a run inside the bank shows real features among
the `prune` rows.

**Q692. The undo check: keep it, or drop it?** Corrected, it fired in none of the 31 cases and
caught nothing real in the ones built to test it; it costs two more rounds of fold fits (up to
about 50 seconds at 150,000 rows and 400 columns). It does fire on narrow frames, where pruning
nominates most features. *Default:* keep it as the safety net, with every column offered and at
most 300 trees. Dropping it would make pruning one fit and one rule; say so if you prefer that.
