"""
Run 5 experiments with varying hyperparameters against the dashboard.
Each run uses a 30-second time budget for speed.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TRAIN_PY = Path(__file__).parent / "train.py"
REASONING = Path(__file__).parent / "reasoning.jsonl"
ORIG_CONTENT = TRAIN_PY.read_text()

EXPERIMENTS = [
    {
        "name": "deeper model (depth=6)",
        "changes": {"DEPTH = 4": "DEPTH = 6"},
        "intent": "Increase model depth from 4 to 6",
        "hypothesis": "More layers should improve capacity and lower val_bpb",
    },
    {
        "name": "higher matrix_lr (0.04)",
        "changes": {"MATRIX_LR = 0.02": "MATRIX_LR = 0.04"},
        "intent": "Double matrix learning rate from 0.02 to 0.04",
        "hypothesis": "Faster learning may converge to better loss in limited time budget",
    },
    {
        "name": "larger batch (2**17)",
        "changes": {"TOTAL_BATCH_SIZE = 2**16": "TOTAL_BATCH_SIZE = 2**17"},
        "intent": "Double the total batch size from 64K to 128K tokens",
        "hypothesis": "Larger batches give more stable gradients, possibly better final loss",
    },
    {
        "name": "warmup 10% + warmdown 60%",
        "changes": {"WARMUP_RATIO = 0.0": "WARMUP_RATIO = 0.1", "WARMDOWN_RATIO = 0.5": "WARMDOWN_RATIO = 0.6"},
        "intent": "Add 10% warmup and extend warmdown to 60%",
        "hypothesis": "Gradual LR warmup prevents early instability; longer cooldown gives smoother convergence",
    },
    {
        "name": "depth=6 + higher LR + warmup",
        "changes": {
            "DEPTH = 4": "DEPTH = 6",
            "MATRIX_LR = 0.02": "MATRIX_LR = 0.03",
            "WARMUP_RATIO = 0.0": "WARMUP_RATIO = 0.1",
        },
        "intent": "Combine depth=6 with matrix_lr=0.03 and 10% warmup",
        "hypothesis": "Deeper model with tuned LR and warmup could compound improvements",
    },
]


def apply_changes(changes: dict) -> str:
    content = ORIG_CONTENT
    for old, new in changes.items():
        content = content.replace(old, new)
    return content


def extract_val_bpb(output: str) -> float | None:
    m = re.search(r"val_bpb:\s+([\d.]+)", output)
    return float(m.group(1)) if m else None


def get_last_run_id() -> str | None:
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/api/runs")
        runs = json.loads(resp.read())
        if runs:
            return runs[0]["run_id"]
    except Exception:
        pass
    return None


def main():
    parent_id = get_last_run_id()  # chain from last existing run
    best_bpb = None

    # Get best bpb from existing runs
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/api/runs")
        existing_runs = json.loads(resp.read())
        for r in existing_runs:
            if r.get("accepted") == 1 and r.get("val_bpb") is not None:
                if best_bpb is None or r["val_bpb"] < best_bpb:
                    best_bpb = r["val_bpb"]
                    parent_id = r["run_id"]
    except Exception:
        pass

    print(f"Starting from parent_id={parent_id}, best_bpb={best_bpb}")
    results = []

    for i, exp in enumerate(EXPERIMENTS, 1):
        print(f"\n{'='*60}")
        print(f"EXPERIMENT {i}/5: {exp['name']}")
        print(f"{'='*60}")

        modified = apply_changes(exp["changes"])
        TRAIN_PY.write_text(modified)

        note = {
            "type": "agent_note",
            "run_id": parent_id or "pending",
            "intent": exp["intent"],
            "hypothesis": exp["hypothesis"],
        }
        with open(REASONING, "a") as f:
            f.write(json.dumps(note) + "\n")

        env = os.environ.copy()
        if parent_id:
            env["PARENT_RUN_ID"] = parent_id

        result = subprocess.run(
            ["uv", "run", "train.py", "--time-budget", "30"],
            capture_output=True, text=True, timeout=300, env=env,
        )

        output = result.stdout + result.stderr
        val_bpb = extract_val_bpb(output)
        run_id = get_last_run_id()

        if val_bpb is not None:
            improved = best_bpb is None or val_bpb < best_bpb
            accepted = improved

            if accepted:
                best_bpb = val_bpb
                parent_id = run_id

            decision = {
                "type": "accept_decision",
                "run_id": run_id,
                "accepted": accepted,
                "reason": f"val_bpb={val_bpb:.6f} {'< best' if accepted else '>= best'} ({best_bpb:.6f})",
            }
            with open(REASONING, "a") as f:
                f.write(json.dumps(decision) + "\n")

            status = "ACCEPTED" if accepted else "REJECTED"
            print(f"  val_bpb = {val_bpb:.6f} [{status}] (best = {best_bpb:.6f})")
            results.append((i, exp["name"], val_bpb, status))
        else:
            print(f"  FAILED (no val_bpb)")
            print(f"  stdout: {result.stdout[-500:]}")
            print(f"  stderr: {result.stderr[-500:]}")
            results.append((i, exp["name"], None, "FAILED"))

    # Restore original train.py
    TRAIN_PY.write_text(ORIG_CONTENT)

    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    for num, name, bpb, status in results:
        bpb_str = f"{bpb:.6f}" if bpb else "N/A"
        print(f"  {num:2d}. {name:35s} {bpb_str}  {status}")
    print(f"\nBest val_bpb: {best_bpb:.6f}" if best_bpb else "\nNo successful runs")


if __name__ == "__main__":
    main()
