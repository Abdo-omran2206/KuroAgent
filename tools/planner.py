"""
KURO Task Planning Engine (tools/planner.py)

Breaks down complex high-level goals into ordered execution plans,
stores them in SQLite persistent memory (memory_db.py), executes steps
sequentially with agent integration, and formats plans for Rich UI / terminal display.
"""

import io
import json
import time
import uuid
from typing import Dict, Any, List, Optional, Union
from core import memory_db

# Rich UI imports (with fallback)
try:
    from rich.table import Table
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def create_task_plan(goal: str, llm_fn=None) -> Dict[str, Any]:
    """Decomposes a complex goal into an ordered multi-step execution plan.
    
    Args:
        goal: High-level task or objective description.
        llm_fn: Optional callable taking (prompt, system_prompt) to generate LLM steps.
        
    Returns:
        dict matching structure:
        {
            "plan_id": "plan_xxx",
            "id": "plan_xxx",
            "title": "...",
            "goal": "...",
            "steps": [
                {
                    "step_num": 1,
                    "description": "...",
                    "tool_hint": "...",
                    "status": "pending"
                }
            ],
            "status": "pending"
        }
    """
    plan_id = f"plan_{uuid.uuid4().hex[:8]}"
    title = f"Task Plan: {goal[:45]}..." if len(goal) > 45 else f"Task Plan: {goal}"

    steps: List[Dict[str, Any]] = []

    if llm_fn:
        prompt = (
            f"You are KURO Task Planner. Break down the following high-level goal into 3 to 6 logical execution steps.\n"
            f"Goal: {goal}\n\n"
            f"Return ONLY valid JSON matching this exact structure:\n"
            f"{{\n"
            f'  "title": "Short descriptive title",\n'
            f'  "steps": [\n'
            f'    {{"step_num": 1, "description": "Clear step description", "tool_hint": "run_command|write_file|search_web|analyze_image"}},\n'
            f'    {{"step_num": 2, "description": "Next step description", "tool_hint": "..."}}\n'
            f'  ]\n'
            f"}}\n"
        )
        try:
            raw_res = llm_fn(prompt, system_prompt="You are a strict JSON task planner. Output ONLY JSON.")
            if isinstance(raw_res, str):
                clean_res = raw_res.strip()
                if "```" in clean_res:
                    clean_res = clean_res.split("```")[1]
                    if clean_res.startswith("json"):
                        clean_res = clean_res[4:]
                clean_res = clean_res.strip()
                parsed = json.loads(clean_res)
                if isinstance(parsed, dict):
                    title = parsed.get("title", title)
                    raw_steps = parsed.get("steps", [])
                    for i, s in enumerate(raw_steps, 1):
                        if isinstance(s, dict):
                            steps.append({
                                "step_num": s.get("step_num", i),
                                "description": s.get("description", str(s)),
                                "tool_hint": s.get("tool_hint", "auto"),
                                "status": "pending"
                            })
                        elif isinstance(s, str):
                            steps.append({
                                "step_num": i,
                                "description": s,
                                "tool_hint": "auto",
                                "status": "pending"
                            })
        except Exception as e:
            steps = []

    if not steps:
        # Fallback structured plan breakdown
        steps = [
            {
                "step_num": 1,
                "description": f"Analyze requirements and inspect environment for '{goal}'",
                "tool_hint": "list_directory",
                "status": "pending"
            },
            {
                "step_num": 2,
                "description": f"Execute main implementation and changes for '{goal}'",
                "tool_hint": "write_file",
                "status": "pending"
            },
            {
                "step_num": 3,
                "description": f"Verify execution results and validate completion for '{goal}'",
                "tool_hint": "run_command",
                "status": "pending"
            }
        ]
    else:
        for idx, s in enumerate(steps, 1):
            s["step_num"] = s.get("step_num", idx)
            s["status"] = "pending"

    # Save to SQLite DB
    plan = memory_db.save_plan(plan_id, title, goal, steps, status="pending")
    
    # Ensure dictionary contains both 'plan_id' and 'id'
    if isinstance(plan, dict):
        plan["plan_id"] = plan_id
        plan["id"] = plan_id
    else:
        plan = {
            "plan_id": plan_id,
            "id": plan_id,
            "title": title,
            "goal": goal,
            "steps": steps,
            "status": "pending"
        }
        
    return plan


def get_active_plan() -> Optional[Dict[str, Any]]:
    """Returns the most recent active/pending/in_progress plan from database."""
    plans = memory_db.list_plans()
    for p in plans:
        if p.get("status") in ("in_progress", "pending"):
            if "plan_id" not in p and "id" in p:
                p["plan_id"] = p["id"]
            return p
    return None


def execute_plan(plan_id: str, agent) -> Dict[str, Any]:
    """Executes all pending steps of a plan sequentially using the KURO agent.
    
    Updates database step status and plan status during execution.
    
    Args:
        plan_id: ID of the plan to execute.
        agent: Agent object with .run(prompt) method or callable agent function.
        
    Returns:
        Dict summarizing execution result and updated plan state.
    """
    plan = memory_db.get_plan(plan_id)
    if not plan:
        return {"success": False, "error": f"Plan '{plan_id}' not found."}

    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        return {"success": False, "error": f"Plan '{plan_id}' has invalid steps structure."}

    # Mark plan in_progress
    memory_db.save_plan(plan_id, plan.get("title", ""), plan.get("goal", ""), steps, status="in_progress")

    executed_count = 0
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            step = {"step_num": idx + 1, "description": str(step), "tool_hint": "auto", "status": "pending"}

        current_status = step.get("status", "pending")
        if current_status == "completed":
            continue

        step_num = step.get("step_num", idx + 1)
        step_desc = step.get("description", "")
        tool_hint = step.get("tool_hint", "auto")

        # Mark step in_progress
        memory_db.update_plan_step(plan_id, idx, "in_progress")

        agent_prompt = (
            f"[Executing Step {step_num}/{len(steps)}: {step_desc}]\n"
            f"Tool Hint: {tool_hint}\n"
            f"Overall Goal: {plan.get('goal')}"
        )

        try:
            if hasattr(agent, "run") and callable(agent.run):
                result_output = agent.run(agent_prompt)
            elif callable(agent):
                result_output = agent(agent_prompt)
            else:
                raise ValueError(f"Agent object {type(agent)} is neither callable nor has a .run() method.")

            res_str = str(result_output) if result_output is not None else "Completed"
            memory_db.update_plan_step(plan_id, idx, "completed", result=res_str[:300])
            executed_count += 1

        except Exception as e:
            err_msg = f"Step {step_num} failed: {e}"
            memory_db.update_plan_step(plan_id, idx, "failed", result=err_msg[:300])
            # Mark overall plan failed
            memory_db.save_plan(plan_id, plan.get("title", ""), plan.get("goal", ""), steps, status="failed")
            updated_plan = memory_db.get_plan(plan_id)
            if updated_plan:
                updated_plan["plan_id"] = plan_id
            return {
                "success": False,
                "error": err_msg,
                "failed_step_index": idx,
                "plan": updated_plan
            }

    # Mark overall plan completed
    memory_db.save_plan(plan_id, plan.get("title", ""), plan.get("goal", ""), steps, status="completed")
    final_plan = memory_db.get_plan(plan_id)
    if final_plan:
        final_plan["plan_id"] = plan_id
    return {
        "success": True,
        "executed_steps": executed_count,
        "plan": final_plan
    }


def execute_plan_step(plan_id: str, step_index: int, agent) -> Dict[str, Any]:
    """Executes a single specific step of a plan using the KURO agent."""
    plan = memory_db.get_plan(plan_id)
    if not plan:
        return {"success": False, "error": f"Plan '{plan_id}' not found."}

    steps = plan.get("steps", [])
    if step_index < 0 or step_index >= len(steps):
        return {"success": False, "error": f"Invalid step index {step_index}."}

    step = steps[step_index]
    step_desc = step.get("description", str(step)) if isinstance(step, dict) else str(step)
    tool_hint = step.get("tool_hint", "auto") if isinstance(step, dict) else "auto"

    memory_db.update_plan_step(plan_id, step_index, "in_progress")

    agent_prompt = f"[Executing Step {step_index + 1}/{len(steps)}: {step_desc}] Tool Hint: {tool_hint} | Goal: {plan.get('goal')}"

    try:
        if hasattr(agent, "run") and callable(agent.run):
            result_text = agent.run(agent_prompt)
        elif callable(agent):
            result_text = agent(agent_prompt)
        else:
            result_text = "Simulated step completion"

        updated_plan = memory_db.update_plan_step(plan_id, step_index, "completed", result=str(result_text)[:300])

        all_done = all(
            s.get("status") == "completed" for s in updated_plan.get("steps", []) if isinstance(s, dict)
        ) if updated_plan else False

        if all_done:
            memory_db.save_plan(plan_id, plan["title"], plan["goal"], updated_plan["steps"], status="completed")

        return {"success": True, "step_index": step_index, "result": result_text, "all_done": all_done}

    except Exception as e:
        memory_db.update_plan_step(plan_id, step_index, "failed", result=str(e)[:300])
        return {"success": False, "step_index": step_index, "error": str(e)}


def format_plan_for_ui(plan: Dict[str, Any]) -> Union[str, Any]:
    """Formats plan status as a Rich Table (if rich available) or text representation.
    
    Args:
        plan: Plan dictionary.
        
    Returns:
        Formatted string (or Rich table string rendering).
    """
    if not plan:
        return "No active plan found."

    plan_id = plan.get("plan_id", plan.get("id", "N/A"))
    title = plan.get("title", "Execution Plan")
    goal = plan.get("goal", "")
    status = plan.get("status", "pending")
    steps = plan.get("steps", [])

    if HAS_RICH:
        table = Table(title=f"📋 {title}\nGoal: {goal} [Status: {status}]", show_header=True, header_style="bold magenta")
        table.add_column("#", style="cyan", width=4, justify="right")
        table.add_column("Status", width=14)
        table.add_column("Description", style="white")
        table.add_column("Tool Hint", style="yellow")
        table.add_column("Result", style="dim white")

        for idx, s in enumerate(steps, 1):
            if isinstance(s, dict):
                step_num = str(s.get("step_num", idx))
                s_status = s.get("status", "pending")
                
                if s_status == "completed":
                    status_str = "[bold green]✅ Completed[/bold green]"
                elif s_status == "in_progress":
                    status_str = "[bold yellow]⏳ In Progress[/bold yellow]"
                elif s_status == "failed":
                    status_str = "[bold red]❌ Failed[/bold red]"
                else:
                    status_str = "[dim]⚪ Pending[/dim]"
                    
                desc = s.get("description", "")
                hint = s.get("tool_hint", "")
                res = str(s.get("result", ""))[:40]
            else:
                step_num = str(idx)
                status_str = "[dim]⚪ Pending[/dim]"
                desc = str(s)
                hint = "auto"
                res = ""
                
            table.add_row(step_num, status_str, desc, hint, res)

        console = Console(file=io.StringIO(), force_terminal=False)
        console.print(table)
        return console.file.getvalue()

    else:
        lines = [
            f"📋 **{title}** (ID: `{plan_id}`)",
            f"Goal: {goal}",
            f"Overall Status: `{status}`",
            "",
            "Steps:"
        ]
        for idx, s in enumerate(steps, 1):
            if isinstance(s, dict):
                s_num = s.get("step_num", idx)
                s_status = s.get("status", "pending")
                badge = "✅" if s_status == "completed" else ("⏳" if s_status == "in_progress" else ("❌" if s_status == "failed" else "⚪"))
                desc = s.get("description", "")
                hint = f" [`{s.get('tool_hint', 'auto')}`]" if s.get("tool_hint") else ""
                lines.append(f"  {badge} {s_num}. {desc}{hint} [{s_status}]")
            else:
                lines.append(f"  ⚪ {idx}. {s}")
        return "\n".join(lines)


def format_plan_table(plan: Dict[str, Any]) -> str:
    """Alias for format_plan_for_ui for backwards compatibility."""
    res = format_plan_for_ui(plan)
    return str(res)
