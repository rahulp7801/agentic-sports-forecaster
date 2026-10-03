"""Run an allowed local paper task from this checkout's source directory.

A copied virtualenv can retain an editable install pointing to another checkout.
Resolve and verify the local module before executing any collection code.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys


MODULES = ("sportsbet.quant.kalshi_stat_only_next_capture",
           "sportsbet.quant.kalshi_stat_only_next_publish",
           "sportsbet.quant.kalshi_stat_only_fixed_score",
           "sportsbet.quant.kalshi_stat_only_settlement_capture",
           "sportsbet.quant.kalshi_stat_only_next_recent_gap",
           "sportsbet.quant.kalshi_stat_only_context_price_audit",
           "sportsbet.quant.kalshi_stat_only_next_teammate_study",
           "sportsbet.quant.kalshi_role_weighting_study",
           "sportsbet.quant.kalshi_stat_only_prelock_paper_result",
           "sportsbet.quant.kalshi_stat_only_next_series_v2",
           "sportsbet.quant.kalshi_stat_only_next_recent_gap_eval_v2",
           "sportsbet.quant.kalshi_role_weighting_eval_v2",
           "sportsbet.quant.kalshi_stat_only_next_teammate_study_v2")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--module", required=True, choices=MODULES)
    parser.add_argument("--inspect-source", action="store_true")
    args, remaining = parser.parse_known_args()
    root = Path(__file__).resolve().parent.parent
    source = root / "src"
    expected = source.joinpath(*args.module.split(".")).with_suffix(".py")
    if expected.is_symlink() or not expected.is_file():
        parser.error("Local paper task source is missing or linked")
    sys.path.insert(0, str(source))
    spec = importlib.util.find_spec(args.module)
    if spec is None or spec.origin is None or Path(spec.origin).resolve() != expected.resolve():
        parser.error("Paper task resolved outside this checkout")
    if args.inspect_source:
        print(json.dumps({"module": args.module, "source": str(expected),
                          "source_sha256": hashlib.sha256(expected.read_bytes()).hexdigest()},
                         sort_keys=True))
        return
    sys.argv = [args.module, *remaining]
    runpy.run_module(args.module, run_name="__main__")


if __name__ == "__main__":
    main()
