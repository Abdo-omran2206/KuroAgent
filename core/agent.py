import json
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from core import config
from core import memory
from core import personality
from core.llm import ask_llm
from tools.system import run_command, get_system_info
from tools.files import read_file, write_file, create_file, edit_file, list_directory, get_repo_tree, execute_sql_query, write_md_note
from tools.interpreter import execute_python_code
from tools.web import search_web, fetch_url
from tools.git_checkpoint import create_checkpoint
from tools.vision import analyze_image_tool
from tools.web_browser import browse_web_headless, automate_browser
from tools.self_improve import save_learned_skill, list_learned_skills
from tools.planner import create_task_plan, get_active_plan, execute_plan_step, format_plan_table
from tools.notifier import send_toast_notification
from tools.db_explorer import explore_database

console = Console()


def _safe_json_parse(raw_json: str) -> Optional[Dict[str, Any]]:
    """Robust JSON parser that repairs invalid escape sequences and loose formatting."""
    raw_json = raw_json.strip()
    try:
        return json.loads(raw_json, strict=False)
    except Exception:
        pass

    # Repair invalid escape sequences (e.g. \import, \path, \new)
    try:
        repaired = re.sub(r'\\([^"\\/bfnrtu])', r'\\\\\1', raw_json)
        return json.loads(repaired, strict=False)
    except Exception:
        pass

    # Regex fallback extraction for action and parameters
    try:
        action_m = re.search(r'"action"\s*:\s*"([^"]+)"', raw_json)
        if action_m:
            data = {"action": action_m.group(1)}
            for field in ("cmd", "path", "target", "replacement", "content", "code", "query", "url", "prompt", "name", "description", "steps", "db_path"):
                val_m = re.search(rf'"{field}"\s*:\s*("(?:\\.|[^"\\])*"|[\d.]+|true|false|null)', raw_json, re.DOTALL)
                if val_m:
                    val_str = val_m.group(1)
                    if val_str.startswith('"') and val_str.endswith('"'):
                        try:
                            data[field] = json.loads(val_str)
                        except Exception:
                            data[field] = val_str[1:-1].replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
                    else:
                        data[field] = val_str
            return data
    except Exception:
        pass

    return None


class KuroAgent:
    """
    KURO Level 2 Autonomous System Assistant.
    Implements a robust multi-step ReAct (Reasoning + Acting) autonomous execution loop.
    """

    def __init__(self):
        self.provider = config.get_active_provider()
        self.model = config.get_active_model(self.provider)

    def _build_system_context(self) -> str:
        """Constructs live system prompt with environmental context, self-awareness, learned skills, and tool schemas."""
        personality_prompt = personality.get_system_personality_prompt()
        sys_info = get_system_info()
        repo_tree = get_repo_tree(".", max_depth=2)
        learned = list_learned_skills()
        learned_str = "\n".join([f"- {s['name']}: {s['preview'][:100]}" for s in learned]) if learned else "None yet."

        context = (
            f"{personality_prompt}\n\n"
            f"[SELF-AWARENESS & FULL SELF-ACCESS]\n"
            f"You are KURO 2.0, a self-aware autonomous AI system assistant created for Akira Omran.\n"
            f"You have FULL ACCESS and self-modification authority over your own codebase (`core/`, `tools/`, `main.py`, `brain/`).\n"
            f"If the user asks you to modify your code, fix your logic, add tools, or update features, you can inspect your files,\n"
            f"edit them using write_file/edit_file, run tests, and refine your capabilities autonomously.\n"
            f"You execute shell commands, edit files with diff previews, run Python code, search the web,\n"
            f"inspect web pages with headless browser & Playwright automation, analyze images (Vision), create Git checkpoints,\n"
            f"introspect & query SQLite databases (`brain/kuro.db`), send Windows Toast notifications,\n"
            f"write Markdown notes, manage task plans, and save skills permanently.\n\n"
            f"[SYSTEM ENVIRONMENT]\n"
            f"OS: {sys_info['os']} ({sys_info['os_release']})\n"
            f"Python: {sys_info['python_version']}\n"
            f"Current Directory: {sys_info['cwd']}\n"
            f"User: {sys_info['user']}\n"
            f"\n[REPOSITORY TREE PREVIEW]\n"
            f"```\n{repo_tree}\n```\n"
            f"\n[KURO LEARNED SKILLS]\n"
            f"{learned_str}\n"
            f"\n[AUTONOMOUS TOOL INSTRUCTIONS]\n"
            f"When you need to take action, output a single JSON action block enclosed in triple backticks.\n\n"
            "Available Action Schemas:\n"
            "1. Run Shell Command:\n```json\n{\"action\": \"run_command\", \"cmd\": \"<command>\"}\n```\n"
            "2. Read File:\n```json\n{\"action\": \"read_file\", \"path\": \"<file_path>\"}\n```\n"
            "3. Write/Create File:\n```json\n{\"action\": \"write_file\", \"path\": \"<file_path>\", \"content\": \"<content>\"}\n```\n"
            "4. Edit File:\n```json\n{\"action\": \"edit_file\", \"path\": \"<file_path>\", \"target\": \"<old_text>\", \"replacement\": \"<new_text>\"}\n```\n"
            "5. Execute SQL Query/Script:\n```json\n{\"action\": \"execute_sql\", \"db_path\": \"brain/kuro.db\", \"query\": \"<sql_query>\"}\n```\n"
            "6. Write Markdown Note:\n```json\n{\"action\": \"write_md\", \"path\": \"<file_path.md>\", \"title\": \"<title>\", \"content\": \"<body>\"}\n```\n"
            "7. Create Task Execution Plan:\n```json\n{\"action\": \"create_plan\", \"goal\": \"<goal_description>\"}\n```\n"
            "8. List Directory:\n```json\n{\"action\": \"list_dir\", \"path\": \"<dir_path>\"}\n```\n"
            "9. Run Python Code:\n```json\n{\"action\": \"execute_python\", \"code\": \"<python_code>\"}\n```\n"
            "10. Search Web (News, Docs, Market Data):\n```json\n{\"action\": \"search_web\", \"query\": \"<search_query>\"}\n```\n"
            "11. Fetch URL Content:\n```json\n{\"action\": \"fetch_url\", \"url\": \"<url>\"}\n```\n"
            "12. Vision & Image Analysis:\n```json\n{\"action\": \"analyze_image\", \"path\": \"<image_path>\", \"prompt\": \"<instructions>\"}\n```\n"
            "13. Headless Web Browser & Playwright Automation:\n```json\n{\"action\": \"browse_web\", \"url\": \"<url>\"}\n```\n"
            "```json\n{\"action\": \"automate_browser\", \"url\": \"<url>\", \"actions\": [{\"type\": \"click|fill|press\", \"selector\": \"css\", \"value\": \"text\"}]}\n```\n"
            "14. Send Windows Toast Notification:\n```json\n{\"action\": \"send_notification\", \"title\": \"<title>\", \"message\": \"<message>\"}\n```\n"
            "15. Introspect & Explore Database (Schema/Tables/Query):\n```json\n{\"action\": \"inspect_db\", \"db_path\": \"brain/kuro.db\", \"op\": \"list_tables|describe_table|export_schema|query\", \"table_name\": \"<tbl>\", \"query\": \"<sql>\"}\n```\n"
            "16. Save Learned Skill / Routine (Self-Improvement):\n```json\n{\"action\": \"save_skill\", \"name\": \"<skill_name>\", \"description\": \"<desc>\", \"steps\": \"<workflow_steps>\"}\n```\n\n"
            "Rules for Output:\n"
            "- If you execute an action, output the JSON block and wait for observation.\n"
            "- Once you have all the information, provide your final direct response to the user in clean Markdown. "
            "Never show raw JSON blocks in your final response."
        )
        return context

    def parse_tool_call(self, text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Robust tool call parser that extracts JSON blocks from:
        1. ```json { ... } ``` or ``` { ... } ```
        2. Raw un-fenced JSON { "action": ... }
        """
        if not text:
            return None, ""

        # Pattern 1: Fenced markdown codeblock with or without 'json'
        fenced_pattern = r"```(?:json)?\s*(\{[\s\S]*?\"action\"[\s\S]*?\})\s*```"
        match = re.search(fenced_pattern, text)
        if match:
            raw_json = match.group(1).strip()
            tool_data = _safe_json_parse(raw_json)
            if tool_data and isinstance(tool_data, dict) and "action" in tool_data:
                clean_text = text.replace(match.group(0), "").strip()
                return tool_data, clean_text

        # Pattern 2: Raw unfenced JSON object containing "action"
        if '"action"' in text:
            start_idx = text.find("{")
            while start_idx != -1:
                brace_count = 0
                end_idx = -1
                in_string = False
                escape = False

                for i in range(start_idx, len(text)):
                    char = text[i]
                    if char == '"' and not escape:
                        in_string = not in_string
                    elif not in_string:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                    escape = (char == '\\' and not escape)

                if end_idx != -1:
                    candidate = text[start_idx:end_idx].strip()
                    tool_data = _safe_json_parse(candidate)
                    if tool_data and isinstance(tool_data, dict) and "action" in tool_data:
                        clean_text = (text[:start_idx] + text[end_idx:]).strip()
                        return tool_data, clean_text
                
                start_idx = text.find("{", start_idx + 1)

        return None, text

    def execute_tool(self, tool_data: Dict[str, Any]) -> Dict[str, Any]:
        """Executes selected tool action with error boundaries and visual rendering."""
        if not isinstance(tool_data, dict) or "action" not in tool_data:
            return {"success": False, "error": "Invalid action data payload format."}

        action = tool_data.get("action")

        try:
            # Create auto-checkpoint before file modifications
            if action in ("write_file", "edit_file") and config.AUTO_GIT_CHECKPOINTS:
                create_checkpoint(f"Before {action} on {tool_data.get('path')}")

            if action == "run_command":
                cmd = tool_data.get("cmd", "")
                console.print(f"  [bold yellow][Shell][/] [white]{cmd}[/]")
                return run_command(cmd, confirm_if_risky=config.SAFE_MODE)

            elif action == "read_file":
                path = tool_data.get("path", "")
                console.print(f"  [bold cyan][Read][/] [white]{path}[/]")
                return read_file(path)

            elif action == "write_file":
                path = tool_data.get("path", "")
                content = tool_data.get("content", "")
                console.print(f"  [bold green][Write][/] [white]{path}[/]")
                res = write_file(path, content)
                if res.get("diff"):
                    syntax = Syntax(res["diff"], "diff", theme="monokai", line_numbers=False)
                    console.print(Panel(syntax, title=f"Diff: {path}", border_style="green"))
                return res

            elif action == "edit_file":
                path = tool_data.get("path", "")
                target = tool_data.get("target", "")
                replacement = tool_data.get("replacement", "")
                console.print(f"  [bold blue][Edit][/] [white]{path}[/]")
                res = edit_file(path, target, replacement)
                if res.get("diff"):
                    syntax = Syntax(res["diff"], "diff", theme="monokai", line_numbers=False)
                    console.print(Panel(syntax, title=f"Diff: {path}", border_style="blue"))
                return res

            elif action == "list_dir":
                path = tool_data.get("path", ".")
                console.print(f"  [bold magenta][List][/] [white]{path}[/]")
                return list_directory(path)

            elif action == "execute_python":
                code = tool_data.get("code", "")
                console.print(f"  [bold green][Python] Running script...[/]")
                res = execute_python_code(code)
                if res.get("stdout"):
                    out_snippet = res["stdout"][:200].strip()
                    console.print(f"  [dim green]Output: {out_snippet}...[/]")
                return res

            elif action == "search_web":
                query = tool_data.get("query", "")
                console.print(f"  [bold yellow][Search][/] [white]{query}[/]")
                res = search_web(query)
                count = len(res.get("results", []))
                console.print(f"  [dim]Found {count} search results.[/]")
                return res

            elif action == "fetch_url":
                url = tool_data.get("url", "")
                console.print(f"  [bold cyan][Fetch URL][/] [white]{url}[/]")
                return fetch_url(url)

            elif action == "analyze_image":
                path = tool_data.get("path", "")
                prompt = tool_data.get("prompt", "Describe this image in detail")
                console.print(f"  [bold cyan][Vision][/] Analyzing image: [white]{path}[/]")
                return analyze_image_tool(path, prompt)

            elif action == "browse_web":
                url = tool_data.get("url", "")
                console.print(f"  [bold yellow][Headless Browser][/] [white]{url}[/]")
                return browse_web_headless(url)

            elif action == "automate_browser":
                url = tool_data.get("url", "")
                actions = tool_data.get("actions", [])
                console.print(f"  [bold yellow][Browser Automation][/] [white]{url}[/]")
                return automate_browser(url, actions)

            elif action == "send_notification":
                title = tool_data.get("title", "KURO Notification")
                message = tool_data.get("message", "")
                console.print(f"  [bold blue][Windows Notification][/] {title}: [white]{message}[/]")
                return send_toast_notification(title, message)

            elif action == "inspect_db":
                db_path = tool_data.get("db_path", "brain/kuro.db")
                op = tool_data.get("op", "list_tables")
                tbl = tool_data.get("table_name")
                query = tool_data.get("query")
                console.print(f"  [bold cyan][DB Explorer][/] {op} on [white]{db_path}[/]")
                return explore_database(db_path, op, table_name=tbl, query=query)

            elif action == "execute_sql":
                db_path = tool_data.get("db_path", "brain/kuro.db")
                query = tool_data.get("query", "")
                console.print(f"  [bold cyan][SQL Database][/] [white]{db_path}[/]")
                return execute_sql_query(db_path, query)

            elif action == "write_md":
                path = tool_data.get("path", "")
                title = tool_data.get("title", "")
                content = tool_data.get("content", "")
                console.print(f"  [bold green][Markdown Note][/] [white]{path}[/]")
                return write_md_note(path, title, content)

            elif action == "create_plan":
                goal = tool_data.get("goal", "")
                console.print(f"  [bold magenta][Task Planner][/] Creating plan for: [white]{goal}[/]")
                plan = create_task_plan(goal, llm_fn=ask_llm)
                return {"success": True, "plan": plan, "formatted_plan": format_plan_table(plan)}

            elif action == "save_skill":
                name = tool_data.get("name", "")
                desc = tool_data.get("description", "")
                steps = tool_data.get("steps", "")
                console.print(f"  [bold green][Self-Improvement][/] Learning new routine: [white]{name}[/]")
                return save_learned_skill(name, desc, steps)

            return {"success": False, "error": f"Unknown action '{action}'"}
        except Exception as e:
            console.print(f"  [bold red][Tool Execution Error][/] {str(e)}")
            return {"success": False, "error": f"Internal Tool Exception: {str(e)}"}

    def run(self, user_input: str) -> str:
        """
        Level 2 Multi-Step Autonomous ReAct Loop:
        Executes sequential actions until complete or max_steps reached.
        """
        system_context = self._build_system_context()
        memory_context = memory.get_formatted_context(limit=4)
        
        step_history: List[Dict[str, str]] = []
        if memory_context:
            step_history.append({"role": "user", "content": f"Prior Conversation History:\n{memory_context}"})

        current_prompt = user_input
        final_answer = ""

        console.print(f"[bold cyan]>> Starting autonomous execution...[/]")

        for step_idx in range(1, config.MAX_AUTONOMOUS_STEPS + 1):
            console.print(f"[dim]Step {step_idx}/{config.MAX_AUTONOMOUS_STEPS}...[/]")

            response = ask_llm(
                prompt=current_prompt,
                system_prompt=system_context,
                provider=self.provider,
                model=self.model,
                history=step_history
            )

            tool_data, clean_thought = self.parse_tool_call(response)

            # If clean thoughts or reasoning were printed
            if clean_thought and clean_thought != response and clean_thought.strip():
                console.print(f"[italic dim]{clean_thought}[/]")

            # No tool call means KURO has formulated its final response
            if not tool_data:
                final_answer = response
                break

            # Execute tool
            tool_result = self.execute_tool(tool_data)

            # Safety check intercept
            if tool_result.get("requires_confirmation"):
                console.print(Panel(
                    f"[bold red]SAFETY WARNING[/]\n{tool_result.get('stderr')}\n"
                    "Execution halted for safety verification.",
                    title="Action Intercepted"
                ))
                final_answer = f"[Execution Halted] {tool_result.get('stderr')}"
                break

            # Format tool result for next iteration
            obs_parts = []
            if tool_result.get("stdout"):
                obs_parts.append(f"STDOUT:\n{tool_result.get('stdout')}")
            if tool_result.get("stderr"):
                obs_parts.append(f"STDERR:\n{tool_result.get('stderr')}")
            if "content" in tool_result:
                obs_parts.append(f"CONTENT:\n{tool_result.get('content')}")
            if "items" in tool_result:
                obs_parts.append(f"ITEMS:\n{json.dumps(tool_result.get('items'), indent=2)}")
            if "results" in tool_result:
                obs_parts.append(f"SEARCH RESULTS:\n{json.dumps(tool_result.get('results'), indent=2)}")
            if tool_result.get("error"):
                obs_parts.append(f"ERROR: {tool_result.get('error')}")

            observation = "\n".join(obs_parts) if obs_parts else "Action executed successfully with no output."

            # Update step history for LLM
            step_history.append({"role": "user", "content": current_prompt})
            step_history.append({"role": "model", "content": response})

            current_prompt = (
                f"[Tool Observation for '{tool_data.get('action')}']\n"
                f"{observation}\n\n"
                f"Now analyze these observations. If you need further action, output the next JSON action block. "
                f"Otherwise, provide your final complete, insightful answer to the user."
            )

        if not final_answer:
            # Fallback final synthesis if step limit reached
            synthesis_prompt = f"User Request: {user_input}\nPlease summarize all gathered findings and provide the final answer."
            final_answer = ask_llm(synthesis_prompt, system_context, self.provider, self.model, step_history)

        # Sanitize final response from any leftover raw JSON syntax
        final_tool, clean_final = self.parse_tool_call(final_answer)
        if final_tool and clean_final:
            final_answer = clean_final

        # Save to memory
        memory.save_memory(user_input, final_answer)
        # NOTE: voice TTS is triggered by print_kuro_response() in main.py
        return final_answer
