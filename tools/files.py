import difflib
from pathlib import Path
from typing import Dict, Any, List, Optional
from rich.syntax import Syntax


def resolve_path(path_str: str) -> Path:
    """Resolves and returns absolute pathlib.Path."""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def read_file(path_str: str) -> Dict[str, Any]:
    """Reads content from a file."""
    try:
        p = resolve_path(path_str)
        if not p.exists():
            return {"success": False, "content": "", "error": f"File '{path_str}' does not exist."}
        if not p.is_file():
            return {"success": False, "content": "", "error": f"Path '{path_str}' is not a file."}
        
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"success": True, "content": content, "error": None}
    except Exception as e:
        return {"success": False, "content": "", "error": str(e)}


def generate_diff(old_content: str, new_content: str, filename: str = "file") -> str:
    """Generates standard unified diff representation between two texts."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}")
    return "".join(diff)


def create_file(path_str: str, content: str = "") -> Dict[str, Any]:
    """Creates a new file with optional content."""
    try:
        p = resolve_path(path_str)
        if p.exists():
            return {"success": False, "error": f"File '{path_str}' already exists."}
        
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        diff = generate_diff("", content, p.name)
        return {"success": True, "path": str(p), "diff": diff, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path_str: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
    """Writes or overwrites content to a file, capturing unified diff."""
    try:
        p = resolve_path(path_str)
        old_content = ""
        if p.exists():
            if not overwrite:
                return {"success": False, "error": f"File '{path_str}' exists and overwrite is False."}
            old_content = p.read_text(encoding="utf-8", errors="replace")
        
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        diff = generate_diff(old_content, content, p.name)
        return {"success": True, "path": str(p), "diff": diff, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def edit_file(path_str: str, target: str, replacement: str) -> Dict[str, Any]:
    """Edits a file by replacing instances of target text with replacement text."""
    try:
        p = resolve_path(path_str)
        if not p.exists() or not p.is_file():
            return {"success": False, "error": f"File '{path_str}' not found."}
        
        old_content = p.read_text(encoding="utf-8")
        if target not in old_content:
            return {"success": False, "error": f"Target string not found in '{path_str}'."}
        
        new_content = old_content.replace(target, replacement)
        p.write_text(new_content, encoding="utf-8")
        diff = generate_diff(old_content, new_content, p.name)
        return {"success": True, "path": str(p), "diff": diff, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_directory(path_str: str = ".") -> Dict[str, Any]:
    """Lists files and directories in specified path."""
    try:
        p = resolve_path(path_str)
        if not p.exists():
            return {"success": False, "items": [], "error": f"Directory '{path_str}' does not exist."}
        if not p.is_dir():
            return {"success": False, "items": [], "error": f"Path '{path_str}' is not a directory."}
        
        items: List[Dict[str, Any]] = []
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            # Skip hidden git / pycache
            if item.name.startswith(".git") or item.name == "__pycache__":
                continue
            items.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0
            })
        return {"success": True, "path": str(p), "items": items, "error": None}
    except Exception as e:
        return {"success": False, "items": [], "error": str(e)}


def execute_sql_query(db_path_str: str, query: str, params: tuple = ()) -> Dict[str, Any]:
    """Executes a SQL query or script against a SQLite database file (.db / .sql)."""
    import sqlite3
    try:
        p = resolve_path(db_path_str)
        if not p.exists():
            return {"success": False, "error": f"Database file '{db_path_str}' does not exist."}

        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # If query contains multiple SQL statements (script)
        if ";" in query and ("CREATE" in query.upper() or "INSERT" in query.upper() or "UPDATE" in query.upper()):
            cursor.executescript(query)
            conn.commit()
            conn.close()
            return {"success": True, "rows": [], "message": "SQL script executed successfully."}

        cursor.execute(query, params)
        if query.strip().upper().startswith(("SELECT", "PRAGMA", "EXPLAIN")):
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return {"success": True, "rows": rows, "count": len(rows)}
        else:
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            return {"success": True, "affected_rows": affected, "message": f"{affected} row(s) updated."}
    except Exception as e:
        return {"success": False, "error": f"SQL Execution Error: {str(e)}"}


def write_md_note(path_str: str, title: str, body: str, metadata: dict = None) -> Dict[str, Any]:
    """Writes a formatted Markdown note (.md) file to project assets / memory."""
    meta_str = ""
    if metadata:
        import json
        meta_str = "```json\n" + json.dumps(metadata, indent=2) + "\n```\n\n"
    content = f"# {title}\n\n{meta_str}{body}\n"
    return write_file(path_str, content, overwrite=True)


def get_repo_tree(root_dir: str = ".", max_depth: int = 3) -> str:
    """Generates visual directory tree for system context."""
    root = resolve_path(root_dir)
    lines = [f"{root.name}/"]

    def _walk(directory: Path, prefix: str, depth: int):
        if depth > max_depth:
            return
        entries = [e for e in sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                   if not e.name.startswith(".") and e.name != "__pycache__"]
        count = len(entries)
        for i, entry in enumerate(entries):
            is_last = (i == count - 1)
            connector = "\\-- " if is_last else "|-- "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                new_prefix = prefix + ("    " if is_last else "|   ")
                _walk(entry, new_prefix, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    try:
        _walk(root, "", 1)
        return "\n".join(lines)
    except Exception:
        return ""


