"""
Unified experiment schema for the autoresearch dashboard.

Each experiment produces one ExperimentRecord. The agent writes it as JSON
after every run. The dashboard reads these to build views.

Usage in train.py:
    from schema import ExperimentRecord, dump_record
    # ... after training ...
    record = ExperimentRecord(...)
    dump_record(record, "experiments.jsonl")
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ExperimentRecord:
    # ── Identity ──
    id: int                          # monotonic experiment number
    commit: str                      # git short hash of the code that ran
    parent_commit: str               # commit this experiment built on (for tree view)
    timestamp: str                   # ISO 8601 UTC
    status: str                      # keep | discard | crash
    description: str                 # what was tried

    # ── Result (the only thing that matters for keep/discard) ──
    val_bpb: float                   # primary metric
    delta: float                     # change vs previous best (negative = improvement)

    # ── Convergence (why it worked or didn't) ──
    train_bpb: float                 # final training loss — gap to val_bpb reveals overfit
    bpb_at_checkpoints: list[float]  # val_bpb sampled at 25%, 50%, 75%, 100% of training
    still_improving: bool            # was loss still dropping in last 25% of training?
    improvement_rate: float          # bpb decrease per step in last 25% (negative = improving)

    # ── Efficiency (throughput vs quality tradeoff) ──
    num_steps: int                   # optimizer steps completed
    tokens_per_second: int           # throughput
    training_seconds: float          # wall clock training time
    total_seconds: float             # wall clock including startup/eval
    mfu_percent: float               # model flops utilization
    total_tokens_M: float            # millions of tokens processed

    # ── Resources (hard constraints) ──
    peak_vram_gb: float              # peak GPU memory
    gpu_name: str                    # e.g. "H100-SXM", "A100-SXM4"

    # ── Architecture (what the model looked like) ──
    num_params_M: float              # millions of parameters
    depth: int                       # transformer layers
    model_dim: int                   # embedding dimension
    n_heads: int                     # attention heads
    head_dim: int                    # per-head dimension
    window_pattern: str              # attention window pattern e.g. "SSSL"

    # ── Optimization (what the optimizer looked like) ──
    total_batch_size: int
    device_batch_size: int
    matrix_lr: float
    embedding_lr: float
    weight_decay: float
    warmdown_ratio: float
    adam_betas: list[float]

    # ── Diff (what changed) ──
    diff_stat: str = ""              # e.g. "3 insertions, 2 deletions"
    diff_hash: str = ""              # hash of the diff itself (dedup identical changes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    def to_json_pretty(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    # ── Dashboard row (the flat TSV view) ──
    def to_row(self) -> str:
        """One-line TSV for results.tsv compatibility."""
        return "\t".join([
            self.commit,
            f"{self.val_bpb:.6f}",
            f"{self.peak_vram_gb:.1f}",
            self.status,
            self.description,
        ])


def dump_record(record: ExperimentRecord, path: str | Path) -> None:
    """Append one record as a JSON line to the given file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(record.to_json() + "\n")


def load_records(path: str | Path) -> list[ExperimentRecord]:
    """Read all records from a JSONL file."""
    p = Path(path)
    if not p.exists():
        return []
    records = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            records.append(ExperimentRecord(**json.loads(line)))
    return records


def next_id(path: str | Path) -> int:
    """Return the next experiment ID."""
    records = load_records(path)
    if not records:
        return 1
    return max(r.id for r in records) + 1


def current_best(path: str | Path) -> float:
    """Return the best val_bpb from kept experiments, or inf if none."""
    records = load_records(path)
    kept = [r.val_bpb for r in records if r.status == "keep"]
    return min(kept) if kept else float("inf")


def git_short_hash() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return r.stdout.strip()
    except Exception:
        return "nogit"


def git_diff_stat() -> str:
    try:
        r = subprocess.run(
            ["git", "diff", "--stat", "HEAD~1"],
            capture_output=True, text=True, check=True,
        )
        lines = r.stdout.strip().splitlines()
        return lines[-1].strip() if lines else ""
    except Exception:
        return ""


def git_diff_hash() -> str:
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD~1"],
            capture_output=True, text=True, check=True,
        )
        import hashlib
        return hashlib.sha1(r.stdout.encode()).hexdigest()[:7]
    except Exception:
        return ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
