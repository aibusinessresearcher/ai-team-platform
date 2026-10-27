# AI Team Platform: Start Here

Study how AI teams share information, coordinate work, and respond to human intervention. The package contains a browser-based study builder (the GUI) and a separate Python research engine (the backend).

| What would you like to do? | Start here | LLM API key? |
| --- | --- | --- |
| Try demonstrations and participant sessions on your computer | [Run the GUI locally](#run-the-gui-locally) | No, with Mock agents |
| Run the scored student-body-president task with real models | [Run the research engine](#run-the-research-engine) | Only for an actual simulation |

**The GUI and backend research engine are not yet integrated.** Configuring or launching a study in the GUI does not launch the backend task. The two programs have separate installations and results.

For GUI demonstrations, select **Use Mock Demo** in LLM Configuration and leave the API key blank. Follow the [GUI walkthroughs](gui/README.md#try-a-pure-ai-demonstration).

## Walkthroughs

### Pure AI Walkthrough

![Pure AI study builder walkthrough](docs/demos/pure_ai_walkthrough.gif)

### Human-in-the-Loop Walkthrough

![Human-in-the-loop study builder and participant session walkthrough](docs/demos/human_in_the_loop_walkthrough.gif)

### Backend Walkthrough

![Backend research engine walkthrough](docs/demos/backend_walkthrough.gif)

## Prepare for local use

Extract the package into a writable folder. You should find `ai-team-platform`, containing `gui` and `backend`. Install **Python 3.11** with pip and virtual-environment support; include the Python launcher (`py`) on Windows. Internet access is needed to install packages.

Open a command window **in the package folder**, without typing a sample folder path:

- **Windows:** Open `ai-team-platform` in File Explorer. Click the address bar, type `powershell`, and press Enter. This opens PowerShell in the package folder, ready for the commands below.
- **macOS:** Open Terminal. Type `cd `, including the space, drag the `ai-team-platform` folder from Finder into the Terminal window, then press Return.
- **Linux:** Open `ai-team-platform` in your file manager and use **Open in Terminal**, if available. Otherwise, type `cd ` in Terminal, paste the folder's full path in double quotes, and press Enter.

Check the folder contents with `Get-ChildItem` on Windows or `ls` on macOS/Linux: both `gui` and `backend` should appear. Check Python with `py -3.11 --version` on Windows or `python3.11 --version` on macOS/Linux.

Each component gets its own `.venv`, a private set of Python packages. No activation command is needed.

## Run the GUI locally

Use the package-folder PowerShell or Terminal window opened above. The first command below enters the `gui` folder.

**Windows PowerShell**

```powershell
cd gui
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

**macOS/Linux Terminal**

```bash
cd gui
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Leave the terminal open and visit **http://127.0.0.1:8000/**. You should see the overview and the Pure AI and human-in-the-loop builders. Start with four agents, two rounds, one replication/session, and **Use Mock Demo**. See the [GUI guide](gui/README.md) for the walkthroughs, downloads, and alternative-port instructions.

**Mock dialogue, displayed scores, and token counts are illustrative, not research outcomes or billed model usage.** Stop the server with **Ctrl+C in its terminal**; closing the browser does not stop it. Save downloads before restarting.

## Run the research engine

If the GUI is running, leave its terminal open. On **Windows**, return to the `ai-team-platform` folder in File Explorer and open a **second PowerShell window** using the address-bar method above. On **macOS/Linux**, open a second Terminal window in the package folder using the method above. The first command below enters `backend`; do not run these commands from inside `gui`.

Install the backend and preview a one-round, AI-only condition:

**Windows PowerShell**

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -c "import teamwork; print('Backend import OK')"
.\.venv\Scripts\python.exe interactive_experiments/run_experiment.py task.max_rounds=1 task.human_interaction=false --cfg job
```

**macOS/Linux Terminal**

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -c "import teamwork; print('Backend import OK')"
.venv/bin/python interactive_experiments/run_experiment.py task.max_rounds=1 task.human_interaction=false --cfg job
```

Expect **Backend import OK**, then settings showing four agents, one round, `team` interdependence, and `human_interaction: false`. **The preview prints settings and exits without a model API call or an API key.** A paid run is not an installation check.

### Optional: run a real simulation

From `backend/`, copy [.env.example](backend/.env.example) to `.env` if it does not already exist. Replace the relevant placeholder key in a text editor. Do not overwrite an existing key file, name it `.env.txt`, or share it.

In [the task configuration](backend/interactive_experiments/configs/task/student_body_president.yaml), set `provider` and `model` under `backend` to match a model available to your account:

| Service | `provider` | Key in `.env` |
| --- | --- | --- |
| Google Gemini, directly | `gemini_direct` | `GEMINI_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |

Repeat the preview after edits. **Only when ready to incur possible API charges**, run without `--cfg job`:

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe interactive_experiments/run_experiment.py task.max_rounds=1 task.human_interaction=false
```

**macOS/Linux Terminal**

```bash
.venv/bin/python interactive_experiments/run_experiment.py task.max_rounds=1 task.human_interaction=false
```

The terminal shows agent contributions and the answer/score. Keep four agents for the supplied prompt. These command overrides do not change the YAML defaults of two rounds with terminal human input enabled. All agents use the same provider/model. Terminal human input is separate from the GUI participant interface.

Press **Ctrl+C** to interrupt a running simulation; unfinished runs may not save final results. Use fictional information for demonstrations and follow your institution's requirements before conducting participant research.

## Find backend results

After a successful simulation, open **`ai-team-platform/backend/outputs/`** in your file browser. Open the run's date folder, then its time-named folder. It contains:

| File or folder | What it contains |
| --- | --- |
| `conversation.json` | Each agent's recorded conversation |
| `results.json` | Submitted rankings and scores, by round; pooled runs are saved by agent |
| `.hydra/` | Configuration and command overrides used for that run; this folder may be hidden |
| `run_experiment.log` | The run's log file |

The backend score is **L1 ranking error**: 0 is exact, and lower is better. The maximum is 8 for a valid four-candidate ranking. It is not the GUI's illustrative agreement score. The standard runner does not automatically aggregate pooled rankings or save token/cost summary tables.

## First-run help

- **Python command unavailable:** Install Python 3.11 and its launcher/venv support, reopen the terminal, and repeat the version check.
- **File or module not found:** Use the correct component folder and its `.venv` Python. GUI commands run beside `run.py`; backend commands beside `pyproject.toml`.
- **Port 8000 busy or participant session problems:** See [GUI troubleshooting](gui/README.md#troubleshooting).
- **Backend key, model, or quota error:** Check `.env`, provider/model settings, and account access/credit before retrying a paid run. Preview again first.
- **Model rejects temperature:** Add `task.backend.temperature=null` to both preview and run commands to omit it.

Offline checks used Windows Python 3.11.4. macOS/Linux commands were reviewed but not executed on those systems.

## License and provenance

See [LICENSE](LICENSE) for the MIT license and retained copyright notices. Portions of the backend build on code by Pappu et al.; this attribution concerns those backend portions, not the GUI.
