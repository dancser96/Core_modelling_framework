# Running EDA and Feature Checks locally (for the LDS)

Do everything in a VS Code terminal at the repo root:

1. **Get the code** (`500fd92`, so the later synthetic changes don't get pulled in):
   `git fetch && git checkout 500fd92`
2. **Install:**
   `python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`
   This needs Python 3.11 and Java 11 with `JAVA_HOME` set; see `docs/guides/setup_macos.md` or `setup_windows_wsl2.md`.
3. **Create the data** (100k clients, about 6 min). The output folder must be new, so delete any old `data/01_raw/synthetic_canonical` first:
   `python -m synthetic --preset canonical --seed 0 --out data/01_raw/synthetic_canonical`
4. **Create the environment file:**
   `sed -e "s#/ABSOLUTE/PATH#$PWD#g" -e "s#synthetic_dev#synthetic_canonical#g" conf/base/environment.example.yml > conf/local/environment.yml`
5. **Save the model input** (Target Factory, both use cases):
   `python -m core_modelling run conf/base/cc_acquisition.yml conf/base/td_acquisition.yml --stages target_factory --env conf/local/environment.yml`
   Running `notebooks/01_target_factory.ipynb` does the same.
6. **Run the notebooks** with the `.venv` kernel, Run All, in this order:
   - `notebooks/02_eda.ipynb`
   - `notebooks/03_feature_checks.ipynb`. Rerun it after any EDA rerun, because EDA clears Feature Checks' output.
   - optionally `notebooks/00_eda_fc_helper.ipynb`
   - For `td_acquisition`, change `CONFIG` in each setup cell.
7. **Open the reports** in a browser:
   - `data/cc_acquisition/04_feature/<hash>/eda/report.html`
   - `data/cc_acquisition/04_feature/<hash>/feature_checks/report.html`
