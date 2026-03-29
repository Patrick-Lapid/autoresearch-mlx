"""
Run 10 experiments with varying hyperparameters against the dashboard.
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
        "name": "baseline",
        "changes": {},
        "intent": "Establish baseline with default hyperparameters",
        "hypothesis": "Default config gives us a reference val_bpb to improve upon",
    },
    {
        "name": "deeper model (depth=6)",
        "changes": {"DEPTH = 4": "DEPTH = 6"},
        "intent": "Increase model depth from 4 to 6",
        "hypothesis": "More layers should improve capacity and lower val_bpb",
    },
    {
        "name": "higher matrix_lr (0.06)",
        "changes": {"MATRIX_LR = 0.04": "MATRIX_LR = 0.06"},
        "intent": "Increase matrix learning rate from 0.04 to 0.06",
        "hypothesis": "Faster learning may converge to better loss in limited time",
    },
    {
        "name": "lower matrix_lr (0.02)",
        "changes": {"MATRIX_LR = 0.04": "MATRIX_LR = 0.02"},
        "intent": "Decrease matrix learning rate from 0.04 to 0.02",
        "hypothesis": "More conservative LR might avoid overshooting and yield smoother convergence",
    },
    {
        "name": "larger batch (2**17)",
        "changes": {"TOTAL_BATCH_SIZE = 2**16": "TOTAL_BATCH_SIZE = 2**17"},
        "intent": "Double the total batch size from 64K to 128K tokens",
        "hypothesis": "Larger batches give more stable gradients, possibly better final loss",
    },
    {
        "name": "warmup 10%",
        "changes": {"WARMUP_RATIO = 0.0": "WARMUP_RATIO = 0.1"},
        "intent": "Add 10% warmup ratio",
        "hypothesis": "Gradual LR warmup prevents early instability and may improve final loss",
    },
    {
        "name": "depth=6 + higher LR",
        "changes": {"DEPTH = 4": "DEPTH = 6", "MATRIX_LR = 0.04": "MATRIX_LR = 0.05"},
        "intent": "Combine depth=6 with slightly higher matrix_lr=0.05",
        "hypothesis": "Deeper model with tuned LR could compound improvements from experiments 2 and 3",
    },
    {
        "name": "window SSLL",
        "changes": {"WINDOW_PATTERN = \"SSSL\"": "WINDOW_PATTERN = \"SSLL\""},
        "intent": "Change window pattern from SSSL to SSLL (more full attention layers)",
        "hypothesis": "More full-context attention layers may help capture longer dependencies",
    },
    {
        "name": "lower weight decay (0.1)",
        "changes": {"WEIGHT_DECAY = 0.2": "WEIGHT_DECAY = 0.1"},
        "intent": "Reduce weight decay from 0.2 to 0.1",
        "hypothesis": "Less regularization may allow the model to fit better in short training runs",
    },
    {
        "name": "depth=6 + warmup + lower WD",
        "changes": {
            "DEPTH = 4": "DEPTH = 6",
            "WARMUP_RATIO = 0.0": "WARMUP_RATIO = 0.1",
            "WEIGHT_DECAY = 0.2": "WEIGHT_DECAY = 0.1",
        },
        "intent": "Combine depth=6, warmup=0.1, weight_decay=0.1",
        "hypothesis": "Best combination of individual improvements found so far",
    },
]


def apply_changes(changes: dict) -> str:
    """Apply hyperparameter changes to train.py, return modified content."""
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
    parent_id = None
    best_bpb = None
    results = []

    for i, exp in enumerate(EXPERIMENTS, 1):
        print(f"\n{'='*60}")
        print(f"EXPERIMENT {i}/10: {exp['name']}")
        print(f"{'='*60}")

        # Apply changes to train.py
        modified = apply_changes(exp["changes"])
        TRAIN_PY.write_text(modified)

        # Write agent note
        note = {
            "type": "agent_note",
            "run_id": parent_id or "pending",
            "intent": exp["intent"],
            "hypothesis": exp["hypothesis"],
        }
        with open(REASONING, "a") as f:
            f.write(json.dumps(note) + "\n")

        # Run experiment
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

            # Write accept/reject decision
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
            results.append((i, exp["name"], None, "FAILED"))

    # Restore original train.py
    TRAIN_PY.write_text(ORIG_CONTENT)

    # Print summary
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    for num, name, bpb, status in results:
        bpb_str = f"{bpb:.6f}" if bpb else "N/A"
        print(f"  {num:2d}. {name:35s} {bpb_str}  {status}")
    print(f"\nBest val_bpb: {best_bpb:.6f}")


if __name__ == "__main__":
    main()
