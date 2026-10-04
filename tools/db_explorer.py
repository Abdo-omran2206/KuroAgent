import sqlite3
import json
from pathlib import Path
from typing import Any, Dict
from tools.files import is_read_sql_query

def explore_database(db_path: str, op: str = "list_tables", table_name: str = None, query: str = None) -> Dict[str, Any]:
    """
    DB Explorer Tool: Introspects database structures, previews table contents,
    executes queries, and exports database schemas.
    """
    target = Path(db_path)
    if not target.exists():
        return {"success": False, "error": f"Database file not found: '{db_path}'"}

    try:
        conn = sqlite3.connect(target)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if op == "list_tables":
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row["name"] for row in cursor.fetchall()]
            
            # Fetch row counts for each table
            table_info = []
            for t in tables:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM [{t}]")
                cnt = cursor.fetchone()["cnt"]
                table_info.append({"table": t, "row_count": cnt})
                
            conn.close()
            return {"success": True, "db_path": str(target), "tables": table_info}

        elif op == "describe_table":
            if not table_name:
                conn.close()
                return {"success": False, "error": "table_name argument is required for describe_table operation."}

            cursor.execute(f"PRAGMA table_info([{table_name}]);")
            columns = [
                {
                    "cid": row["cid"],
                    "name": row["name"],
                    "type": row["type"],
                    "notnull": bool(row["notnull"]),
                    "pk": bool(row["pk"])
                }
                for row in cursor.fetchall()
            ]

            # Grab 5 sample rows
            cursor.execute(f"SELECT * FROM [{table_name}] LIMIT 5;")
            sample_rows = [dict(r) for r in cursor.fetchall()]

            conn.close()
            return {
                "success": True,
                "table": table_name,
                "columns": columns,
                "sample_rows": sample_rows
            }

        elif op == "export_schema":
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            schemas = {row["name"]: row["sql"] for row in cursor.fetchall()}
            conn.close()

            md_lines = [f"# Database Schema Summary: `{target.name}`\n"]
            for tbl, sql in schemas.items():
                md_lines.append(f"## Table: `{tbl}`\n```sql\n{sql}\n```\n")
            
            schema_md = "\n".join(md_lines)
            return {"success": True, "db_path": str(target), "schema_md": schema_md}

        elif op == "query":
            if not query:
                conn.close()
                return {"success": False, "error": "query argument is required for query operation."}

            cursor.execute(query)
            if is_read_sql_query(query):
                rows = [dict(r) for r in cursor.fetchall()]
                conn.close()
                return {"success": True, "rows": rows, "count": len(rows)}
            else:
                conn.commit()
                affected = cursor.rowcount
                conn.close()
                return {"success": True, "affected_rows": affected}

        else:
            conn.close()
            return {"success": False, "error": f"Unknown DB operation '{op}'."}

    except Exception as e:
        return {"success": False, "error": f"Database Explorer Exception: {str(e)}"}
