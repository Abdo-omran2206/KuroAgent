# 🤖 KURO 2.0 - Autonomous Terminal AI System Assistant

**KURO 2.0** is an autonomous, system-level AI engineer and terminal assistant inspired by Claude Code and Open Interpreter. It features a multi-step **ReAct execution loop**, intelligent **Multi-Key & Multi-Model Pools** with automatic rate-limit failover, persistent **SQLite Brain**, **Neural TTS Voice**, **Multimodal Vision**, **Task Planning Mode**, **Global Windows Hotkey**, and a modern Rich terminal experience.

---

## 🌟 Level 2 Core Capabilities

- **🔄 Multi-Step Autonomous ReAct Loop:** Executes complex sequential tasks (up to 10 automated steps: analyze ➔ file operations ➔ shell commands ➔ code executions ➔ verification).
- **🤖 Full Self-Access & Self-Modification:** KURO has full access to its own codebase (`core/`, `tools/`, `main.py`, `brain/`). When instructed to add features, fix bugs, or alter system behavior, it inspects and updates its own source files.
- **🔔 Windows Toast Notifications (`/notify`):** Native Windows Toast notifications and optional webhooks for alerting when tasks finish.
- **🗄️ Database Explorer Tool (`/db`):** Introspect SQLite database structures (`brain/kuro.db`), view tables, describe columns, and run SQL queries.
- **🌐 Browser Automation (Playwright & Headless):** Automated link clicking, form interaction, web scraping (`/browse`), and page content extraction.
- **🧠 Persistent Brain Storage (`brain/`):** Integrated SQLite database (`brain/kuro.db`), Markdown personality profile (`brain/personality.md`), task plans, notes (`brain/notes/`), and skills (`brain/skills/`).
- **🎙️ Ultra-Realistic Neural Voice:** Built-in `edge-tts` voice engine with 8 realistic human speakers (Ava, Andrew, Emma, Brian, Guy, Jenny, Ryan, Sonia) and live typewriter streaming.
- **📋 Task Planning Mode (`/plan`):** Decomposes high-level goals into multi-step execution plans tracked in SQLite database.
- **⌨️ Global Windows Hotkey (`Ctrl+Alt+K`):** Win32 background listener that brings KURO to the foreground instantly from any application.
- **🔑 Multi-Key & Multi-Model Resource Pools:** Supply multiple API keys (`GEMINI_API_KEYS=k1,k2,k3`). Automatically rotates on rate limits or cascades across providers.
- **🛡️ Auto-Git Checkpoints & `/undo`:** Automatic snapshots before modifying files, allowing instant one-command rollbacks.

---

## 📁 Project Architecture

```
KURO/
├── main.py                     # Main CLI REPL Entry Point & Interface
├── requirements.txt            # Project Dependencies
├── README.md                   # Documentation
├── .env / .env.example         # Multi-key & multi-provider configuration
├── .gitignore                  # Git specification
│
├── core/                       # Core AI Assistant Engine
│   ├── __init__.py            # Package Exporter
│   ├── config.py              # KeyPools, Fallback Chains, & Paths
│   ├── agent.py               # Autonomous ReAct Agent Loop (Self-Access & Self-Modification)
│   ├── llm.py                 # Multi-Provider Failover & Vision Dispatcher
│   ├── memory.py              # Memory interface & automatic summarizer
│   ├── memory_db.py           # SQLite Database Brain interface (kuro.db)
│   └── personality.py         # Personality profile loader & trait sync
│
├── tools/                      # Autonomous Action Tools
│   ├── __init__.py            # Package Exporter
│   ├── system.py              # Subprocess command execution & security checks
│   ├── files.py               # Pathlib file operations, unified diffs, & SQL queries
│   ├── notifier.py            # Native Windows Toast notifications & webhooks
│   ├── db_explorer.py         # DB Introspection, table schema viewer, & queries
│   ├── planner.py             # Task planning engine & multi-step execution
│   ├── hotkey.py              # Win32 global hotkey listener (Ctrl+Alt+K)
│   ├── voice.py               # Edge-TTS Neural voice & audio player
│   ├── vision.py              # Gemini multimodal vision analysis
│   ├── web.py                 # Web search & URL fetcher
│   ├── web_browser.py         # Playwright & urllib headless browser engine
│   ├── git_checkpoint.py      # Git auto-checkpoints & rollback
│   ├── interpreter.py         # Embedded Python interpreter engine
│   └── self_improve.py        # Custom skills persistence
│
├── brain/                      # Persistent Brain Storage
│   ├── kuro.db                # SQLite Brain Database
│   ├── personality.md         # Persistent Personality Profile
│   ├── memory.json            # Memory cache
│   ├── kuro_prompt.txt        # Base system prompt template
│   ├── notes/                 # User & KURO Markdown Notes
│   └── skills/                # Self-learned routines & skills
│
├── build/                      # Build & Packaging Tools
│   ├── build_exe.py           # PyInstaller automated executable builder
│   ├── setup_installer.iss    # Inno Setup Windows installer script
│   └── KURO.spec              # PyInstaller specification
│
├── tests/                      # Verification & Test Suite
│   ├── test_all.py            # Master regression test suite
│   └── test_hotkey.py         # Hotkey unit test
│
└── assets/                     # Media & Graphics
    └── kuro_icon.png          # App Icon
```

---

## ⚡ Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Keys
Add your keys using the CLI or `.env`:
```bash
/key YOUR_GEMINI_KEY
/key groq YOUR_GROQ_KEY
```

### 3. Launch KURO 2.0
```bash
python main.py
```

---

## 🛠️ Building Standalone Executable & Windows Installer (`build/`)

### 📦 One-Click Batch Build Scripts
- **`build_all.bat`**: Builds both the PyInstaller executable AND the Inno Setup Windows installer in one step.
- **`build.bat`**: Compiles standalone `dist/KURO.exe` executable with embedded `.ico` icon.
- **`build_installer.bat`**: Compiles `dist/KURO_v2_Setup.exe` Windows setup wizard using Inno Setup (`ISCC.exe`).

```cmd
:: Full build (Exe + Installer)
build_all.bat

:: Build standalone EXE only
build.bat

:: Build setup installer wizard only
build_installer.bat
```

---

## 💻 Slash Commands Reference

| Command | Action | Example |
|---------|--------|---------|
| `/notify <title> \| <msg>` | Send native Windows Toast notification | `/notify Task Completed \| Finished build` |
| `/db [db_path]` | Introspect & view SQLite database tables | `/db brain/kuro.db` |
| `/plan <goal>` | Generate multi-step task execution plan | `/plan Build automated crypto price monitor` |
| `/sql <query>` | Execute SQL query/script on `brain/kuro.db` | `/sql SELECT * FROM conversations LIMIT 5;` |
| `/notes <name.md> <content>` | Write structured Markdown note to `brain/notes/` | `/notes market_notes.md BTC price 95k` |
| `/hotkey` | View status of global Windows hotkey (`Ctrl+Alt+K`) | `/hotkey` |
| `/voice` | Toggle TTS output / list voices (`/voice list`) / set voice (`/voice andrew`) | `/voice list` |
| `/listen` | Microphone speech-to-text input mode | `/listen` |
| `/see <path>` | Multimodal image vision analysis | `/see C:\chart.png explain trends` |
| `/browse <url>` | Headless web browser scraping | `/browse https://news.ycombinator.com` |
| `/pool` | View live KeyPool status, 429 rate limit cooldowns | `/pool` |
| `/models` | View fallback model chain for current provider | `/models` |
| `/undo` | Rollback last automated file modifications via Git | `/undo` |
| `/search <query>` | Perform a live web search | `/search OpenAI news 2026` |
| `/status` | View active configuration and safety modes | `/status` |
| `/memory` | Inspect conversation history & brain summary | `/memory` |
| `/clear` | Clear saved conversation memory | `/clear` |
| `!command` | Run direct shell command (e.g. `!git status`) | `!git status` |
| `exit` / `quit` | Exit KURO session | `exit` |
