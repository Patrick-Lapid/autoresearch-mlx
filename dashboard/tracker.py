"""
Event emitter + SQLite writer for the autoresearch dashboard.
Imported by train.py to log runs, steps, and agent notes.
All DB writes happen on a background thread so they never block training.
"""

import asyncio
import json
import queue
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path

DB_PATH = Path(__file__).parent / "runs.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_q: queue.Queue = queue.Queue()
_sse_subscribers: list = []  # list of asyncio.Queue, populated by server.py
_loop = None  # will be set to the asyncio event loop by server.py


def init_db():
    """Called once at server/tracker start. Idempotent."""
    con = sqlite3.connect(str(DB_PATH))
    con.executescript(SCHEMA_PATH.read_text())
    con.close()


def _next_iteration() -> int:
    """Get the next iteration number."""
    con = sqlite3.connect(str(DB_PATH))
    row = con.execute("SELECT MAX(iteration) FROM runs").fetchone()
    con.close()
    return (row[0] or 0) + 1


def start_run(config: dict, parent_run_id: str | None = None) -> str:
    """
    Called at the top of train.py __main__ block.
    Returns a run_id (uuid4 short). Writes a 'run_start' event.
    """
    init_db()
    run_id = uuid.uuid4().hex[:8]
    iteration = _next_iteration()
    now = time.time()

    row = {
        "run_id": run_id,
        "iteration": iteration,
        "started_at": now,
        "status": "running",
        "parent_run_id": parent_run_id,
        "depth": config.get("depth"),
        "total_batch_size": config.get("total_batch_size"),
        "device_batch_size": config.get("device_batch_size"),
        "embedding_lr": config.get("embedding_lr"),
        "unembedding_lr": config.get("unembedding_lr"),
        "matrix_lr": config.get("matrix_lr"),
        "scalar_lr": config.get("scalar_lr"),
        "weight_decay": config.get("weight_decay"),
        "warmup_ratio": config.get("warmup_ratio"),
        "warmdown_ratio": config.get("warmdown_ratio"),
        "final_lr_frac": config.get("final_lr_frac"),
        "adam_betas": json.dumps(config.get("adam_betas")),
        "window_pattern": config.get("window_pattern"),
        "aspect_ratio": config.get("aspect_ratio"),
        "head_dim": config.get("head_dim"),
        "time_budget": config.get("time_budget"),
    }

    event = {
        "type": "run_start",
        "run_id": run_id,
        "iteration": iteration,
        "parent_run_id": parent_run_id,
        "config": config,
    }
    _q.put(("insert_run", row, event))
    return run_id


def log_step(run_id: str, step: int, wall_time: float, loss: float,
             smooth_loss: float, lrm: float, tok_per_sec: int,
             pct_done: float, epoch: int):
    """
    Called every step inside the training loop.
    Enqueues a 'step' event; background thread writes to steps table.
    """
    if run_id is None:
        return
    row = {
        "run_id": run_id,
        "step": step,
        "wall_time": wall_time,
        "loss": loss,
        "smooth_loss": smooth_loss,
        "lrm": lrm,
        "tok_per_sec": tok_per_sec,
        "pct_done": pct_done,
        "epoch": epoch,
    }
    event = {"type": "step", "run_id": run_id, **row}
    _q.put(("insert_step", row, event))


def end_run(run_id: str, val_bpb: float | None, accepted: bool | None,
            summary: dict):
    """
    Called after evaluate_bpb() returns.
    Captures git diff vs parent. Writes 'run_end' event.
    """
    if run_id is None:
        return

    diff_patch = _capture_diff()
    status = "completed" if val_bpb is not None else "failed"

    updates = {
        "ended_at": time.time(),
        "status": status,
        "accepted": (1 if accepted else 0) if accepted is not None else None,
        "val_bpb": val_bpb,
        "num_params_m": summary.get("num_params_m"),
        "total_tokens_m": summary.get("total_tokens_m"),
        "num_steps": summary.get("num_steps"),
        "training_seconds": summary.get("training_seconds"),
        "peak_vram_mb": summary.get("peak_vram_mb"),
        "mfu_percent": summary.get("mfu_percent"),
        "diff_patch": diff_patch,
    }

    event = {
        "type": "run_end",
        "run_id": run_id,
        "val_bpb": val_bpb,
        "accepted": accepted,
        "summary": summary,
    }
    _q.put(("update_run", run_id, updates, event))
    flush()


def mark_accepted(run_id: str, accepted: bool):
    """Called by server.py when it parses an accept_decision from reasoning.jsonl."""
    updates = {"accepted": 1 if accepted else 0}
    event = {
        "type": "accept_decision",
        "run_id": run_id,
        "accepted": accepted,
    }
    _q.put(("update_run", run_id, updates, event))


def log_agent_note(run_id: str, intent: str, hypothesis: str, raw: str):
    """
    Called when an agent_note event is parsed from reasoning.jsonl.
    """
    now = time.time()
    row = {
        "run_id": run_id,
        "ts": now,
        "intent": intent,
        "hypothesis": hypothesis,
        "raw": raw,
    }
    event = {
        "type": "agent_note",
        "run_id": run_id,
        "intent": intent,
        "hypothesis": hypothesis,
    }
    _q.put(("insert_note", row, event))


def register_subscriber(q: asyncio.Queue):
    _sse_subscribers.append(q)


def unregister_subscriber(q: asyncio.Queue):
    try:
        _sse_subscribers.remove(q)
    except ValueError:
        pass


def set_event_loop(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop


def _capture_diff() -> str:
    """Capture unified diff of working tree (train.py changes)."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--", "train.py"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).parent.parent,
        )
        return result.stdout or ""
    except Exception:
        return ""


def _fan_out(event: dict):
    """Push event to all SSE subscriber queues."""
    for sub_q in list(_sse_subscribers):
        if _loop is not None:
            _loop.call_soon_threadsafe(sub_q.put_nowait, event)


def _worker():
    """Background thread: drains _q, writes to SQLite, fans out to SSE subscribers."""
    con = sqlite3.connect(str(DB_PATH))
    con.execute("PRAGMA journal_mode=WAL")

    while True:
        try:
            item = _q.get(timeout=1.0)
        except queue.Empty:
            continue

        try:
            op = item[0]

            if op == "insert_run":
                _, row, event = item
                cols = ", ".join(row.keys())
                placeholders = ", ".join(["?"] * len(row))
                con.execute(
                    f"INSERT INTO runs ({cols}) VALUES ({placeholders})",
                    list(row.values()),
                )
                con.commit()
                _fan_out(event)

            elif op == "insert_step":
                _, row, event = item
                cols = ", ".join(row.keys())
                placeholders = ", ".join(["?"] * len(row))
                con.execute(
                    f"INSERT INTO steps ({cols}) VALUES ({placeholders})",
                    list(row.values()),
                )
                con.commit()
                _fan_out(event)

            elif op == "update_run":
                _, run_id, updates, event = item
                set_clauses = ", ".join(f"{k} = ?" for k in updates.keys())
                con.execute(
                    f"UPDATE runs SET {set_clauses} WHERE run_id = ?",
                    list(updates.values()) + [run_id],
                )
                con.commit()
                _fan_out(event)

            elif op == "insert_note":
                _, row, event = item
                cols = ", ".join(row.keys())
                placeholders = ", ".join(["?"] * len(row))
                con.execute(
                    f"INSERT INTO agent_notes ({cols}) VALUES ({placeholders})",
                    list(row.values()),
                )
                con.commit()
                _fan_out(event)

        except Exception as e:
            print(f"[tracker] error processing {item[0]}: {e}")


def flush(timeout: float = 5.0):
    """Block until the queue is drained or timeout expires."""
    deadline = time.time() + timeout
    while not _q.empty() and time.time() < deadline:
        time.sleep(0.05)


# Start background writer thread
_thread = threading.Thread(target=_worker, daemon=True)
_thread.start()
