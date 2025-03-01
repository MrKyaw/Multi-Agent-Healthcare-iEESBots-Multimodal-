"""Command-line interface for the iEESBots governance core.

Examples::

    python -m ieesbots --demo
    python -m ieesbots --demo --json
    python -m ieesbots --case synthetic_case.json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .casefile import demo_case, load_case
from .exceptions import CaseValidationError
from .models import RunResult, RunStatus
from .orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="ieesbots",
        description=(
            "Run a synthetic, offline multi-agent care-navigation case through "
            "consent, safety-policy, PHI-redaction, and hash-chained audit "
            "controls. Research prototype; not a medical device."
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--demo",
        action="store_true",
        help="run the built-in fictional high-acuity demo case",
    )
    source.add_argument(
        "--case",
        metavar="FILE",
        help="path to a synthetic case JSON file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the full structured run result as JSON",
    )
    return parser


def render_result(result: RunResult) -> str:
    """Render a compact human-readable run report."""

    counts = ", ".join(
        f"{kind}={count}" for kind, count in sorted(result.redaction.counts.items())
    )
    lines = [
        f"iEESBots synthetic run — {result.case_id}",
        f"Status: {result.status.value}",
        f"Human review required: {result.requires_human}",
        f"Policy verdict: {result.policy.verdict.value}",
        f"PHI tokens: {result.redaction.total}"
        + (f" ({counts})" if counts else ""),
        "Routing:",
    ]
    lines.extend(
        f"  - {decision.role.label} (priority {decision.priority})"
        for decision in result.plan.decisions
    )
    lines.extend(
        [
            "",
            result.summary.render(),
            f"Audit entries: {len(result.ledger)}",
            (
                "Audit chain: intact"
                if result.audit.valid
                else f"Audit chain: BROKEN at {result.audit.broken_index}"
            ),
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.demo and args.case is None:
        parser.print_help()
        return 0

    if args.demo:
        case = demo_case()
    else:
        try:
            case = load_case(args.case)
        except CaseValidationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    result = Orchestrator().run(case)
    if args.as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_result(result))

    if result.status in (RunStatus.COMPLETED, RunStatus.AWAITING_HUMAN_REVIEW):
        return 0
    return 1
