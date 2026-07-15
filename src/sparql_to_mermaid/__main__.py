"""Command-line entry point: read a SPARQL query, print a Mermaid diagram."""

from __future__ import annotations

import argparse
import sys

from . import to_mermaid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sparql-to-mermaid",
        description="Render a SPARQL query as a Mermaid graph diagram.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="SPARQL query file (reads stdin if omitted)",
    )
    parser.add_argument(
        "--fence",
        action="store_true",
        help="wrap the output in a ```mermaid code fence",
    )
    args = parser.parse_args(argv)

    query = sys.stdin.read() if args.file is None else _read(args.file)
    diagram = to_mermaid(query)
    if args.fence:
        print("```mermaid")
        print(diagram)
        print("```")
    else:
        print(diagram)
    return 0


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


if __name__ == "__main__":
    raise SystemExit(main())
