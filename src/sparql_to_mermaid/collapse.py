"""Cosmetic post-process: drop UNION arm wrappers Mermaid would render empty.

When the two arms of a ``UNION`` reference the *same* nodes -- e.g. a disease
related to a gene in both directions, ``{ A :p ?x } UNION { ?x :p A }`` -- Mermaid
cannot place a node in two subgraphs at once. It assigns each shared node to the
*deepest, last* subgraph that references it, so the shared nodes land in the
second arm and the first arm renders as an empty box tethered by the ``or``
connector.

:func:`collapse_empty_union_arms` walks the emitted lines, works out which
subgraph ends up *owning* each node (deepest wins; ties break to the later line),
and unwraps any UNION arm that owns nothing -- keeping the arm's edges and
dropping the now-dangling ``or`` connector. Everything else is left byte-for-byte
untouched, so it stays a purely visual clean-up.
"""

from __future__ import annotations

import re

# A node declaration is an id immediately followed by a shape opener, e.g.
# ``v1("?gene")``, ``graph0c1(["MONDO:0005258"])``, ``f0[["..."]]``. ``style``,
# ``classDef`` and ``subgraph`` lines put a space (or nothing) before any bracket
# and so never match.
_NODE_DECL = re.compile(r"^([A-Za-z0-9_]+)[(\[]")
_TOKEN = re.compile(r"[A-Za-z0-9_]+")
_CONNECTOR = re.compile(r"^(\S+)\s*<==\s*or\s*==>\s*(\S+)\s*$")


class _Frame:
    __slots__ = ("id", "depth", "start", "end", "owned")

    def __init__(self, sid: str, depth: int, start: int):
        self.id = sid
        self.depth = depth
        self.start = start  # index of the ``subgraph`` header line
        self.end = -1  # index of the matching ``end`` line
        self.owned = 0  # number of nodes this frame ends up owning


def collapse_empty_union_arms(lines: list[str]) -> list[str]:
    """Return ``lines`` with empty UNION arm wrappers removed."""
    frames: list[_Frame] = []
    stack: list[_Frame] = []
    innermost: list[_Frame | None] = [None] * len(lines)
    node_ids: set[str] = set()

    # Pass 1 -- parse subgraph nesting and collect declared node ids.
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("subgraph "):
            sid = s[len("subgraph ") :].split("[", 1)[0].strip()
            frame = _Frame(sid, len(stack), i)
            frames.append(frame)
            stack.append(frame)
            continue
        if s == "end":
            if stack:
                stack.pop().end = i
            continue
        innermost[i] = stack[-1] if stack else None
        m = _NODE_DECL.match(s)
        if m:
            node_ids.add(m.group(1))

    if not node_ids:
        return lines

    # Pass 2 -- assign each node to the deepest, last subgraph referencing it.
    owner: dict[str, tuple[int, int, _Frame | None]] = {}
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("subgraph ") or s == "end" or s.startswith("style "):
            continue
        frame = innermost[i]
        depth = frame.depth + 1 if frame else 0
        for tok in _TOKEN.findall(s):
            if tok not in node_ids:
                continue
            key = (depth, i, frame)
            best = owner.get(tok)
            if best is None or (depth, i) > (best[0], best[1]):
                owner[tok] = key
    for _tok, (_d, _i, frame) in owner.items():
        if frame is not None:
            frame.owned += 1

    # Pass 3 -- decide which arm wrappers to unwrap from the ``or`` connectors.
    by_id = {f.id: f for f in frames}
    drop_lines: set[int] = set()
    for i, line in enumerate(lines):
        m = _CONNECTOR.match(line.strip())
        if not m:
            continue
        arms = [by_id.get(m.group(1)), by_id.get(m.group(2))]
        empty = [f for f in arms if f is not None and f.owned == 0]
        if not empty:
            continue
        drop_lines.add(i)  # the connector is now dangling
        for f in empty:
            drop_lines.add(f.start)
            drop_lines.add(f.end)
            for j in range(f.start + 1, f.end):
                if lines[j].strip().startswith(f"style {f.id} "):
                    drop_lines.add(j)

    if not drop_lines:
        return lines
    return [line for i, line in enumerate(lines) if i not in drop_lines]
