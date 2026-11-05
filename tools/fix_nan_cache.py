"""
One-shot script to sanitize all NaN/Infinity values and clean up corrupted pattern cache records.
"""
import sqlite3
import json
import math
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import CACHE_DB_PATH


def sanitize(obj):
    """Recursively replace NaN/Inf floats with None so the JSON is browser-safe."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


def fix_cache():
    conn = sqlite3.connect(CACHE_DB_PATH)
    cur = conn.cursor()

    # 1. Clean up corrupted synthesizer outputs that had the 474.49 entry ceiling anomaly
    cur.execute("DELETE FROM agent_runs_cache WHERE output_data LIKE '%474.49%'")
    print(f"Deleted {cur.rowcount} stale records with 474.49 anomaly.")

    # 2. Fix NaN/Infinity records
    cur.execute("SELECT run_id, output_data FROM agent_runs_cache")
    rows = cur.fetchall()
    fixed = 0
    for run_id, output_data in rows:
        if not output_data:
            continue
        if "NaN" not in output_data and "Infinity" not in output_data:
            continue
        try:
            parsed = json.loads(output_data)
            clean = sanitize(parsed)
            clean_json = json.dumps(clean)
            cur.execute(
                "UPDATE agent_runs_cache SET output_data = ? WHERE run_id = ?",
                (clean_json, run_id)
            )
            fixed += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    print(f"Done. Fixed {fixed} NaN records.")


if __name__ == "__main__":
    fix_cache()
