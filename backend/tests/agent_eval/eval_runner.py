"""Agent evaluation runner.

Runs all eval cases against the current Agent implementation and reports:
  - tool_accuracy: % of cases where the correct tool was selected
  - arg_accuracy: % of cases where key args matched expected values

Usage:
  python -m tests.agent_eval.eval_runner
  python -m tests.agent_eval.eval_runner --verbose
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.agent.graph import run_agent_graph
from app.db.session import SessionLocal


def load_eval_cases() -> list[dict]:
    cases_path = Path(__file__).parent / "eval_cases.json"
    with open(cases_path, encoding="utf-8") as f:
        return json.load(f)


def evaluate_case(db, case: dict, verbose: bool = False) -> dict:
    """Run one eval case and compare result to expected."""
    result = {
        "id": case["id"],
        "input": case["input"],
        "expected_tool": case["expected_tool"],
        "actual_tool": "",
        "expected_args": case.get("expected_args", {}),
        "actual_args": {},
        "tool_correct": False,
        "args_correct": False,
    }

    try:
        response = run_agent_graph(db, case["input"], chat_id=f"eval-{case['id']}")
    except Exception as exc:
        result["actual_tool"] = f"ERROR: {exc}"
        if verbose:
            print(f"  ❌ Case {case['id']}: {exc}")
        return result

    # Extract the first tool call from steps
    if response.steps:
        first_step = response.steps[0]
        result["actual_tool"] = first_step.tool_name
        result["actual_args"] = first_step.tool_args
    else:
        result["actual_tool"] = response.intent_name or "no_tool"
        result["actual_args"] = response.intent_filters

    # Check tool correctness
    result["tool_correct"] = result["actual_tool"] == case["expected_tool"]

    # Check arg correctness (partial match — only check keys specified in expected)
    expected = case.get("expected_args", {})
    actual = result["actual_args"]
    if expected and actual:
        all_match = True
        for key, val in expected.items():
            actual_val = actual.get(key)
            # Handle type conversions (JSON parsing is string-based)
            if isinstance(val, bool):
                actual_val_bool = actual_val in (True, "true", "True", True)
                if actual_val_bool != val:
                    all_match = False
            elif str(actual_val) != str(val):
                all_match = False
        result["args_correct"] = all_match
    elif not expected:
        result["args_correct"] = True  # No specific args to check
    else:
        result["args_correct"] = False  # Expected args but got none

    if verbose:
        icon = "✅" if result["tool_correct"] else "❌"
        print(f"  {icon} Case {case['id']}: expected={case['expected_tool']} actual={result['actual_tool']}")
        if not result["args_correct"] and expected:
            print(f"       args: expected={expected} actual={actual}")

    return result


def run_evaluation(verbose: bool = False) -> dict[str, Any]:
    """Run all eval cases and return a summary report."""
    cases = load_eval_cases()
    db = SessionLocal()

    try:
        if verbose:
            print(f"\nRunning {len(cases)} eval cases...\n")

        results = [evaluate_case(db, case, verbose=verbose) for case in cases]

        # Calculate metrics
        total = len(results)
        tool_correct = len([r for r in results if r["tool_correct"]])
        args_correct = len([r for r in results if r["args_correct"]])

        # By category
        categories: dict[str, dict] = {}
        for case in cases:
            cat = case.get("category", "unknown")
            if cat not in categories:
                categories[cat] = {"total": 0, "tool_correct": 0}
            categories[cat]["total"] += 1

        for r in results:
            cat = next((c.get("category", "unknown") for c in cases if c["id"] == r["id"]), "unknown")
            if r["tool_correct"]:
                categories[cat]["tool_correct"] += 1

        # Build report
        report = {
            "total_cases": total,
            "tool_accuracy": round(tool_correct / total * 100, 1) if total else 0,
            "arg_accuracy": round(args_correct / total * 100, 1) if total else 0,
            "tool_correct": tool_correct,
            "args_correct": args_correct,
            "by_category": {
                cat: {
                    "total": data["total"],
                    "correct": data["tool_correct"],
                    "accuracy": round(data["tool_correct"] / data["total"] * 100, 1) if data["total"] else 0,
                }
                for cat, data in categories.items()
            },
            "failed_cases": [
                {"id": r["id"], "input": r["input"], "expected": r["expected_tool"], "actual": r["actual_tool"]}
                for r in results if not r["tool_correct"]
            ],
        }

        # Print summary
        print("\n" + "=" * 50)
        print("Agent Evaluation Report")
        print("=" * 50)
        print(f"Total cases:       {total}")
        print(f"Tool accuracy:     {report['tool_accuracy']}% ({tool_correct}/{total})")
        print(f"Arg accuracy:      {report['arg_accuracy']}% ({args_correct}/{total})")
        print()
        print("By category:")
        for cat, data in report["by_category"].items():
            bar = "█" * int(data["accuracy"] / 10) + "░" * (10 - int(data["accuracy"] / 10))
            print(f"  {cat:10s} {bar} {data['accuracy']}% ({data['correct']}/{data['total']})")

        if report["failed_cases"]:
            print(f"\nFailed cases ({len(report['failed_cases'])}):")
            for fc in report["failed_cases"]:
                print(f"  #{fc['id']}: '{fc['input']}' → expected {fc['expected']}, got {fc['actual']}")

        print("=" * 50)

        return report

    finally:
        db.close()


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    run_evaluation(verbose=verbose)
