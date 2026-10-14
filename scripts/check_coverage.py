"""Enforce independent line and branch coverage thresholds from coverage.py XML."""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def percentage(value):
    """Validate a percentage supplied on the command line."""
    number = float(value)
    if not 0 <= number <= 100:
        raise argparse.ArgumentTypeError("threshold must be between 0 and 100")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="coverage.py XML report (coverage.xml)")
    parser.add_argument("--line-threshold", type=percentage, default=70, metavar="PERCENT")
    parser.add_argument("--branch-threshold", type=percentage, default=60, metavar="PERCENT")
    args = parser.parse_args(argv)
    try:
        root = ET.parse(args.report).getroot()
        if root.tag != "coverage":
            raise ValueError("expected a coverage XML report")
        line_rate = float(root.attrib["line-rate"])
        branch_rate = float(root.attrib["branch-rate"])
        if not (0 <= line_rate <= 1 and 0 <= branch_rate <= 1):
            raise ValueError("coverage rates must be between 0 and 1")
    except (OSError, ET.ParseError, KeyError, ValueError) as exc:
        print(f"Cannot read coverage report: {exc}", file=sys.stderr)
        return 2

    # coverage.py reports branch-rate=1 when there are no executable branches.
    print(f"Line coverage: {line_rate:.2%} (required: {args.line_threshold:.2f}%)")
    print(f"Branch coverage: {branch_rate:.2%} (required: {args.branch_threshold:.2f}%)")
    passed = line_rate >= args.line_threshold / 100 and branch_rate >= args.branch_threshold / 100
    print(f"Coverage gate {'PASSED' if passed else 'FAILED'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
