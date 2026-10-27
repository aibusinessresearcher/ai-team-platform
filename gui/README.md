# GUI Guide

Use the browser interface (GUI) to design Pure AI or human-in-the-loop studies and explore their workflow with **Mock agents**. Mock agents use prewritten dialogue; their displayed scores and token counts are demonstration values, not research findings or billed model usage.

**The GUI is not yet connected to the separate backend research engine.** A browser study does not launch that engine's scored task. For backend installation and results, see the package's [Start Here guide](../README.md#run-the-research-engine).

## Local demonstrations

Install and start the GUI below. No API key is needed with Mock agents, and your demonstration records are saved on your computer.

## Install and start locally

Install **Python 3.11** with pip and virtual-environment support. On Windows, include the Python launcher (`py`). Internet access is needed for installation; the Mock demonstration needs no API key or `.env` file.

Find the **`gui` folder inside `ai-team-platform`**, then open a terminal there:

- **Windows:** Open `gui` in File Explorer, click the address bar, type `powershell`, and press Enter.
- **macOS:** Open Terminal, type `cd ` with a trailing space, drag the `gui` folder from Finder into the window, then press Return.
- **Linux:** Use your file manager's **Open in Terminal** option in `gui`, if available. Otherwise, type `cd ` in Terminal, paste that folder's full path in double quotes, and press Enter.

The folder should contain `run.py` and `requirements.txt`. The commands create a GUI-only `.venv` and use its Python directly; no activation is needed. Keep the backend in its own environment.

**Windows PowerShell**

```powershell
Get-ChildItem
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

**macOS/Linux Terminal**

```bash
ls
python3.11 --version
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Keep the terminal open and visit **http://127.0.0.1:8000/**. You should see the AI Team Platform overview with links to both study builders. To return later, reopen a terminal in `gui` and run only the last command for your operating system.

Stop the server with **Ctrl+C in that terminal**. Closing the browser alone does not stop it.

## Try a Pure AI demonstration

1. Open **Pure AI Team Study Builder**. Enter a title and research question, then choose an interdependence structure and task.
2. For this walkthrough, set **Is this task scored?** to **No**, use **4 agents**, **2 discussion rounds**, **1 replication**, and concurrency **1**. Concurrency is how many replications run at once.
3. In **LLM Configuration**, click **Use Mock Demo** and leave the API key blank. Provider/model controls are part of the study builder; select Mock explicitly for this demonstration.
4. Review the configuration. **Download Protocol** saves your design choices. Click **Start Experiment** and wait for completion.
5. Open **View Results Dashboard**. Use **Download JSON** to save results and **View Runs** to read each transcript.

With these settings, expect one completed run and eight agent messages. Mock dialogue does not validate the effects of custom prompts, agent instructions, or other study choices. For example, **Hidden-Profile Decision Task** currently maps to Lost-at-Sea demonstration dialogue, not the backend's student-body-president task.

### Communication patterns in the GUI

| Selection | How the GUI organizes the conversation |
| --- | --- |
| Pooled | Agents contribute independently; no automatic aggregate ranking is calculated |
| Sequential | Each agent receives contributions from earlier agents in the sequence |
| Reciprocal | Agents receive their immediate neighbors' earlier contributions |
| Team / Comprehensive | Agents receive the team's earlier-round discussion |

These GUI patterns should not be assumed to match every procedure in the separate research engine.

## Try a participant session

1. Open **AI Team with Human-in-the-Loop Study Builder**. Choose four agents, two rounds, one session, and **Use Mock Demo**. Enter participant instructions and your intended role/recipient settings.
2. At Review & Launch, select **Create Participant Session**. Open the generated participant link in another tab.
3. Press **Begin Session** on the participant page. Observe the first round, then choose **Yes, Intervene**, select **All Agents**, type a short message, and send it. Round two begins automatically. Alternatively, continue without a message.
4. Return to **Researcher Dashboard** and click the session's row to expand its details. Download **Study Specification JSON**, **Conversation Transcript JSON**, and **Events Log CSV**.

The transcript includes agent and human messages; the event CSV records timestamped events. A localhost link works only on the computer running the server. Role and recipient labels alone do not establish research-grade permissions or message privacy. Use fictional information for demonstrations.

## Find and keep your records

For a normal local installation, these folders sit inside `gui`:

| Location | Contents |
| --- | --- |
| [data/batches/](data/batches/) | Pure AI configuration JSON and completed-run JSONL |
| [data/sessions/](data/sessions/) | Participant-session configuration JSON and event JSONL |

JSON is a readable data-file format; JSONL stores one record per line. Browser downloads go to its configured download location, usually Downloads.

Keep both the design protocol and run exports: selected study settings and executed demonstration content can differ. Use downloads rather than relying only on Experiment History. Save records before stopping the server; active jobs and participant sessions are held in memory and may not survive a restart.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Python command unavailable | Install Python 3.11 and its launcher/venv support, reopen the terminal, then repeat the version check. |
| `run.py` or a module cannot be found | Check that the terminal is in `gui`, beside `run.py` and `requirements.txt`, and use the `.venv` interpreter shown above. |
| Browser cannot open the local page | Keep the server terminal open, check for startup errors, and visit the exact address and port printed there. |
| Participant link fails after a restart | Create a new session while the server is running. Restarting does not restore an active session. |

If **port 8000 is already in use**, do not stop an unrelated application. From `gui`, use another port:

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

**macOS/Linux Terminal**

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open **http://127.0.0.1:8001/** instead. Stop it with Ctrl+C. If a local demonstration requests a researcher password, the default is `researcher` unless you changed `RESEARCHER_PASSWORD` in a local `.env` file; this is not a security arrangement for participant research.

Checks used Windows Python 3.11.4. macOS/Linux commands were reviewed but not executed on those systems.
