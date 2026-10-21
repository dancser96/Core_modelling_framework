# Setup — Windows 11 (WSL2)

**Verdict:** do all development *inside* WSL2 (Ubuntu). Windows only runs VS Code, which connects
into WSL. The Mac and the PC then use the same shell commands, and PySpark avoids the
Windows-native workarounds.

**Status:** deferred. The builder works on the Mac only until large data or heavy testing needs
the PC. [Switching from the Mac](#switching-from-the-mac) lists everything that doesn't travel
with git; keep it current whenever something machine-local is added on the Mac.

Time: ~30–45 min once. Commands in `PowerShell` blocks run in Windows; everything else runs in the
Ubuntu terminal.

## 1. Install WSL2 + Ubuntu

```powershell
# PowerShell as Administrator
wsl --install -d Ubuntu-24.04
```
Reboot when asked. Ubuntu then opens and asks for a Linux username and password (independent of
Windows). If WSL was already installed: `wsl --update`, then `wsl --set-default-version 2`.

## 2. System packages (Ubuntu terminal)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git build-essential libgomp1 software-properties-common curl
```

## 3. Python 3.11 (Ubuntu 24.04 ships 3.12, the bank uses 3.11)

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
python3.11 --version          # expect 3.11.x
```

## 4. Java 11 (bank parity for PySpark 3.4.3)

```bash
sudo apt install -y openjdk-11-jdk
java -version                 # expect 11.x
echo 'export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64' >> ~/.bashrc
source ~/.bashrc
```
If `apt` cannot find `openjdk-11-jdk`, install Eclipse Temurin 11 from adoptium.net's apt
repository and point `JAVA_HOME` at it.

## 5. GitHub access (SSH)

```bash
git config --global user.name  "<your name>"
git config --global user.email "<your github email>"
ssh-keygen -t ed25519 -C "<your github email>"     # accept defaults
cat ~/.ssh/id_ed25519.pub                          # copy → GitHub → Settings → SSH keys → New
ssh -T git@github.com                              # expect a greeting
```

## 6. Clone into the Linux filesystem (not /mnt/c — it is much slower)

```bash
mkdir -p ~/code && cd ~/code
git clone git@github.com:<you>/retail.core_modelling.git
cd retail.core_modelling
```

## 7. Virtual environment + dependencies

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

## 8. Verify the stack

```bash
# numpy 2 + PySpark 3.4 needs the NaN alias before flaml/pyspark.pandas import (trap T1)
python -c "import numpy as np; np.NaN = np.nan; import flaml, pyspark; print('imports ok')"
python -c "from pyspark.sql import SparkSession; s = SparkSession.builder.master('local[2]').getOrCreate(); print('spark ok', s.range(3).count())"
pytest                        # 'no tests ran' is expected until the first tests exist
```

## 9. VS Code + Claude Code

1. Install **VS Code on Windows** (code.visualstudio.com). Install the **WSL** extension
   (`ms-vscode-remote.remote-wsl`).
2. From the Ubuntu terminal, in the repo folder, run `code .` — VS Code opens connected to WSL
   (bottom-left shows `WSL: Ubuntu-24.04`).
3. Install extensions **in WSL** (VS Code offers "Install in WSL"): Python, Jupyter, Ruff,
   **Claude Code**. The repo recommends them via `.vscode/extensions.json`.
4. `Ctrl+Shift+P` → *Python: Select Interpreter* → `./.venv/bin/python`.
5. Claude Code CLI inside WSL (the extension does not put `claude` on your PATH):
   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   claude                        # log in with your Claude account
   ```
6. Notebooks: open any `.ipynb` and pick the `.venv` kernel.
7. Optional, gives Claude live Python type checking: `sudo apt install -y pipx && pipx install
   pyright` (outside the venv; dev machine only), then once in the repo
   `claude plugin install pyright-lsp@claude-plugins-official --scope project`.

Next: `docs/guides/claude_code_workflow.md`.

## Switching from the Mac

Everything committed travels with git. These don't:

1. **This guide's system setup:** Java 11 + `JAVA_HOME`, Python 3.11, `libgomp1` (the Mac's
   `libomp`), then `pip install -r requirements-dev.txt` (it also installs `synthetic/` and the
   scipy / plotly pins).
2. **Claude Code's laptop-level state.** Everything project-specific that Claude follows is in the
   repo (`CLAUDE.md`, `.claude/skills`, `.claude/agents`, `.claude/commands`, `.claude/settings.json`)
   and travels with git. What does not, as of 2026-10-20:
   - **The memory folder** `~/.claude/projects/<mac-path>/memory/`: the rules and preferences
     Claude recorded across sessions (one file per fact plus `MEMORY.md`). Copy it into the folder
     Claude Code creates for the repo on the PC (`~/.claude/projects/<pc-path>/memory/`). The
     folder name encodes the repo's absolute path, so it differs per machine. Open a session in
     the repo once first, so the folder exists. This is the only place where Claude's cross-session
     "rules" live outside the repo; sessions and chat history do not transfer and are not needed.
   - **User settings** `~/.claude/settings.json`: currently only the model choice. Copy or set it.
   - **User-level skills** `~/.claude/skills/`: the synced `skill-creator` (kept user-level by
     D-019). It re-syncs from the account; nothing to copy.
   - **Plugins** `~/.claude/plugins/installed_plugins.json`: `pyright-lsp` (D-019). Re-enable it
     from the marketplace on the PC rather than copying the file.
   - **Gitignored repo files** are item 3 below.
3. **Gitignored local files**, if they exist by then: `conf/local/` (copy),
   `.claude/settings.local.json` (copy), `data/` (regenerate the synthetic data from its seed
   rather than copying it).
4. **Verify:** `pytest` green, then run step 0's proof on the PC
   (`docs/components/test_harness.md`).

