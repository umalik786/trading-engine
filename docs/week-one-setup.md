# Week One — Click by Click

**Assumes:** Windows, Python 3.11 installed, VS Code installed, no coding experience.
**Produces:** a working project folder, tools installed, code backed up to GitHub, and one test passing on screen.
**Time:** two to three hours, comfortably split across two sittings.

Nothing here is trading yet. This is building the workbench.

Steps 1–9 are one sitting. Steps 10–14 are the second.

---

## Before you start: three words you'll see constantly

**Terminal.** A text box where you type commands instead of clicking buttons. Also called a command line, console, or PowerShell. It's built into VS Code so you won't need a separate window.

**Package.** Someone else's code that your project uses, downloaded from the internet. Like an add-in for Excel.

**Repository (repo).** A folder whose entire history is tracked — every change, when, and why. Not a backup of the current state; a recording of how it got here.

That's enough vocabulary to begin.

---

## Step 1 — Open a terminal inside VS Code

1. Open VS Code.
2. Top menu: **Terminal → New Terminal**.
3. A panel opens along the bottom.

**What you should see:** a line ending in `>` with a blinking cursor. Something like:

```
PS C:\Users\YourName>
```

`PS` means PowerShell. The path is the folder the terminal is currently "standing in". Commands you type act on that folder.

That's it for this step. Leave it open.

---

## Step 2 — Check Python is reachable

Python being installed and Python being *findable from the terminal* are two different things. Check.

Type this and press Enter:

```
python --version
```

**Working:** `Python 3.11.9` or similar.

**Two ways it goes wrong:**

*The Microsoft Store opens, or you see nothing at all.* Windows ships a placeholder that hijacks the word `python`. Fix it: Start menu → search **"Manage app execution aliases"** → open it → find the two entries called **App Installer: python.exe** and **App Installer: python3.exe** → switch both **Off**. Close and reopen the terminal, try again.

*`'python' is not recognized as an internal or external command`.* Python was installed without being added to PATH — the list of places Windows looks for programs. Try this instead:

```
py --version
```

If `py` works, you're fine; just use `py` where this guide says `python`. If neither works, reinstall Python from python.org and **tick the "Add python.exe to PATH" checkbox on the first installer screen**. It's easy to miss and it's the single most common Python installation problem on Windows.

Don't continue until one of these shows you a version number.

---

## Step 3 — Install `uv`

**What it is:** the tool that manages which packages your project uses and keeps them at fixed versions. That last part matters for your project specifically — `trading-engine-architecture.md` P5 requires that the same code and data always produce the same result, and "same code but a different version of a package" isn't the same code.

Type:

```
pip install uv
```

**What you'll see:** several lines of text, ending with something like `Successfully installed uv-0.x.x`.

Then confirm it's there:

```
uv --version
```

**Working:** a version number.

**If `pip` isn't recognized:** use `python -m pip install uv` instead. (`-m` means "run the module that came with Python", which sidesteps PATH problems.)

---

## Step 4 — Create the folders

You're building this structure:

```
C:\trading\
    engine\      the code
    data\        market data — deliberately outside the code folder
    runtime\     logs and saved state — also outside
```

**Why data and runtime sit outside the code folder rather than inside it:** there's a routine cleanup command in Git, `git clean -xdf`, that deletes files the repository is told to ignore. If your market data lived inside the code folder as an ignored folder, that one command would delete gigabytes of history and your saved trading state. Keeping them outside means no cleanup command can reach them.

In the terminal, type each line and press Enter after each:

```
cd C:\
mkdir trading
cd trading
mkdir engine
mkdir data
mkdir runtime
cd engine
```

`cd` means "change directory" — walk into a folder. `mkdir` means "make directory".

**What you should see:** the prompt now reads `PS C:\trading\engine>`. The prompt always tells you where you are.

**One thing to check.** Confirm `C:\trading` is not being synced by OneDrive. Windows sometimes redirects folders without asking. Open **Settings → OneDrive → Backup** and make sure nothing points at `C:\trading`. OneDrive holds locks on files your engine will have open, and syncs half-written files.

---

## Step 5 — Open the folder in VS Code

1. VS Code menu: **File → Open Folder**.
2. Navigate to `C:\trading\engine`, click **Select Folder**.
3. If asked "Do you trust the authors of the files in this folder?" — yes, it's yours.

**What you should see:** a sidebar on the left showing an empty ENGINE folder. Reopen the terminal if it closed (**Terminal → New Terminal**); it now opens directly in `C:\trading\engine`.

---

## Step 6 — Create the project

```
uv init .
```

The `.` means "here, in the current folder".

**What you should see:** a few new files appear in the left sidebar:

| File | What it is |
|---|---|
| `pyproject.toml` | The project's definition — its name, its Python version, its list of packages |
| `.python-version` | Which Python version this project uses |
| `README.md` | A description file, currently empty |
| `main.py` or `hello.py` | A sample file you'll delete shortly |
| `.gitignore` | A list of things not to track (created here or in step 10) |

Now pin the Python version explicitly:

```
uv python pin 3.11
```

**What you should see:** `Pinned `.python-version` to `3.11``

Click on `pyproject.toml` in the sidebar to look at it. You don't need to understand it. It's just useful to see that the file exists and is short.

---

## Step 7 — Add your first packages

```
uv add --dev pytest
```

`pytest` is the tool that runs tests. `--dev` marks it as something needed while building but not while running live.

**What you should see:** a few lines about resolving and installing packages, then a summary. Two new things appear:

- A folder called `.venv` — the "virtual environment", a private copy of Python that belongs only to this project. This is why installing a package here can't break anything else on your computer.
- A file called `uv.lock` — the exact versions of everything, so this project can be rebuilt identically later.

Then add the small compatibility package mentioned earlier:

```
uv add typing-extensions
```

---

## Step 8 — Install the VS Code extensions

Extensions are add-ons. Four of them.

1. Click the **Extensions** icon in the far-left sidebar — four squares, one detached.
2. Search and click **Install** for each:

| Extension | Publisher | What it does |
|---|---|---|
| **Python** | Microsoft | Understands Python files; enables the Testing panel |
| **Pylance** | Microsoft | Catches mistakes as you type, underlined in red |
| **Ruff** | Astral Software | Formats your code automatically and flags problems |
| **Claude Code** | Anthropic | Claude writes and edits code directly in the editor |

3. Now point VS Code at the right Python. Press **Ctrl+Shift+P** — this opens the Command Palette, a search box for VS Code's own commands. Type `Python: Select Interpreter` and press Enter. From the list, choose the one showing a path containing `.venv`. It'll look like:

```
Python 3.11.9 ('.venv': venv)   .\.venv\Scripts\python.exe
```

**Why this matters:** without it, VS Code uses your system-wide Python instead of the project's private one, and nothing you installed will be visible. It's a common source of "but I installed it!" confusion.

---

## Step 9 — Get a green tick, then a red cross

This is the important step, and not for the reason it looks like.

### 9a. Make a test file

1. In the sidebar, hover over the ENGINE folder name. Click the **New Folder** icon (a folder with a `+`). Name it `tests`.
2. Hover over `tests`. Click the **New File** icon. Name it `test_setup.py`.

The name matters: `pytest` finds tests by looking for files starting with `test_` containing functions starting with `test_`. Break that convention and it finds nothing and says nothing.

3. Type this into the file:

```python
from datetime import datetime, timezone


def test_arithmetic_works():
    assert 1 + 1 == 2


def test_datetime_is_timezone_aware():
    now = datetime.now(timezone.utc)
    assert now.tzinfo is not None
```

4. Save with **Ctrl+S**.

Reading it plainly: `def` starts a function. `assert` means "this must be true, or fail". The second test checks that a timestamp knows which time zone it's in — that's the discipline your architecture doc calls for in Appendix A.3, since you're in Dubai at UTC+4, your broker's server is on a different offset with daylight saving, and everything internally must be UTC. Three time bases. This is the habit that stops them mixing.

### 9b. Run them

```
uv run pytest
```

**What you should see:**

```
==================== test session starts ====================
collected 2 items

tests\test_setup.py ..                                 [100%]

===================== 2 passed in 0.03s =====================
```

Two dots, two passed, in green. That's the workbench working.

### 9c. Now break one on purpose

Change `assert 1 + 1 == 2` to `assert 1 + 1 == 3`. Save. Run `uv run pytest` again.

You'll get a red `F`, a failure, and an explanation of what it expected versus what it got.

**Why do this deliberately.** `project-alignment.md` §8 names the failure mode: accepting a phase because the tests are green, when the tests were written from the same misunderstanding as the code. A test you have never seen fail might not be testing anything at all — it might be passing vacuously, or not running. Watching a test go red is how you know it can.

You'll use this repeatedly. When Claude Code says a phase passes, one good question is "show me this test failing when the thing it checks is broken." That's a question you can ask without reading a line of the implementation.

Change it back to `== 2`. Save. Run again. Green.

### 9d. The Testing panel

1. Click the **Testing** icon in the far-left sidebar — a flask or beaker.
2. If prompted to configure, choose **pytest**, then the **tests** directory.
3. Your two tests appear as a list with play buttons.

Click the play button at the top. Green ticks. This is the interface you'll use for phase exit criteria — a visible list of what passes and what doesn't, no terminal required.

**End of the first sitting.** Everything below can wait for another day.

---

## Step 10 — Install Git

**What it is:** the thing that records every change to your code with a note about why. It's also what puts your work somewhere other than one hard drive.

1. Go to **git-scm.com/download/win**. The download starts automatically.
2. Run the installer. It has a lot of screens. Accept defaults on all of them **except these two**:

**"Choosing the default editor used by Git"** — the default is **Vim**. Do not accept it. Vim is a text editor that famously traps newcomers because quitting it requires knowing a specific key sequence. Choose **"Use Visual Studio Code as Git's default editor"** from the dropdown.

**"Adjusting the name of the initial branch in new repositories"** — choose **"Override the default branch name for new repositories"** and leave it as `main`. GitHub uses `main`; matching avoids a small confusion later.

3. Finish. **Close VS Code completely and reopen it** — it only detects Git at startup.
4. In the terminal:

```
git --version
```

**Working:** a version number.

5. Tell Git who you are. This gets attached to every change you record:

```
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

---

## Step 11 — Start tracking your work

```
git init
```

**What you should see:** a message about an empty repository being initialised. In the sidebar, filenames turn green or get letters beside them — Git is now noticing changes.

Now check `.gitignore` exists in the sidebar. Open it, and make sure it contains at least:

```
.venv
__pycache__/
*.pyc
.env
```

Add any that are missing, one per line, and save.

**What this file does:** lists things Git should not record. `.venv` is thousands of downloaded files that can be rebuilt from `uv.lock` — no point storing them. `.env` is where credentials will live later, and it must never be recorded, because this repository is going to be public.

Now record your first change:

```
git add .
git commit -m "Initial project setup"
```

`git add .` means "include everything that changed". `git commit` records it with a message describing what and why.

**What you should see:** a summary listing several files changed.

---

## Step 12 — Put it on GitHub

**What GitHub is:** a website that stores repositories. It's your backup, and later it's what runs your tests automatically every time you change something.

1. Go to **github.com**, create a free account if you don't have one.
2. Click the **+** at the top right → **New repository**.
3. Name: `trading-engine`. Visibility: **Public** (this is the framework — `project-alignment.md` §5 says the framework is the credential). **Do not tick** "Add a README" or any other initialise option — your folder already has files, and pre-filling causes a conflict that's confusing to untangle.
4. Click **Create repository**.
5. The next page shows commands under "…or push an existing repository from the command line". They look like this, with your username:

```
git remote add origin https://github.com/YOURNAME/trading-engine.git
git branch -M main
git push -u origin main
```

Type them into the VS Code terminal, one at a time.

**What happens:** a browser window opens asking you to sign in to GitHub. That's Git Credential Manager, installed alongside Git, handling authentication so you never type a password into the terminal. Sign in, and the push completes.

6. Refresh the GitHub page. Your files are there.

From now on, saving work is three actions in VS Code's **Source Control** panel (the branching icon in the left sidebar): type a message, click the tick to commit, click **Sync Changes** to push. No commands needed.

---

## Step 13 — The private repository

Your strategies stay private. Repeat step 12 with two differences: name it `trading-engine-private`, and set visibility to **Private**.

Then create the folder for it locally:

```
cd C:\trading
mkdir private
cd private
git clone https://github.com/YOURNAME/trading-engine-private.git .
```

`git clone` downloads a repository. The `.` again means "into here".

It's empty for now. It becomes relevant around week 7. Setting it up now means the split exists from the start rather than being retrofitted, which is harder — separating public from private after the fact means rewriting history.

---

## Step 14 — The three memory files

These solve the problem that neither Claude Code nor a new chat remembers anything.

### `CLAUDE.md`

In the sidebar, with `C:\trading\engine` open, create a new file in the root called `CLAUDE.md`:

```markdown
# Trading Engine

A strategy-agnostic trading engine. Full specification in `docs/architecture.md`;
rationale and decision record in `docs/alignment.md`. Read both before making changes.

## Non-negotiables

- One engine, two wirings. Backtest and live share the same orchestrator.
  There is no separate backtester.
- No LLM anywhere in the signal path.
- TradingView never emits a live signal. Research only.
- Features are computed incrementally as bars arrive, never by vectorising
  over a complete dataframe.
- Risk can veto or reduce an order. It can never originate one.
- All datetimes are timezone-aware and UTC internally. Never construct a naive datetime.

## Current state

Phase: 0 (repo skeleton, types, config loading, decision log schema)

## Working agreement

- One phase at a time. Do not start the next phase until the current exit criterion passes.
- The operator has no coding experience and is reviewing your output.
  Explain what each change does and why, in plain language.
- Do not write the property tests in `tests/properties/`. Those are hand-written
  by the operator by design — see architecture spec section 7.3.
```

Claude Code reads this automatically at the start of every session. Without it, it will happily rewrite on day 12 something it built on day 4.

### `docs/alignment.md` and `docs/architecture.md`

Create a `docs` folder and put your two existing documents in it. They currently live only as chat attachments. In the repository they're version-controlled, so their history becomes a record of how your thinking changed.

### `docs/state.md`

Create it with:

```markdown
# Current State

**Phase:** 0 — not started
**Last session:** [date]

## Decided recently
- Development environment set up; pytest green; repos on GitHub

## Blocked on
- Nothing

## Next
- Phase 0: repo skeleton, core types, config loading, decision log schema
```

Update the bottom three sections at the end of each working session — ten lines, sixty seconds. This is the file you paste at the start of a new chat.

Commit everything:

```
git add .
git commit -m "Add project documentation and Claude Code context"
git push
```

---

## Where you are now

- A project folder with a private Python environment
- Tests running, and you've seen one fail on purpose
- Two repositories, one public and one private, both backed up
- Context files so neither Claude Code nor a new chat starts from zero

Not written yet: any engine code. That's phase 0, and it's the next thing.

---

## If something goes wrong

**A command isn't recognized.** Usually PATH. Try `python -m <thing>` instead of `<thing>`, or close and reopen VS Code — newly installed programs often aren't visible to a terminal that was already open.

**`uv run pytest` says "no tests ran".** Check the file is inside `tests`, its name starts with `test_`, and the function names start with `test_`.

**VS Code can't find a package you installed.** The interpreter isn't pointed at `.venv`. Redo step 8, part 3.

**The terminal is in the wrong folder.** Look at the prompt — it tells you where you are. `cd C:\trading\engine` to get back.

**Something is genuinely stuck.** Copy the exact error text, all of it, into a chat. Error messages are ugly but specific, and the specific part is usually the answer. Don't paraphrase them.
