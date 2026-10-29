"""Command-line entry point. `ask` arrives in Phase 4 (the eval harness is `python -m eval.run_eval`)."""

import argparse
import sys

_NOT_YET = {"ask": "Phase 4 (agent core)"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sql-analyst")
    parser.add_argument("command", choices=sorted(_NOT_YET))
    args, _rest = parser.parse_known_args(argv)
    print(f"'{args.command}' is not implemented yet: it is built in {_NOT_YET[args.command]}.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
