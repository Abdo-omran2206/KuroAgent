import sys
import os
import json
import time
import threading
import typer

# Suppress pygame startup banner before any import triggers it
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

# Fix for rich._unicode_data version resolution (prevents No module named 'rich._unicode_data.unicode17-0-0')
os.environ.setdefault("UNICODE_VERSION", "15.1.0")

# Force UTF-8 output on Windows so Rich spinners and Unicode chars work
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Defensive compatibility patch for Rich unicode data tables
try:
    import rich._unicode_data
    _orig_rich_unicode_load = rich._unicode_data.load
    def _safe_rich_unicode_load(unicode_version="auto"):
        try:
            return _orig_rich_unicode_load(unicode_version)
        except Exception:
            try:
                return _orig_rich_unicode_load("15.1.0")
            except Exception:
                from rich.cells import CellTable
                return CellTable(frozenset())
    rich._unicode_data.load = _safe_rich_unicode_load
except Exception:
    pass

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich.live import Live
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich import box

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import PathCompleter, Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.lexers import SimpleLexer

from core import config
from core import memory
from core.llm import ask_llm
from core.agent import KuroAgent
from tools.system import run_command
from tools.git_checkpoint import rollback_checkpoint
from tools.web import search_web
from tools.voice import set_voice_enabled, is_voice_enabled, listen_microphone, speak_text, set_voice_name, list_available_voices
from tools.files import execute_sql_query, write_md_note
from tools.planner import create_task_plan, get_active_plan, execute_plan_step, format_plan_table
from tools.hotkey import start_global_hotkey_listener, focus_kuro_window
from tools.self_improve import save_learned_skill, list_learned_skills
from tools.notifier import send_toast_notification
from tools.db_explorer import explore_database

# ─────────────────────────────────────────────────────────
# App & Console Setup
# ─────────────────────────────────────────────────────────
app = typer.Typer(invoke_without_command=True, add_completion=False)
console = Console(highlight=False)

# ─────────────────────────────────────────────────────────
import html

# ─────────────────────────────────────────────────────────
# KURO Cat ASCII Logo
# ─────────────────────────────────────────────────────────
CAT_LOGO = r"""[bold cyan]
       _                        
       \`*-.                    
        )  _`-.                 
       .  : `. .                
       : _   '  \               
       ; *` _.   `*-._          
       `-.-'          `-.       
         ;       `       `.     
         :.       .        \    
         . \  .   :   .-'   .   
         '  `+.;  ;  '      :   
         :  '  |    ;       ;-. 
         ; '   : :`-:     _.`* ;
       .*' /  .*' ; .*`- +'  `*' 
      `*-*   `*-*  `*-*'[/bold cyan]"""

KURO_TITLE = "[bold cyan]K[/][bold white]U[/][bold cyan]R[/][bold white]O[/]"

BANNER_LINES = [
    "",
    f"   {KURO_TITLE}  [dim]v2.0[/dim]  [bold cyan]Autonomous Terminal Intelligence[/]",
    "   [dim]ReAct 2.0  |  Context Engine  |  Encrypted Vault  |  Sandbox Guard  |  Integrations[/]",
    "",
]

COMMAND_LIST = [
    "/help", "/status", "/pool", "/models",
    "/key", "/undo", "/clear", "/memory",
    "/search", "/see", "/browse", "/voice", "/listen",
    "/learn", "/skills", "/plan", "/sql", "/notes", "/hotkey",
    "/notify", "/db", "/dir", "/project", "/integrations", "/connect", "/disconnect", "/tasks", "/metrics",
    "/vault", "/sandbox", "/safe",
    "exit", "quit"
]

SLASH_DESCRIPTIONS = {
    "/help":         "Show command reference & capabilities",
    "/status":       "Active provider, model, & safe mode status",
    "/safe":         "Toggle Safe Mode & permission prompts: /safe <on|off|toggle|status|allow <tool>>",
    "/pool":         "API key pool & cooldown status",
    "/models":       "Model fallback priority chain",
    "/key":          "Add API key: /key <KEY> or /key <provider> <KEY>",
    "/undo":         "Rollback last automated file changes",
    "/clear":        "Reset active conversation memory",
    "/memory":       "View stored conversation history & brain summary",
    "/search":       "Live web search: /search <query>",
    "/see":          "Vision analysis: /see <image_path> [prompt]",
    "/browse":       "Headless web automation: /browse <url>",
    "/voice":        "Toggle TTS | /voice list | /voice <name>",
    "/listen":       "Microphone Speech-to-Text input mode",
    "/learn":        "Save custom routine: /learn <skill_name> <steps>",
    "/skills":       "List all KURO self-learned skills",
    "/plan":         "Task planning mode: /plan <goal_description>",
    "/sql":          "Execute SQL query: /sql <query_or_script>",
    "/notes":        "Write MD note: /notes <filename.md> <content>",
    "/hotkey":       "Global hotkey status (Ctrl+Alt+K / Ctrl+Shift+K)",
    "/notify":       "Send Windows Toast: /notify <title> | <message>",
    "/db":           "Database explorer: /db [db_path]",
    "/dir":          "List directory contents: /dir [path]",
    "/project":      "Show current project profile & architecture hints",
    "/integrations": "Manage connected services (GitHub, Google Drive)",
    "/connect":      "Connect service token: /connect <github|drive|email> <TOKEN>",
    "/disconnect":   "Disconnect service: /disconnect <github|drive|email>",
    "/tasks":        "List active/historical tasks & state lifecycle",
    "/metrics":      "View execution analytics (tokens, tool calls, costs)",
    "/vault":        "Encrypted credential vault: /vault <set|get|list|delete|lock|unlock|migrate>",
    "/sandbox":      "Execution guard & AST sandbox: /sandbox <status|on|off|toggle|clean|check>",
}

# ─────────────────────────────────────────────────────────
# Prompt Toolkit Style — Modern Dark Terminal Theme
# ─────────────────────────────────────────────────────────
PT_STYLE = Style.from_dict({
    # Prompt label
    "prompt.user":      "#00d7ff bold",
    "prompt.gt":        "#555555",
    # Input text
    "":                 "#e0e0e0",
    # Auto-suggest ghost text
    "auto-suggest":     "#444444 italic",
    # Completion menu
    "completion-menu.completion":          "bg:#1a1a2e #c0c0c0",
    "completion-menu.completion.current":  "bg:#00d7ff #000000 bold",
    "completion-menu.meta.completion":     "bg:#111111 #888888",
    "completion-menu.meta.completion.current": "bg:#007aa8 #ffffff",
    "scrollbar.background": "bg:#111111",
    "scrollbar.button":     "bg:#333333",
    # Validation error
    "validation-toolbar": "bg:#800000 #ffffff",
    # Bottom bar
    "bottom-toolbar": "bg:#111111 #555555",
})

# ─────────────────────────────────────────────────────────
# Smart Completer with descriptions
# ─────────────────────────────────────────────────────────
class KuroCompleter(Completer):
    """Combines slash commands with autocomplete and path completion."""
    def __init__(self):
        self.path_completer = PathCompleter(only_directories=False, expanduser=True)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        word = document.get_word_before_cursor()

        # Slash command completion
        if text.startswith("/"):
            for cmd in COMMAND_LIST:
                if cmd.startswith(text.split()[0] if text.split() else "/"):
                    raw_desc = SLASH_DESCRIPTIONS.get(cmd, "")
                    desc = html.escape(raw_desc)
                    cmd_escaped = html.escape(cmd)
                    yield Completion(
                        cmd,
                        start_position=-len(text.split()[0] if text.split() else ""),
                        display=HTML(f"<ansibrightcyan>{cmd_escaped}</ansibrightcyan>"),
                        display_meta=HTML(f"<ansidarkgray>{desc}</ansidarkgray>")
                    )
            return

        # Shell command path completion after '!'
        if text.startswith("!"):
            for c in self.path_completer.get_completions(document, complete_event):
                yield c
            return

        # Regular chat — suggest /commands for quick access
        if not text:
            for cmd in COMMAND_LIST:
                raw_desc = SLASH_DESCRIPTIONS.get(cmd, "")
                desc = html.escape(raw_desc)
                cmd_escaped = html.escape(cmd)
                yield Completion(
                    cmd,
                    start_position=0,
                    display=HTML(f"<ansibrightcyan>{cmd_escaped}</ansibrightcyan>"),
                    display_meta=HTML(f"<ansidarkgray>{desc}</ansidarkgray>")
                )


# ─────────────────────────────────────────────────────────
# Bottom toolbar
# ─────────────────────────────────────────────────────────
def get_bottom_toolbar():
    provider = html.escape(config.get_active_provider().upper())
    model = html.escape(config.get_active_model())
    safe = "SAFE" if config.SAFE_MODE else "UNSAFE"
    return HTML(
        f" <b><ansibrightcyan>KURO</ansibrightcyan></b>  "
        f"<ansidarkgray>|</ansidarkgray>  "
        f"<ansibrightgreen>{provider}</ansibrightgreen>  "
        f"<ansidarkgray>{model}</ansidarkgray>  "
        f"<ansidarkgray>|</ansidarkgray>  "
        f"<ansiyellow>{safe}</ansiyellow>  "
        f"<ansidarkgray>|  Tab: complete  |  Up/Down: history  |  /help: commands</ansidarkgray>"
    )


# ─────────────────────────────────────────────────────────
# Key Bindings
# ─────────────────────────────────────────────────────────
kb = KeyBindings()

@kb.add("c-l")          # Ctrl+L → clear screen
def _clear(event):
    os.system("cls" if os.name == "nt" else "clear")
    _print_header()

@kb.add("c-c")          # Ctrl+C → interrupt gracefully
def _interrupt(event):
    event.app.exit()


# ─────────────────────────────────────────────────────────
# UI Rendering Helpers
# ─────────────────────────────────────────────────────────
def _print_header():
    """Renders the full KURO startup screen: cat logo + title + status."""
    console.clear()

    # Side-by-side: Cat + Title
    cat_panel = Panel(
        CAT_LOGO.strip(),
        border_style="cyan",
        title="[bold cyan]KURO[/]",
        padding=(0, 1),
    )
    title_text = Text.assemble(
        "\n",
        ("  KURO ", "bold cyan"),
        ("v2.0\n", "dim"),
        ("  Autonomous Terminal Intelligence\n\n", "bold white"),
        ("  Your local AI system assistant.\n", "dim"),
        ("  Trading  |  Coding  |  Research  |  System Ops\n", "dim"),
    )
    title_panel = Panel(title_text, border_style="bright_black", padding=(0, 2))

    console.print(Columns([cat_panel, title_panel], equal=False, expand=False))
    print_status_banner()
    console.print(Rule("[dim]Tab autocomplete  |  /help commands  |  Ctrl+L clear  |  exit to quit[/dim]", style="bright_black"))
    console.print()


def print_status_banner():
    """Compact, inline status bar."""
    provider = config.get_active_provider()
    model = config.get_active_model(provider)
    pool = config.KEY_POOLS.get(provider)
    key_count = len(pool.keys) if pool else 0
    safe = "[green]SAFE[/green]" if config.SAFE_MODE else "[red]UNSAFE[/red]"
    git = "[green]GIT-ON[/green]" if config.AUTO_GIT_CHECKPOINTS else "[dim]GIT-OFF[/dim]"

    status_text = (
        f" [bold cyan]{provider.upper()}[/]  [dim]|[/]  "
        f"[yellow]{model}[/]  [dim]|[/]  "
        f"[magenta]{key_count} key(s)[/]  [dim]|[/]  "
        f"{safe}  [dim]|[/]  {git}"
    )
    console.print(Panel(status_text, border_style="bright_black", padding=(0, 1)))



def _typewriter_print(text: str, delay: float = 0.018):
    """
    Streams text to terminal with a typewriter effect.
    - Normal text: typed word-by-word with small delay
    - Code blocks (```...```): printed instantly so formatting isn't broken
    - A blinking cursor ▌ trails the output
    """
    import re as _re

    # Split on code block boundaries so we can handle them differently
    segments = _re.split(r'(```.*?```)', text, flags=_re.DOTALL)

    for segment in segments:
        if segment.startswith("```"):
            # Print code blocks instantly (preserve formatting)
            console.print(Syntax(
                segment.strip("`").lstrip("\n"),
                "python",
                theme="monokai",
                line_numbers=False,
                word_wrap=True,
            ))
        else:
            # Stream plain text word-by-word
            words = segment.split(" ")
            for i, word in enumerate(words):
                # Handle newlines inside the word
                parts = word.split("\n")
                for j, part in enumerate(parts):
                    if part:
                        console.print(part + " ", end="", highlight=False)
                    if j < len(parts) - 1:
                        console.print()  # actual newline
                time.sleep(delay)


def print_kuro_response(response: str):
    """Renders KURO's final answer with a live typewriter effect.
    Voice (if enabled) plays in background while text streams simultaneously.
    """
    from tools.voice import is_voice_enabled, speak_text

    console.print()
    console.print(Rule("[bold cyan]KURO[/bold cyan]", style="cyan", align="left"))

    # Start voice in background thread (non-blocking) while typing plays
    if is_voice_enabled():
        voice_thread = threading.Thread(
            target=speak_text, args=(response,), kwargs={"async_mode": False}, daemon=True
        )
        voice_thread.start()

    # Typewriter effect for the response
    _typewriter_print(response)

    console.print()
    console.print(Rule(style="bright_black"))
    console.print()



def print_shell_output(cmd: str, res: dict):
    """Renders shell command output in a styled panel."""
    console.print(f"\n[bold yellow]$ {cmd}[/]")
    if res.get("stdout"):
        console.print(Panel(
            res["stdout"].strip(),
            title="[bold green]stdout[/]",
            border_style="green",
            padding=(0, 1)
        ))
    if res.get("stderr"):
        console.print(Panel(
            res["stderr"].strip(),
            title="[bold red]stderr[/]",
            border_style="red",
            padding=(0, 1)
        ))


def display_pool_status():
    """Rich table of all key pools."""
    summaries = config.get_pool_status_summary()
    table = Table(
        title="KURO  Resource Pool Status",
        border_style="cyan",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Provider", style="bold cyan", min_width=12)
    table.add_column("Keys", style="white", justify="center")
    table.add_column("Active", style="bold green", justify="center")
    table.add_column("Cooling (429)", style="red", justify="center")
    table.add_column("Model Fallback Chain", style="yellow", min_width=40)

    for s in summaries:
        models_str = " -> ".join(s["models"][:3])
        if len(s["models"]) > 3:
            models_str += f"  [dim](+{len(s['models'])-3} more)[/dim]"
        table.add_row(
            s["provider"],
            str(s["total_keys"]),
            str(s["active_keys"]),
            str(s["cooling_keys"]),
            models_str,
        )
    console.print()
    console.print(table)
    console.print()


def display_help():
    """Sectioned, modern styled help panel with command categories and usage examples."""
    sections = [
        ("⚙️  Core & Configuration", [
            ("/status",      "Show active LLM provider, model, & safe mode status", "Type [cyan]/status[/cyan]"),
            ("/safe",        "Toggle Safe Mode & permission prompts (on/off/allow)", "[cyan]/safe off[/cyan] | [cyan]/safe allow execute_python[/cyan]"),
            ("/pool",        "View API key pool rotation & rate limit cooldowns",    "Type [cyan]/pool[/cyan]"),
            ("/models",      "View model fallback chain for active provider",       "Type [cyan]/models[/cyan]"),
            ("/key",         "Add API key to provider pool & persist to .env",       "[cyan]/key <KEY>[/cyan] or [cyan]/key groq <KEY>[/cyan]"),
            ("/undo",        "Rollback last automated file changes via Git",        "Type [cyan]/undo[/cyan]"),
            ("/hotkey",      "Global Win32 Hotkey Status (Ctrl+Alt+K)",             "Type [cyan]/hotkey[/cyan]"),
            ("!<cmd>",       "Direct shell command bypass (executes locally)",      "[cyan]!git status[/cyan] or [cyan]!dir[/cyan]"),
        ]),
        ("📁  Workspace & Project Awareness", [
            ("/dir",         "List directory contents (with path Tab autocompletion)","[cyan]/dir [path][/cyan]"),
            ("/project",     "Inspect project profile, tech stack, entry points",   "Type [cyan]/project[/cyan]"),
            ("/notes",       "Write structured Markdown note to brain/notes/",      "[cyan]/notes notes.md content[/cyan]"),
            ("/db",          "Explore SQLite database schema, tables, and rows",    "[cyan]/db [db_path][/cyan]"),
            ("/sql",         "Execute raw SQL query or script on SQLite database",  "[cyan]/sql SELECT * FROM tasks;[/cyan]"),
        ]),
        ("🧠  Memory, Tasks & Metrics", [
            ("/memory",      "Inspect persistent conversation memory and summary",  "Type [cyan]/memory[/cyan]"),
            ("/clear",       "Reset active conversation working memory",            "Type [cyan]/clear[/cyan]"),
            ("/plan",        "Task Planning Mode (decompose goal into steps)",      "[cyan]/plan build a trading bot[/cyan]"),
            ("/tasks",       "List active and historical task state lifecycles",    "Type [cyan]/tasks[/cyan]"),
            ("/metrics",     "View execution analytics (tokens, tool calls, costs)", "Type [cyan]/metrics[/cyan]"),
        ]),
        ("🛠️  Autonomous Tools & Perception", [
            ("/search",      "Live web search (DuckDuckGo + Wikipedia)",            "[cyan]/search OpenAI news 2026[/cyan]"),
            ("/see",         "Multimodal Vision & Image Analysis",                  "[cyan]/see C:\\image.png explain[/cyan]"),
            ("/browse",      "Headless web browser automation & scraping",          "[cyan]/browse https://news.ycombinator.com[/cyan]"),
            ("/voice",       "Neural TTS Voice output (toggle / list / switch)",    "[cyan]/voice[/] | [cyan]/voice list[/] | [cyan]/voice andrew[/]"),
            ("/listen",      "Microphone Speech-to-Text voice input mode",          "Type [cyan]/listen[/cyan]"),
            ("/notify",      "Omni-channel smart notifier (Toast, Telegram, Discord)", "[cyan]/notify --channel telegram Hello[/cyan] | [cyan]/notify test[/cyan]"),
        ]),
        ("🌐  Integrations & Skills", [
            ("/integrations","List connected services (Telegram, Discord, GitHub, Drive, Email)", "Type [cyan]/integrations[/cyan]"),
            ("/connect",     "Connect external service & persist to Encrypted Vault", "[cyan]/connect telegram <TOKEN> [CHAT_ID][/cyan]"),
            ("/disconnect",  "Disconnect an external service integration",          "[cyan]/disconnect <service>[/cyan]"),
            ("/learn",       "Save custom procedural routine (Self-Improvement)",   "[cyan]/learn test_flow Run tests[/cyan]"),
            ("/skills",      "List all self-learned skills and workflows",          "Type [cyan]/skills[/cyan]"),
        ]),
        ("🔒  Security & Privacy", [
            ("/vault",       "Encrypted credential vault manager (DPAPI / AES-256)", "[cyan]/vault list[/cyan] | [cyan]/vault set <K> <V>[/cyan]"),
            ("/sandbox",     "AST Code Safety Analyzer & Execution Guardrails",      "[cyan]/sandbox status[/cyan] | [cyan]/sandbox toggle[/cyan]"),
        ]),
        ("🚪  Session Management", [
            ("/help",        "Display this categorized command reference",          "Type [cyan]/help[/cyan]"),
            ("exit / quit",  "Terminate active KURO session",                       "Type [cyan]exit[/cyan] or [cyan]quit[/cyan]"),
        ]),
    ]

    console.print()
    console.print(Rule("[bold cyan]KURO 2.0  Categorized Command Reference[/bold cyan]", style="cyan"))
    console.print()

    for sec_title, cmd_rows in sections:
        table = Table(
            title=sec_title,
            title_style="bold magenta",
            border_style="cyan",
            box=box.ROUNDED,
            show_lines=False,
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("Command", style="bold cyan", width=18)
        table.add_column("Capability & Action", style="white", ratio=3)
        table.add_column("How to Use / Example", style="yellow", ratio=3)

        for cmd, desc, usage in cmd_rows:
            table.add_row(cmd, desc, usage)

        console.print(table)
        console.print()

    console.print(
        Panel(
            "[dim]💡 Shortcuts & Tips:\n"
            "• [bold]Tab Completion:[/bold] Press [bold]Tab[/bold] to autocomplete slash commands and directory paths.\n"
            "• [bold]Command History:[/bold] Press [bold]Up / Down arrows[/bold] to navigate previous commands.\n"
            "• [bold]Clear Terminal Screen:[/bold] Press [bold]Ctrl+L[/bold] to clear the view without losing conversation memory.\n"
            "• [bold]Self-Awareness:[/bold] KURO inspects its own tools dynamically. Ask [bold]'What tools do you have?'[/bold] anytime.[/dim]",
            title="Interactive CLI Tips",
            border_style="bright_black",
            padding=(0, 2),
        )
    )
    console.print()


# ─────────────────────────────────────────────────────────
# Thinking Spinner (blocks until done)
# ─────────────────────────────────────────────────────────
def run_with_spinner(fn, *args, **kwargs):
    """Runs fn(*args) with a live animated spinner, returns result."""
    result_holder = [None]
    error_holder = [None]

    def _worker():
        try:
            result_holder[0] = fn(*args, **kwargs)
        except Exception as e:
            error_holder[0] = e

    thread = threading.Thread(target=_worker)
    thread.start()

    spinner_frames = ["[    ]", "[=   ]", "[==  ]", "[=== ]", "[====]", "[ ===]", "[  ==]", "[   =]"]
    idx = 0
    while thread.is_alive():
        frame = spinner_frames[idx % len(spinner_frames)]
        sys.stdout.write(f"\r  [bold cyan]{frame}[/bold cyan]  [dim]KURO thinking...[/dim]   ")
        sys.stdout.flush()
        time.sleep(0.12)
        idx += 1
        # Use rich live to avoid encoding issues
        try:
            console.print(f"\r  [cyan]{frame}[/] [dim]KURO thinking...[/dim]   ", end="")
        except Exception:
            pass

    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()

    thread.join()
    if error_holder[0]:
        raise error_holder[0]
    return result_holder[0]


# ─────────────────────────────────────────────────────────
# Main App Entry
# ─────────────────────────────────────────────────────────
@app.command()
def main(
    query: str = typer.Argument(None, help="Optional single request to execute non-interactively"),
    provider: str = typer.Option(None, "--provider", "-p", help="Override LLM provider"),
    model:    str = typer.Option(None, "--model",    "-m", help="Override LLM model"),
):
    """KURO 2.0 — Autonomous Terminal AI System Assistant"""
    if provider:
        os.environ["KURO_PROVIDER"] = provider.lower()

    agent = KuroAgent()
    if model:
        agent.model = model

    # ── Single-shot mode ──────────────────────────────────
    if query:
        if query.startswith("!"):
            cmd = query[1:].strip()
            res = run_command(cmd)
            print_shell_output(cmd, res)
        else:
            with Live(Spinner("dots", text="[cyan]KURO thinking...[/]"), refresh_per_second=12, console=console):
                response = agent.run(query)
            print_kuro_response(response)
        sys.exit(0)

    # ── Interactive REPL ──────────────────────────────────
    start_global_hotkey_listener()
    _print_header()

    from core.paths import HISTORY_FILE
    session = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=KuroCompleter(),
        style=PT_STYLE,
        key_bindings=kb,
        bottom_toolbar=get_bottom_toolbar,
        refresh_interval=1.0,
        enable_history_search=True,
        complete_while_typing=True,
        mouse_support=False,
        wrap_lines=True,
        lexer=SimpleLexer("class:"),
    )

    while True:
        try:
            # Build dynamic prompt
            provider_label = config.get_active_provider().upper()
            prompt_tokens = HTML(
                f'<ansibrightblack>[</ansibrightblack>'
                f'<ansibrightcyan>KURO</ansibrightcyan>'
                f'<ansibrightblack>|</ansibrightblack>'
                f'<ansidarkgray>{provider_label}</ansidarkgray>'
                f'<ansibrightblack>]</ansibrightblack> '
                f'<ansiwhite>></ansiwhite> '
            )

            user_input = session.prompt(prompt_tokens).strip()

            if not user_input:
                continue

            # Exit
            if user_input.lower() in ("exit", "quit", ":q", "bye"):
                console.print()
                console.print(Rule("[bold cyan]KURO session ended. Goodbye![/bold cyan]", style="cyan"))
                console.print()
                break

            # ── Slash commands ─────────────────────────────
            if user_input.startswith("/"):
                parts = user_input.split()
                cmd = parts[0].lower()

                if cmd == "/help":
                    display_help()

                elif cmd == "/status":
                    console.print()
                    print_status_banner()

                elif cmd == "/pool":
                    display_pool_status()

                elif cmd == "/models":
                    prov = config.get_active_provider()
                    chain = config.MODEL_CHAINS.get(prov, [])
                    console.print()
                    table = Table(title=f"Model Fallback Chain: {prov.upper()}", border_style="cyan", box=box.ROUNDED)
                    table.add_column("Priority", justify="center", style="dim")
                    table.add_column("Model", style="yellow")
                    for i, m in enumerate(chain, 1):
                        badge = "[bold green](active)[/]" if i == 1 else ""
                        table.add_row(str(i), f"{m}  {badge}")
                    console.print(table)
                    console.print()

                elif cmd == "/undo":
                    console.print("[bold yellow]Rolling back last file changes...[/]")
                    res = rollback_checkpoint()
                    if res.get("success"):
                        console.print(f"[bold green]  [OK] {res.get('stdout')}[/]")
                    else:
                        console.print(f"[bold red]  [FAIL] {res.get('error')}[/]")

                elif cmd == "/search":
                    if len(parts) < 2:
                        console.print("[yellow]  Usage: /search <query>[/]")
                    else:
                        q = " ".join(parts[1:])
                        console.print(f"[bold yellow]  Searching:[/] {q}")
                        res = search_web(q)
                        results = res.get("results", [])
                        table = Table(border_style="cyan", box=box.SIMPLE, show_header=False, padding=(0, 1))
                        table.add_column("", style="dim")
                        table.add_column("", style="white")
                        for i, r in enumerate(results[:5], 1):
                            table.add_row(
                                f"[cyan]{i}.[/]",
                                f"[white]{r.get('snippet', '')}[/]\n[dim]{r.get('url', '')}[/]"
                            )
                        console.print(Panel(table, title=f"Web Search: {q}", border_style="cyan"))

                elif cmd == "/clear":
                    memory.clear_memory()
                    console.print("[bold green]  Memory cleared.[/]")

                elif cmd == "/memory":
                    items = memory.load_memory()
                    if not items:
                        console.print("[yellow]  Memory is empty.[/]")
                    else:
                        for i, item in enumerate(items[-5:], 1):
                            console.print(Panel(
                                f"[bold cyan]You:[/] {item.get('user', '')}\n"
                                f"[bold white]KURO:[/] {item.get('assistant', '')[:300]}...",
                                title=f"Memory [{i}]",
                                border_style="bright_black",
                            ))

                elif cmd == "/voice":
                    sub = parts[1].lower() if len(parts) > 1 else ""

                    if sub == "list":
                        # Show all available neural voices in a table
                        voices = list_available_voices()
                        from tools.voice import get_active_voice
                        active_id = get_active_voice()
                        vtable = Table(
                            title="Available Neural Voices  (Edge-TTS Ultra-Realistic)",
                            border_style="cyan",
                            box=box.ROUNDED,
                            header_style="bold cyan",
                        )
                        vtable.add_column("Name", style="bold cyan", min_width=10)
                        vtable.add_column("Voice ID", style="yellow")
                        vtable.add_column("Active", justify="center")
                        for name, vid in voices.items():
                            tick = "[bold green]✓[/]" if vid == active_id else ""
                            vtable.add_row(name.upper(), vid, tick)
                        console.print()
                        console.print(vtable)
                        console.print(f"  [dim]Usage: /voice \u003cname\u003e   e.g.  /voice andrew[/dim]\n")

                    elif sub and sub != "on" and sub != "off":
                        # Switch to named voice
                        ok, msg = set_voice_name(sub)
                        if ok:
                            console.print(f"[bold green]  [OK] {msg}[/]")
                            if not is_voice_enabled():
                                set_voice_enabled(True)
                                console.print("[bold cyan]  Voice TTS auto-enabled. Use /voice to toggle off.[/]")
                        else:
                            console.print(f"[bold red]  [FAIL] {msg}[/]")
                            console.print("  [dim]Tip: type /voice list to see available voices.[/dim]")

                    else:
                        # Plain /voice → toggle ON/OFF
                        new_state = not is_voice_enabled()
                        set_voice_enabled(new_state)
                        status = "[bold green]ENABLED[/]" if new_state else "[bold red]DISABLED[/]"
                        console.print(f"[bold cyan]  Local Voice TTS output is now {status}.[/]")

                elif cmd in ("/listen", "/talk"):
                    console.print("[bold cyan]  Listening to microphone... Speak now![/]")
                    ok, speech_text = listen_microphone()
                    if not ok:
                        console.print(f"[yellow]  {speech_text}[/]")
                    else:
                        console.print(f"[bold green]  You (Voice):[/] {speech_text}")
                        user_input = speech_text

                elif cmd == "/see":
                    if len(parts) < 2:
                        console.print("[yellow]  Usage: /see <image_path> [prompt][/]")
                    else:
                        img_path = parts[1]
                        prompt_text = " ".join(parts[2:]) if len(parts) > 2 else "Describe this image in detail and extract key information."
                        console.print(f"[bold cyan]  Analyzing Image:[/] {img_path}")
                        res = analyze_image_tool(img_path, prompt_text)
                        if not res.get("success"):
                            console.print(f"[bold red]  [FAIL] {res.get('error')}[/]")
                        else:
                            with Live(Spinner("dots", text="[bold cyan]KURO Vision analyzing...[/]"), refresh_per_second=12, console=console):
                                vision_res = ask_llm(prompt_text, system_prompt="You are KURO Vision. Analyze the image accurately.", provider=agent.provider, model=agent.model, image_info=res)
                            print_kuro_response(vision_res)

                elif cmd == "/browse":
                    if len(parts) < 2:
                        console.print("[yellow]  Usage: /browse <url>[/]")
                    else:
                        url_target = parts[1]
                        console.print(f"[bold yellow]  Headless Browsing:[/] {url_target}")
                        res = browse_web_headless(url_target)
                        if not res.get("success"):
                            console.print(f"[bold red]  [FAIL] {res.get('error')}[/]")
                        else:
                            console.print(Panel(
                                f"[bold cyan]Title:[/] {res.get('title')}\n\n"
                                f"[bold white]Content Preview (Word Count: {res.get('word_count')}):[/]\n"
                                f"{res.get('content_preview')[:1500]}...",
                                title=f"Headless Browser: {url_target}",
                                border_style="cyan"
                            ))

                elif cmd == "/learn":
                    if len(parts) < 3:
                        console.print("[yellow]  Usage: /learn <skill_name> <steps / description>[/]")
                    else:
                        s_name = parts[1]
                        s_steps = " ".join(parts[2:])
                        res = save_learned_skill(s_name, f"Custom user routine: {s_name}", s_steps)
                        if res.get("success"):
                            console.print(f"[bold green]  [OK] Skill '{s_name}' learned and saved to scratch/skills![/]")
                        else:
                            console.print(f"[bold red]  [FAIL] {res.get('error')}[/]")

                elif cmd == "/skills":
                    skills = list_learned_skills()
                    if not skills:
                        console.print("[yellow]  No custom learned skills saved yet. Use /learn <name> <steps> to add one![/]")
                    else:
                        table = Table(title="KURO Self-Learned Skills", border_style="cyan", box=box.ROUNDED)
                        table.add_column("Skill Name", style="bold cyan")
                        table.add_column("Location", style="dim")
                        table.add_column("Preview", style="white")
                        for s in skills:
                            table.add_row(s["name"], s["path"], s["preview"][:80] + "...")
                        console.print(table)

                elif cmd == "/key":
                    if len(parts) == 2:
                        target_key, target_prov = parts[1], "gemini"
                    elif len(parts) >= 3:
                        target_prov, target_key = parts[1].lower(), parts[2]
                    else:
                        console.print("[yellow]  Usage: /key <KEY>  or  /key <provider> <KEY>[/]")
                        continue

                    if config.save_api_key(target_key, target_prov):
                        agent.provider = config.get_active_provider()
                        agent.model    = config.get_active_model(agent.provider)
                        console.print(f"[bold green]  [OK] Key added to {target_prov.upper()} pool & saved.[/]")
                        console.print()
                        print_status_banner()
                    else:
                        console.print("[bold red]  [FAIL] Could not save API key.[/]")

                elif cmd == "/plan":
                    if len(parts) < 2:
                        active = get_active_plan()
                        if active:
                            console.print(Panel(format_plan_table(active), border_style="magenta", title="Active Task Plan"))
                        else:
                            console.print("[yellow]  Usage: /plan <goal_description>[/]")
                    else:
                        goal_text = " ".join(parts[1:])
                        console.print(f"[bold magenta]  Generating Task Plan:[/] {goal_text}")
                        plan = create_task_plan(goal_text, llm_fn=ask_llm)
                        console.print(Panel(format_plan_table(plan), border_style="magenta", title="Generated Task Plan"))

                elif cmd == "/sql":
                    if len(parts) < 2:
                        console.print("[yellow]  Usage: /sql <query_or_script>  (runs against brain/kuro.db)[/]")
                    else:
                        q = " ".join(parts[1:])
                        res = execute_sql_query("brain/kuro.db", q)
                        if res.get("success"):
                            rows = res.get("rows", [])
                            if rows:
                                table = Table(title="SQL Query Result", border_style="cyan", box=box.ROUNDED)
                                for col in rows[0].keys():
                                    table.add_column(col, style="yellow")
                                for r in rows[:10]:
                                    table.add_row(*[str(v) for v in r.values()])
                                console.print(table)
                            else:
                                console.print(f"[bold green]  [OK] {res.get('message', 'Query executed successfully.')}[/]")
                        else:
                            console.print(f"[bold red]  [FAIL] {res.get('error')}[/]")

                elif cmd == "/notes":
                    if len(parts) < 3:
                        console.print("[yellow]  Usage: /notes <filename.md> <content>[/]")
                    else:
                        fname = parts[1]
                        if not fname.endswith(".md"):
                            fname += ".md"
                        note_body = " ".join(parts[2:])
                        res = write_md_note(f"brain/notes/{fname}", fname, note_body)
                        if res.get("success"):
                            console.print(f"[bold green]  [OK] Note saved to brain/notes/{fname}[/]")
                        else:
                            console.print(f"[bold red]  [FAIL] {res.get('error')}[/]")

                elif cmd == "/hotkey":
                    console.print(Panel(
                        "[bold cyan]Windows Global Hotkey Listener[/]\n\n"
                        "• Key combination: [bold yellow]Ctrl + Alt + K[/bold yellow] (or [bold yellow]Ctrl + Shift + K[/bold yellow])\n"
                        "• Function: Immediately focuses and brings KURO terminal window to foreground from anywhere on your OS.\n"
                        "• Status: [bold green]ACTIVE[/bold green]",
                        border_style="cyan"
                    ))

                elif cmd == "/notify":
                    if len(parts) < 2:
                        console.print(Panel(
                            "[bold cyan]KURO Smart Multi-Channel Notification Center[/]\n\n"
                            "• [bold]Basic:[/bold]        [cyan]/notify <message>[/cyan]\n"
                            "• [bold]Titled:[/bold]       [cyan]/notify <title> | <message>[/cyan]\n"
                            "• [bold]To Telegram:[/bold]  [cyan]/notify --channel telegram [--target @channel_name] <message>[/cyan]\n"
                            "• [bold]With Image:[/bold]   [cyan]/notify --image C:\\image.png --channel telegram <caption/message>[/cyan]\n"
                            "• [bold]Urgency:[/bold]      [cyan]/notify --priority <info|success|warning|critical|alert> <message>[/cyan]\n"
                            "• [bold]Audio / Voice:[/bold][cyan]/notify --sound <default|im|mail|alarm|silent> --speak <message>[/cyan]\n\n"
                            "[bold yellow]Channel Configurations & Diagnostics:[/bold yellow]\n"
                            "  - [cyan]/notify config telegram <BOT_TOKEN> <CHAT_ID_OR_CHANNEL>[/cyan]\n"
                            "  - [cyan]/notify config discord <WEBHOOK_URL>[/cyan]\n"
                            "  - [cyan]/notify config slack <WEBHOOK_URL>[/cyan]\n"
                            "  - [cyan]/notify test [telegram|discord|slack|toast|all][/cyan]\n"
                            "  - [cyan]/notify diagnose telegram [@channel_or_chat_id][/cyan]",
                            title="🔔 Notification Engine & Telegram Channel Support",
                            border_style="cyan"
                        ))
                    else:
                        from tools.notifier import (
                            send_smart_notification,
                            load_notification_config,
                            save_notification_config,
                            diagnose_channel,
                            NotificationUrgency
                        )

                        subcmd = parts[1].lower()

                        if subcmd == "test":
                            target_ch = parts[2].lower() if len(parts) > 2 else "all"
                            console.print(f"[bold cyan]  Running diagnostic test on channel:[/] [yellow]{target_ch.upper()}[/]")
                            res = send_smart_notification(
                                title="System Test Alert",
                                message="KURO 2.0 notification engine is operational and verified!",
                                urgency=NotificationUrgency.SUCCESS,
                                channels=[target_ch],
                                speak=True if target_ch in ("toast", "all") else False
                            )
                            table = Table(title="Notification Dispatch Report", border_style="cyan", box=box.ROUNDED)
                            table.add_column("Channel", style="bold cyan")
                            table.add_column("Status", justify="center")
                            table.add_column("Details / Diagnosis", style="yellow")

                            for ch, ch_res in res.get("dispatched", {}).items():
                                ok = ch_res.get("success", False)
                                status_str = "[bold green]✓ SUCCESS[/]" if ok else "[bold red]✗ FAILED[/]"
                                detail = str(ch_res.get("error") or ch_res.get("message") or "Delivered successfully")
                                table.add_row(ch.upper(), status_str, detail)

                            console.print(table)

                        elif subcmd == "diagnose":
                            target_ch = parts[2].lower() if len(parts) > 2 else "telegram"
                            target_id = parts[3] if len(parts) > 3 else None
                            console.print(f"[bold cyan]  Diagnosing channel:[/] [yellow]{target_ch.upper()}[/]")
                            diag = diagnose_channel(target_ch, target=target_id)
                            console.print(Panel(
                                json.dumps(diag, indent=2, ensure_ascii=False),
                                title=f"Channel Diagnostic: {target_ch.upper()}",
                                border_style="cyan"
                            ))

                        elif subcmd == "config":
                            if len(parts) < 4:
                                console.print("[yellow]  Usage: /notify config <discord|telegram|slack> <TOKEN_OR_URL> [CHAT_ID_OR_CHANNEL][/]")
                            else:
                                target_chan = parts[2].lower()
                                cfg = load_notification_config()
                                if target_chan in ("discord", "disc"):
                                    cfg["discord_webhook"] = parts[3]
                                    save_notification_config(cfg)
                                    console.print("[bold green]  [OK] Discord webhook configured & stored in Encrypted Vault![/]")
                                elif target_chan in ("telegram", "tg"):
                                    cfg["telegram_token"] = parts[3]
                                    if len(parts) > 4:
                                        cfg["telegram_chat_id"] = parts[4]
                                    save_notification_config(cfg)
                                    console.print(f"[bold green]  [OK] Telegram configured! (Chat/Channel: {cfg.get('telegram_chat_id', 'Default')})[/]")
                                elif target_chan == "slack":
                                    cfg["slack_webhook"] = parts[3]
                                    save_notification_config(cfg)
                                    console.print("[bold green]  [OK] Slack webhook configured & stored in Encrypted Vault![/]")
                                else:
                                    console.print(f"[yellow]  Unknown channel '{target_chan}'.[/]")

                        else:
                            # Parse flags: --priority, --sound, --speak, --channel, --target, --image
                            raw_args = parts[1:]
                            urgency = NotificationUrgency.INFO
                            sound_preset = "default"
                            speak_alert = False
                            chan_override = None
                            target_override = None
                            image_path = None

                            clean_parts = []
                            i = 0
                            while i < len(raw_args):
                                arg = raw_args[i]
                                if arg in ("--priority", "-p") and i + 1 < len(raw_args):
                                    p_val = raw_args[i + 1].lower()
                                    try:
                                        urgency = NotificationUrgency(p_val)
                                    except Exception:
                                        pass
                                    i += 2
                                elif arg in ("--sound", "-s") and i + 1 < len(raw_args):
                                    sound_preset = raw_args[i + 1].lower()
                                    i += 2
                                elif arg in ("--speak", "-v"):
                                    speak_alert = True
                                    i += 1
                                elif arg in ("--channel", "-c") and i + 1 < len(raw_args):
                                    chan_override = [raw_args[i + 1].lower()]
                                    i += 2
                                elif arg in ("--target", "-t") and i + 1 < len(raw_args):
                                    target_override = raw_args[i + 1]
                                    i += 2
                                elif arg in ("--image", "-i") and i + 1 < len(raw_args):
                                    image_path = raw_args[i + 1]
                                    i += 2
                                else:
                                    clean_parts.append(arg)
                                    i += 1

                            full_txt = " ".join(clean_parts)
                            if "|" in full_txt:
                                ntitle, nmsg = [p.strip() for p in full_txt.split("|", 1)]
                            else:
                                ntitle, nmsg = "KURO System Assistant", full_txt

                            res = send_smart_notification(
                                title=ntitle,
                                message=nmsg,
                                urgency=urgency,
                                channels=chan_override,
                                speak=speak_alert,
                                sound=sound_preset,
                                target_override=target_override,
                                image_path=image_path,
                            )
                            if res.get("success"):
                                console.print(f"[bold green]  [OK] Notification sent ({urgency.value.upper()})! Dispatched to: {list(res.get('dispatched', {}).keys())}[/]")
                            else:
                                err_details = []
                                for k_ch, v_ch in res.get("dispatched", {}).items():
                                    if not v_ch.get("success"):
                                        err_details.append(f"{k_ch.upper()}: {v_ch.get('error', 'Failed')}")
                                console.print(f"[bold red]  [FAIL] Notification error:[/] {'; '.join(err_details) if err_details else 'Failed to deliver'}")

                elif cmd == "/db":
                    target_db = parts[1] if len(parts) > 1 else "brain/kuro.db"
                    res = explore_database(target_db, op="list_tables")
                    if res.get("success"):
                        table = Table(title=f"Database Explorer: {target_db}", border_style="cyan", box=box.ROUNDED)
                        table.add_column("Table Name", style="bold cyan")
                        table.add_column("Row Count", justify="right", style="yellow")
                        for t in res.get("tables", []):
                            table.add_row(t["table"], str(t["row_count"]))
                        console.print(table)
                elif cmd == "/dir":
                    target_path = parts[1] if len(parts) > 1 else "."
                    from tools.files import list_directory
                    res = list_directory(target_path)
                    if res.get("success"):
                        table = Table(title=f"Directory Listing: {target_path}", border_style="cyan", box=box.ROUNDED)
                        table.add_column("Type", style="yellow", width=8)
                        table.add_column("Name", style="bold cyan")
                        table.add_column("Size", justify="right", style="dim")
                        for item in res.get("items", []):
                            table.add_row(item.get("type", "file"), item.get("name", ""), str(item.get("size", "-")))
                        console.print(table)
                    else:
                        console.print(f"[bold red]  [FAIL] {res.get('error')}[/]")

                elif cmd == "/project":
                    from core.project_aware import project_inspector
                    profile = project_inspector.inspect(".", force_refresh=True)
                    console.print(Panel(
                        f"[bold cyan]Project Profile:[/] {profile.name}\n\n"
                        f"[bold yellow]Languages:[/] {', '.join(profile.languages)}\n"
                        f"[bold yellow]Frameworks:[/] {', '.join(profile.frameworks) if profile.frameworks else 'None'}\n"
                        f"[bold yellow]Package Managers:[/] {', '.join(profile.package_managers)}\n"
                        f"[bold yellow]Entry Points:[/] {', '.join(profile.entry_points)}\n"
                        f"[bold yellow]Git Status:[/] {profile.git_status}\n"
                        f"[bold yellow]Build Cmd:[/] `{profile.build_command}`\n"
                        f"[bold yellow]Test Cmd:[/] `{profile.test_command}`",
                        title=f"Project Profile",
                        border_style="cyan"
                    ))

                elif cmd == "/integrations":
                    from core.integration_manager import integration_manager
                    integs = integration_manager.list_integrations()
                    table = Table(title="Connected Services & External Integrations", border_style="cyan", box=box.ROUNDED)
                    table.add_column("Integration", style="bold cyan")
                    table.add_column("Connected", justify="center")
                    table.add_column("Account / Details", style="yellow")
                    for i in integs:
                        tick = "[bold green]✓ Connected[/]" if i["connected"] else "[dim]○ Disconnected[/]"
                        table.add_row(i["name"].upper(), tick, str(i.get("account", "-")))
                    console.print(table)
                    console.print(Panel(
                        "[dim]How to connect an integration:\n"
                        "• Connect Telegram:     [cyan]/connect telegram <BOT_TOKEN> [CHAT_ID_OR_CHANNEL][/cyan]\n"
                        "• Connect Discord:      [cyan]/connect discord <WEBHOOK_URL>[/cyan]\n"
                        "• Connect GitHub:       [cyan]/connect github <PERSONAL_ACCESS_TOKEN>[/cyan]\n"
                        "• Connect Google Drive: [cyan]/connect drive <DRIVE_API_TOKEN>[/cyan]\n"
                        "• Connect Email:        [cyan]/connect email <EMAIL_API_TOKEN>[/cyan]\n"
                        "• Disconnect service:   [cyan]/disconnect <service_name>[/cyan]\n\n"
                        "Tokens are encrypted and stored securely in your Encrypted Secret Vault.[/dim]",
                        border_style="bright_black",
                        padding=(0, 2)
                    ))

                elif cmd == "/connect":
                    if len(parts) < 3:
                        console.print("[yellow]  Usage: /connect <telegram|discord|github|drive|email> <TOKEN_OR_URL> [chat_id_or_user][/]")
                    else:
                        target_service = parts[1].lower()
                        if target_service in ("drive", "gdrive", "google-drive"):
                            target_service = "google_drive"
                        elif target_service in ("tg", "tele"):
                            target_service = "telegram"
                        elif target_service in ("disc",):
                            target_service = "discord"

                        target_token = parts[2]
                        target_user = parts[3] if len(parts) > 3 else None

                        from core.integration_manager import integration_manager
                        if integration_manager.connect_integration(target_service, target_token, user=target_user):
                            console.print(f"[bold green]  [OK] Integration '{target_service.upper()}' successfully connected and saved in Encrypted Vault![/]")
                        else:
                            console.print(f"[bold red]  [FAIL] Failed to connect integration '{target_service}'. Verify your token/credentials.[/]")

                elif cmd == "/disconnect":
                    if len(parts) < 2:
                        console.print("[yellow]  Usage: /disconnect <telegram|discord|github|drive|email>[/]")
                    else:
                        target_service = parts[1].lower()
                        if target_service in ("drive", "gdrive", "google-drive"):
                            target_service = "google_drive"
                        elif target_service in ("tg", "tele"):
                            target_service = "telegram"
                        elif target_service in ("disc",):
                            target_service = "discord"

                        from core.integration_manager import integration_manager
                        if integration_manager.disconnect_integration(target_service):
                            console.print(f"[bold green]  [OK] Integration '{target_service.upper()}' disconnected.[/]")
                        else:
                            console.print(f"[bold red]  [FAIL] Failed to disconnect integration '{target_service}'.[/]")

                elif cmd == "/tasks":
                    from core.task_state import task_registry
                    tasks = task_registry.list_all()
                    if not tasks:
                        console.print("[yellow]  No task lifecycle history recorded yet.[/]")
                    else:
                        table = Table(title="Task Lifecycle State Machine History", border_style="cyan", box=box.ROUNDED)
                        table.add_column("Task ID", style="bold cyan")
                        table.add_column("State", style="yellow")
                        table.add_column("Goal", style="white")
                        for t in tasks[-10:]:
                            table.add_row(t.task_id, t.state.value.upper(), t.goal[:50])
                        console.print(table)

                elif cmd == "/metrics":
                    from core.memory_db import get_metrics_summary
                    metrics = get_metrics_summary(limit=10)
                    if not metrics:
                        console.print("[yellow]  No execution metrics recorded yet.[/]")
                    else:
                        table = Table(title="Execution Analytics & Metrics Summary", border_style="cyan", box=box.ROUNDED)
                        table.add_column("Task ID", style="dim")
                        table.add_column("Provider / Model", style="bold cyan")
                        table.add_column("Tool Calls", justify="center", style="yellow")
                        table.add_column("Duration", justify="right", style="green")
                        for m in metrics:
                            table.add_row(
                                str(m.get("task_id", "N/A")),
                                f"{m.get('provider')}/{m.get('model')}",
                                str(m.get("tool_calls", 0)),
                                f"{m.get('duration_seconds', 0.0):.1f}s",
                            )
                        console.print(table)

                elif cmd == "/vault":
                    from core.vault import vault
                    subcmd = parts[1].lower() if len(parts) > 1 else "list"

                    if subcmd == "status":
                        status = vault.get_status()
                        console.print(Panel(
                            f"[bold cyan]Vault Storage Path:[/] {status['path']}\n"
                            f"[bold yellow]Vault Exists:[/] {status['exists']}\n"
                            f"[bold yellow]Lock Status:[/] {'[red]LOCKED[/red]' if status['locked'] else '[green]UNLOCKED[/green]'}\n"
                            f"[bold yellow]Crypto Backend:[/] {status['backend']}\n"
                            f"[bold yellow]Total Secrets:[/] {status['secret_count']}\n"
                            f"[bold yellow]Custom Master Password:[/] {status['has_password']}",
                            title="🔒 KURO Encrypted Credential Vault Status",
                            border_style="cyan"
                        ))

                    elif subcmd == "list":
                        secrets = vault.list_secrets()
                        if not secrets:
                            console.print("[yellow]  Vault is empty or locked. Use /vault set <KEY> <VALUE> or /vault migrate.[/]")
                        else:
                            table = Table(title="🔒 KURO Encrypted Secret Vault", border_style="cyan", box=box.ROUNDED)
                            table.add_column("Secret Key", style="bold cyan")
                            table.add_column("Encrypted / Masked Value", style="yellow")
                            table.add_column("Description", style="white")
                            for s in secrets:
                                table.add_row(s["key"], s["masked"], s["description"] or "-")
                            console.print(table)
                            console.print(Panel(
                                "[dim]• Set secret:    [cyan]/vault set <KEY> <VALUE> [description][/cyan]\n"
                                "• Get secret:    [cyan]/vault get <KEY> [--reveal][/cyan]\n"
                                "• Delete secret: [cyan]/vault delete <KEY>[/cyan]\n"
                                "• Auto-migrate:  [cyan]/vault migrate[/cyan] (imports API keys from .env)[/dim]",
                                border_style="bright_black",
                                padding=(0, 2)
                            ))

                    elif subcmd == "set":
                        if len(parts) < 4:
                            console.print("[yellow]  Usage: /vault set <KEY> <VALUE> [description][/]")
                        else:
                            k = parts[2]
                            v = parts[3]
                            desc = " ".join(parts[4:]) if len(parts) > 4 else "Stored credential"
                            if vault.set_secret(k, v, description=desc):
                                console.print(f"[bold green]  [OK] Secret '{k.upper()}' encrypted and securely stored in vault![/]")
                            else:
                                console.print(f"[bold red]  [FAIL] Failed to save secret '{k}'. Vault may be locked.[/]")

                    elif subcmd == "get":
                        if len(parts) < 3:
                            console.print("[yellow]  Usage: /vault get <KEY> [--reveal][/]")
                        else:
                            k = parts[2]
                            reveal = "--reveal" in parts or "-r" in parts
                            sec = vault.get_secret(k)
                            if sec is None:
                                console.print(f"[yellow]  Secret '{k.upper()}' not found in vault.[/]")
                            else:
                                if reveal:
                                    console.print(f"[bold green]  {k.upper()}:[/] [white]{sec}[/]")
                                else:
                                    from core.vault import mask_secret
                                    console.print(f"[bold green]  {k.upper()}:[/] [yellow]{mask_secret(sec)}[/] [dim](use --reveal to display plaintext)[/dim]")

                    elif subcmd == "delete":
                        if len(parts) < 3:
                            console.print("[yellow]  Usage: /vault delete <KEY>[/]")
                        else:
                            k = parts[2]
                            if vault.delete_secret(k):
                                console.print(f"[bold green]  [OK] Secret '{k.upper()}' deleted from vault.[/]")
                            else:
                                console.print(f"[bold red]  [FAIL] Secret '{k.upper()}' not found or vault is locked.[/]")

                    elif subcmd == "migrate":
                        count = vault.auto_migrate_from_env()
                        console.print(f"[bold green]  [OK] Migrated {count} secret(s) from .env into encrypted vault![/]")

                    elif subcmd == "lock":
                        vault.lock()
                        console.print("[bold yellow]  [LOCKED] Vault locked and in-memory secrets purged.[/]")

                    elif subcmd == "unlock":
                        pwd = parts[2] if len(parts) > 2 else None
                        if vault.unlock(password=pwd):
                            console.print("[bold green]  [OK] Vault unlocked successfully![/]")
                        else:
                            console.print("[bold red]  [FAIL] Failed to unlock vault. Incorrect password or decryption error.[/]")

                    else:
                        console.print("[yellow]  Usage: /vault <list|status|set|get|delete|migrate|lock|unlock>[/]")

                elif cmd == "/sandbox":
                    from core.sandbox import sandbox
                    subcmd = parts[1].lower() if len(parts) > 1 else "status"

                    if subcmd in ("status", "info"):
                        status = sandbox.get_status()
                        console.print(Panel(
                            f"[bold yellow]Sandbox Guard Active:[/] {'[bold green]ENABLED[/bold green]' if status['enabled'] else '[bold red]DISABLED[/bold red]'}\n"
                            f"[bold yellow]Strict AST Mode:[/] {status['strict_mode']}\n"
                            f"[bold yellow]Privacy PII Masking:[/] {status['privacy_masking']}\n"
                            f"[bold yellow]Sandbox Workspace:[/] {status['sandbox_dir']}\n"
                            f"[bold yellow]Temp Sandbox Files:[/] {status['total_sandbox_files']}",
                            title="🛡️ KURO Sandbox Guard & Safety Engine",
                            border_style="cyan"
                        ))

                    elif subcmd in ("on", "enable"):
                        sandbox.enable()
                        console.print("[bold green]  [OK] Sandbox execution guardrail ENABLED.[/]")

                    elif subcmd in ("off", "disable"):
                        sandbox.disable()
                        console.print("[bold yellow]  [WARNING] Sandbox execution guardrail DISABLED.[/]")

                    elif subcmd == "toggle":
                        new_state = sandbox.toggle()
                        state_str = "[bold green]ENABLED[/bold green]" if new_state else "[bold red]DISABLED[/bold red]"
                        console.print(f"  [OK] Sandbox guard is now {state_str}.")

                    elif subcmd == "clean":
                        cleaned = sandbox.clean_sandbox()
                        console.print(f"[bold green]  [OK] Cleaned {cleaned} temporary files from sandbox workspace.[/]")

                    elif subcmd == "check":
                        if len(parts) < 3:
                            console.print("[yellow]  Usage: /sandbox check <python_code_or_file_path>[/]")
                        else:
                            target = " ".join(parts[2:])
                            if Path(target).exists() and Path(target).is_file():
                                code_to_check = Path(target).read_text(encoding="utf-8")
                            else:
                                code_to_check = target
                            rep = sandbox.validate_python_code(code_to_check)
                            table = Table(title="AST Code Safety Inspection", border_style="cyan", box=box.ROUNDED)
                            table.add_column("Property", style="bold cyan")
                            table.add_column("Value", style="yellow")
                            table.add_row("Is Safe", str(rep.is_safe))
                            table.add_row("Risk Level", rep.risk_level)
                            table.add_row("Violations", "\n".join(rep.violations) if rep.violations else "None")
                            table.add_row("Warnings", "\n".join(rep.warnings) if rep.warnings else "None")
                            console.print(table)

                    else:
                        console.print("[yellow]  Usage: /sandbox <status|on|off|toggle|clean|check>[/]")

                elif cmd == "/safe":
                    from core.permissions import default_gate
                    subcmd = parts[1].lower() if len(parts) > 1 else "status"

                    if subcmd in ("status", "info"):
                        status_str = "[bold green]ENABLED (Prompt for impactful actions)[/bold green]" if config.SAFE_MODE else "[bold yellow]DISABLED (Auto-allow confirmable actions)[/bold yellow]"
                        overrides = list(default_gate._overrides.keys())
                        overrides_str = ", ".join(overrides) if overrides else "None"
                        console.print(Panel(
                            f"[bold cyan]Safe Mode Status:[/] {status_str}\n"
                            f"[bold yellow]Tool Overrides (Always Allowed):[/] {overrides_str}\n\n"
                            "[dim]• Enable Safe Mode:      [cyan]/safe on[/cyan]\n"
                            "• Disable Safe Mode:     [cyan]/safe off[/cyan]\n"
                            "• Toggle:                [cyan]/safe toggle[/cyan]\n"
                            "• Always Allow One Tool: [cyan]/safe allow <tool_name>[/cyan] (e.g. /safe allow execute_python)\n"
                            "• Clear Overrides:       [cyan]/safe clear[/cyan][/dim]",
                            title="🛡️ KURO Permission Gate & Safe Mode",
                            border_style="cyan"
                        ))

                    elif subcmd in ("on", "enable"):
                        config.SAFE_MODE = True
                        default_gate.set_safe_mode(True)
                        console.print("[bold green]  [OK] Safe Mode ENABLED. Impactful actions will prompt for confirmation.[/]")

                    elif subcmd in ("off", "disable"):
                        config.SAFE_MODE = False
                        default_gate.set_safe_mode(False)
                        console.print("[bold yellow]  [WARNING] Safe Mode DISABLED. Autonomous tools (Python, file writes, commands) will execute without prompting.[/]")

                    elif subcmd == "toggle":
                        config.SAFE_MODE = not config.SAFE_MODE
                        default_gate.set_safe_mode(config.SAFE_MODE)
                        state_str = "[bold green]ENABLED[/bold green]" if config.SAFE_MODE else "[bold yellow]DISABLED[/bold yellow]"
                        console.print(f"  [OK] Safe Mode is now {state_str}.")

                    elif subcmd == "allow":
                        if len(parts) < 3:
                            console.print("[yellow]  Usage: /safe allow <action_name>  (e.g. /safe allow execute_python)[/]")
                        else:
                            target_tool = parts[2]
                            default_gate.allow_action(target_tool)
                            console.print(f"[bold green]  [OK] Tool '{target_tool}' will now always be permitted without confirmation prompts.[/]")

                    elif subcmd in ("clear", "reset"):
                        default_gate.clear_overrides()
                        console.print("[bold green]  [OK] Cleared all tool permission overrides.[/]")

                    else:
                        console.print("[yellow]  Usage: /safe <status|on|off|toggle|allow <tool>|clear>[/]")

                else:
                    console.print(f"[yellow]  Unknown command '{cmd}'. Type /help.[/]")
                continue

            # ── Shell command mode ─────────────────────────
            if user_input.startswith("!"):
                cmd = user_input[1:].strip()
                if not cmd:
                    console.print("[red]  No command given.[/]")
                    continue
                res = run_command(cmd, confirm_if_risky=config.SAFE_MODE)
                print_shell_output(cmd, res)
                continue

            # ── Autonomous Agent Mode ──────────────────────
            console.print()
            response = None

            with Live(
                Spinner("dots2", text="[bold cyan]KURO is thinking...[/bold cyan]"),
                refresh_per_second=12,
                console=console,
                transient=True,
            ):
                response = agent.run(user_input)

            print_kuro_response(response)

        except (KeyboardInterrupt, EOFError):
            console.print()
            console.print(Rule("[bold cyan]KURO session ended.[/bold cyan]", style="cyan"))
            console.print()
            break
        except Exception as e:
            console.print(f"[bold red]  Runtime Error:[/] {str(e)}")


if __name__ == "__main__":
    app()
