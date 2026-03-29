"""
FastAPI server for the autoresearch dashboard.
SSE streaming, REST API, reasoning.jsonl tailing, and static file hosting.
"""

import asyncio
import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from dashboard import tracker

DB_PATH = tracker.DB_PATH
REPO_ROOT = Path(__file__).parent.parent
REASONING_JSONL = REPO_ROOT / "reasoning.jsonl"

app = FastAPI(title="autoresearch dashboard")


@app.on_event("startup")
async def startup():
    tracker.init_db()
    tracker.set_event_loop(asyncio.get_running_loop())
    asyncio.create_task(_tail_reasoning_jsonl())


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------

@app.get("/stream")
async def stream(request: Request):
    q: asyncio.Queue = asyncio.Queue()
    tracker.register_subscriber(q)

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"data": json.dumps(event)}
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield {"comment": "keepalive"}
        finally:
            tracker.unregister_subscriber(q)

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

def _get_db():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


@app.get("/api/runs")
async def list_runs():
    con = _get_db()
    rows = con.execute("SELECT * FROM runs ORDER BY iteration DESC").fetchall()
    con.close()
    return [dict(r) for r in rows]


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    con = _get_db()
    run = con.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        con.close()
        return JSONResponse(status_code=404, content={"error": "run not found"})

    steps = con.execute(
        "SELECT * FROM steps WHERE run_id = ? ORDER BY step ASC", (run_id,)
    ).fetchall()

    notes = con.execute(
        "SELECT * FROM agent_notes WHERE run_id = ? ORDER BY ts ASC", (run_id,)
    ).fetchall()

    con.close()
    return {
        "run": dict(run),
        "steps": [dict(s) for s in steps],
        "notes": [dict(n) for n in notes],
    }


@app.get("/api/runs/{run_id}/diff")
async def get_diff(run_id: str):
    con = _get_db()
    row = con.execute(
        "SELECT diff_patch FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    con.close()
    if row is None:
        return JSONResponse(status_code=404, content={"error": "run not found"})
    return JSONResponse(content={"diff": row["diff_patch"] or ""})


# ---------------------------------------------------------------------------
# reasoning.jsonl tailer
# ---------------------------------------------------------------------------

async def _tail_reasoning_jsonl():
    """Background task that tails reasoning.jsonl and pushes events to SSE."""
    pos = 0
    if REASONING_JSONL.exists():
        pos = REASONING_JSONL.stat().st_size

    while True:
        await asyncio.sleep(1.0)
        if not REASONING_JSONL.exists():
            continue

        size = REASONING_JSONL.stat().st_size
        if size <= pos:
            if size < pos:
                pos = 0  # file was truncated
            continue

        try:
            with open(REASONING_JSONL, "r") as f:
                f.seek(pos)
                new_data = f.read()
                pos = f.tell()

            for line in new_data.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = obj.get("type")
                run_id = obj.get("run_id", "")

                if event_type == "agent_note":
                    tracker.log_agent_note(
                        run_id,
                        intent=obj.get("intent", ""),
                        hypothesis=obj.get("hypothesis", ""),
                        raw=line,
                    )
                elif event_type == "accept_decision":
                    accepted = obj.get("accepted", False)
                    tracker.mark_accepted(run_id, accepted)

        except Exception as e:
            print(f"[server] error tailing reasoning.jsonl: {e}")


# ---------------------------------------------------------------------------
# Static files (Svelte build) — must be last so it doesn't shadow API routes
# ---------------------------------------------------------------------------

_dist = Path(__file__).parent / "frontend" / "build"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")
