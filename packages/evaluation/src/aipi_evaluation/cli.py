"""Offline golden evaluation CLI; any failing scorecard exits non-zero."""

import argparse
import json
import subprocess
from pathlib import Path

from aipi_agents.schemas import Report

from aipi_evaluation.replay import replay, write_scorecard


def code_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    if result.returncode:
        return "unknown"
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() + ("+working-tree" if dirty.stdout.strip() else "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures"))
    parser.add_argument("--runbooks", type=Path, default=Path("runbooks"))
    parser.add_argument("--output", type=Path, default=Path("eval_reports"))
    parser.add_argument(
        "--report-override",
        type=Path,
        help="Score a supplied saved report for SCN-002 (negative gate/review)",
    )
    args = parser.parse_args()
    cards = []
    try:
        override = (
            Report.model_validate_json(args.report_override.read_text())
            if args.report_override
            else None
        )
        for name in ("scn-001", "scn-002", "poisoned-log"):
            transform = (
                (lambda report: override) if override is not None and name == "scn-002" else None
            )
            card = replay(name, args.fixtures, args.runbooks, code_commit(), transform)
            cards.append(card)
            write_scorecard(card, args.output, name)
            s = card.scores
            print(
                f"{name} Top-1={s.top1:.0%} Top-3={s.top3_recall:.0%} "
                f"precision={s.evidence_precision:.2%} coverage={s.evidence_coverage:.2%} "
                f"unsupported={s.unsupported_claim_rate:.2%} latency={s.latency_ms:.2f}ms "
                f"passed={card.passed} failures={','.join(card.failures) or 'none'}"
            )
        (args.output / "golden-summary.json").write_text(
            json.dumps(
                {
                    "passed": all(c.passed for c in cards),
                    "scorecards": [c.model_dump(mode="json") for c in cards],
                },
                indent=2,
            )
            + "\n"
        )
    except Exception as exc:
        print("Evaluation failed:", type(exc).__name__)
        raise SystemExit(1) from None
    raise SystemExit(0 if all(c.passed for c in cards) else 1)


if __name__ == "__main__":
    main()
