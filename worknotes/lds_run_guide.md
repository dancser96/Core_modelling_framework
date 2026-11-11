# Running EDA and Feature Checks locally (for the LDS)

Do everything in a VS Code terminal at the repo root:

1. **Get the latest code** (the tip of `main`):
   `git fetch && git checkout main && git pull`
2. **Install:**
   `python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`
   This needs Python 3.11 and Java 11 with `JAVA_HOME` set; see `docs/guides/setup_macos.md` or `setup_windows_wsl2.md`.
3. **Create the data** (100k clients, about 6 min). The synthetic data changed since the first try-out, so create it again. The output folder must be new: delete any old `data/01_raw/synthetic_canonical` first.
   `python -m synthetic --preset canonical --seed 0 --out data/01_raw/synthetic_canonical`
4. **Create the environment file:**
   `sed -e "s#/ABSOLUTE/PATH#$PWD#g" -e "s#synthetic_dev#synthetic_canonical#g" conf/base/environment.example.yml > conf/local/environment.yml`
5. **Save the model input** (Target Factory, both use cases):
   `python -m core_modelling run conf/base/cc_acquisition.yml conf/base/td_acquisition.yml --stages target_factory --env conf/local/environment.yml`
   Running `notebooks/01_target_factory.ipynb` does the same.
6. **Run the notebooks** with the `.venv` kernel, Run All, in this order:
   - `notebooks/02_eda.ipynb`
   - `notebooks/03_feature_checks.ipynb`
   - optionally `notebooks/00_eda_fc_helper.ipynb`, which shows where each number comes from
   - For `td_acquisition`, change `CONFIG` in each setup cell.
7. **Open the reports** in a browser. Step 1 of each notebook prints the folder in use:
   - `<that folder>/eda/report.html`
   - `<that folder>/feature_checks/report.html`

## What to look out for
- **Rerun in order.** Outputs of an older version are refused with "rerun": run EDA, then Feature Checks. Any EDA rerun makes the stored Feature Checks stale, so rerun it after.
- **A flag acts.** Every feature Feature Checks flags is held out of training until a person keeps or excludes it (notebook 03, step 9). Judge whether the held list is right: the planted traps (`trap` in the name) should be there, and few honest features.
- **The ranking is on one scale.** Notebook 02, step 5: the concordance (0.5 means no signal) with its standard error, for both tasks. The key features in step 6 are the ones the config lists, then the top of the ranking minus near-duplicates.
- **Nulls are never filled.** A null is a bin of its own in every statistic. The sources table in notebook 02, step 4 shows how many clients each joined source covers; about 85% for the extract is built in.
- **Nothing is sampled, and the validation period is never read.** Every number comes from counts over every row of the observation window, never a client sample. People's decisions here have seen test labels, which the model report will state.

Some questions that came up before: `docs/guides/eda_fc_faq.md`.
