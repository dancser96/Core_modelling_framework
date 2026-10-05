# Setup — macOS (Apple Silicon)

**Verdict:** everything is native. Homebrew provides Python 3.11, Java 11 and `libomp` (needed by
LightGBM and XGBoost on macOS).

## 1. Command-line tools + Homebrew

```bash
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# then run the two 'Next steps' lines the installer prints (adds brew to your PATH)
```

## 2. Python 3.11, git, libomp, Java 11

```bash
brew install python@3.11 git libomp
brew install --cask temurin@11
echo 'export JAVA_HOME=$(/usr/libexec/java_home -v 11)' >> ~/.zshrc
source ~/.zshrc
python3.11 --version && java -version     # expect 3.11.x and 11.x
```
If the `temurin@11` cask is unavailable, install Temurin 11 from adoptium.net (macOS aarch64 .pkg).

## 3. GitHub access (SSH) and clone

```bash
git config --global user.name  "<your name>"
git config --global user.email "<your github email>"
ssh-keygen -t ed25519 -C "<your github email>"
pbcopy < ~/.ssh/id_ed25519.pub        # paste into GitHub → Settings → SSH keys
ssh -T git@github.com
mkdir -p ~/code && cd ~/code
git clone git@github.com:<you>/retail.core_modelling.git && cd retail.core_modelling
```

## 4. Virtual environment + dependencies

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

## 5. Verify the stack

```bash
python -c "import numpy as np; np.NaN = np.nan; import flaml, pyspark; print('imports ok')"
python -c "from pyspark.sql import SparkSession; s = SparkSession.builder.master('local[2]').getOrCreate(); print('spark ok', s.range(3).count())"
pytest
```
If LightGBM or XGBoost fail to import with an OpenMP error, `brew reinstall libomp`.

## 6. VS Code + Claude Code

1. Install VS Code (code.visualstudio.com). `Cmd+Shift+P` → *Shell Command: Install 'code'
   command in PATH*.
2. `code .` in the repo, then install the recommended extensions (Python, Jupyter, Ruff,
   Claude Code).
3. *Python: Select Interpreter* → `./.venv/bin/python`.
4. Claude Code CLI: `curl -fsSL https://claude.ai/install.sh | bash`, then `claude` to log in.
5. Optional, gives Claude live Python type checking: `brew install pyright` (outside the venv; dev
   machine only), then once in the repo
   `claude plugin install pyright-lsp@claude-plugins-official --scope project`.
6. Optional: turn on VS Code **Settings Sync** so both machines share settings and extensions.

Next: `docs/guides/claude_code_workflow.md`.
