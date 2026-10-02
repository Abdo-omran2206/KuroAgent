import sys
import os
import json
import time
import threading
import typer

# Suppress pygame startup banner before any import triggers it
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"


# Force UTF-8 output on Windows so Rich spinners and Unicode chars work
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

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
    "   [dim]ReAct Engine  |  Multi-Key Pools  |  Web Search  |  Git Checkpoints[/]",
    "",
]

COMMAND_LIST = [
    "/help", "/status", "/pool", "/models",
    "/key", "/undo", "/clear", "/memory",
    "/search", "/see", "/browse", "/voice", "/listen",
    "/learn", "/skills", "/plan", "/sql", "/notes", "/hotkey",
    "/notify", "/db",
    "exit", "quit"
]

SLASH_DESCRIPTIONS = {
    "/help":    "Show command reference & capabilities",
    "/status":  "Active provider, model, & system status",
    "/pool":    "API key pool & cooldown status",
    "/models":  "Model fallback priority chain",
    "/key":     "Add API key: /key <KEY> or /key <provider> <KEY>",
    "/undo":    "Rollback last automated file changes",
    "/clear":   "Reset active conversation memory",
    "/memory":  "View stored conversation history & brain summary",
    "/search":  "Live web search: /search <query>",
    "/see":     "Vision analysis: /see <image_path> [prompt]",
    "/browse":  "Headless web automation: /browse <url>",
    "/voice":   "Toggle TTS | /voice list | /voice <name>",
    "/listen":  "Microphone Speech-to-Text input mode",
    "/learn":   "Save custom routine: /learn <skill_name> <steps>",
    "/skills":  "List all KURO self-learned skills",
    "/plan":    "Task planning mode: /plan <goal_description>",
    "/sql":     "Execute SQL query: /sql <query_or_script>",
    "/notes":   "Write MD note: /notes <filename.md> <content>",
    "/hotkey":  "Global hotkey status (Ctrl+Alt+K / Ctrl+Shift+K)",
    "/notify":  "Send Windows Toast: /notify <title> | <message>",
    "/db":      "Database explorer: /db [db_path]",
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
    """Modern styled help panel with command usage and self-aware capabilities."""
    table = Table(
        title="KURO 2.0  Command Reference & Self-Aware Capabilities",
        border_style="cyan",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("Command", style="bold cyan", min_width=16)
    table.add_column("Capability & Action", style="white", min_width=30)
    table.add_column("How to Use / Example", style="yellow")

    rows = [
        ("/help",                  "Display system reference & tool capabilities",  "Type [cyan]/help[/cyan]"),
        ("/status",                "Show active LLM provider, model, & safe mode", "Type [cyan]/status[/cyan]"),
        ("/pool",                  "View API key pool & rate limit cooldowns",    "Type [cyan]/pool[/cyan]"),
        ("/models",                "View model fallback chain for active provider","Type [cyan]/models[/cyan]"),
        ("/key",                   "Add API key to provider pool",                 "[cyan]/key <KEY>[/cyan] or [cyan]/key groq <KEY>[/cyan]"),
        ("/undo",                  "Rollback automated file changes via Git",       "Type [cyan]/undo[/cyan]"),
        ("/search",                "Live web search (DuckDuckGo + Wikipedia)",      "[cyan]/search OpenAI news 2026[/cyan]"),
        ("/see",                   "Multimodal Vision & Image Analysis",           "[cyan]/see C:\\chart.png explain trends[/cyan]"),
        ("/browse",                 "Headless web browser scraping",                "[cyan]/browse https://news.ycombinator.com[/cyan]"),
        ("/voice",                  "Neural TTS Voice Output  (toggle / list / switch speaker)",  "[cyan]/voice[/]  |  [cyan]/voice list[/]  |  [cyan]/voice andrew[/]"),
        ("/plan",                   "Task Planning Mode (multi-step decomposition)", "[cyan]/plan build a trading bot[/cyan]"),
        ("/sql",                    "SQLite Database Query / Script execution",      "[cyan]/sql SELECT * FROM conversations LIMIT 5;[/cyan]"),
        ("/notes",                  "Write structured Markdown note to brain/notes/","[cyan]/notes market_notes.md BTC looks bullish[/cyan]"),
        ("/hotkey",                 "Global Win32 Hotkey Status (Ctrl+Alt+K)",        "Type [cyan]/hotkey[/cyan]"),
        ("/learn",                  "Save custom routine (Self-Improvement)",      "[cyan]/learn test_flow Run pytest and lint[/cyan]"),
        ("/skills",                 "List all self-learned skills & routines",      "Type [cyan]/skills[/cyan]"),
        ("/memory",                 "Inspect persistent conversation memory store",  "Type [cyan]/memory[/cyan]"),
        ("/clear",                  "Reset conversation context memory",           "Type [cyan]/clear[/cyan]"),
        ("!<cmd>",                  "Direct shell execution (bypass LLM)",           "[cyan]!git status[/cyan] or [cyan]!dir[/cyan]"),
        ("exit / quit",             "Terminate KURO session",                       "Type [cyan]exit[/cyan] or [cyan]quit[/cyan]"),
    ]
    for cmd, desc, usage in rows:
        table.add_row(cmd, desc, usage)

    console.print()
    console.print(table)
    console.print(
        Panel(
            "[dim]Tips:\n"
            "• Press [bold]Tab[/bold] to autocomplete commands and file paths.\n"
            "• Press [bold]Up/Down arrows[/bold] to navigate command history.\n"
            "• Press [bold]Ctrl+L[/bold] to clear terminal screen without losing memory.\n"
            "• KURO is self-aware: ask KURO [bold]'What can you do?'[/bold] to inspect live capabilities.[/dim]",
            border_style="bright_black",
            padding=(0, 2),
        )
    )
    console.print()
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

    history_file = config.BASE_DIR / ".kuro_history"
    session = PromptSession(
        history=FileHistory(str(history_file)),
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
                        console.print("[yellow]  Usage: /notify <title> | <message>[/]")
                    else:
                        full_txt = " ".join(parts[1:])
                        if "|" in full_txt:
                            ntitle, nmsg = [p.strip() for p in full_txt.split("|", 1)]
                        else:
                            ntitle, nmsg = "KURO System Assistant", full_txt
                        res = send_toast_notification(ntitle, nmsg)
                        if res.get("success"):
                            console.print(f"[bold green]  [OK] Toast notification sent via {res.get('method')}.[/]")
                        else:
                            console.print(f"[bold red]  [FAIL] {res.get('error')}[/]")

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
                    else:
                        console.print(f"[bold red]  [FAIL] {res.get('error')}[/]")

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
