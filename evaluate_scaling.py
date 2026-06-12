from __future__ import annotations

import argparse
from pathlib import Path

from evaluate_common import scaling_criteria, write_outputs


def main() -> None:
    """Evaluate scaling results for a selected run group."""

    parser = argparse.ArgumentParser(description="Evaluate scaling criteria for all runs in a run_group_id.")
    parser.add_argument("--summary", default="results/runs.tsv")
    parser.add_argument("--run-group-id", required=True)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-tsv", default=None)
    args = parser.parse_args()

    summary_path = Path(args.summary)
    base = summary_path.parent / f"evaluate-scaling-{args.run_group_id}"
    output_json = Path(args.output_json) if args.output_json else base.with_suffix(".json")
    output_tsv = Path(args.output_tsv) if args.output_tsv else base.with_suffix(".tsv")

    document = scaling_criteria(summary_path, args.run_group_id)
    write_outputs(document, output_json, output_tsv)

    print(f"Evaluation JSON: {output_json}")
    print(f"Evaluation TSV:  {output_tsv}")


if __name__ == "__main__":
    main()
