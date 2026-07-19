"""Render a SPARQL query as a Mermaid ``graph TD`` diagram.

Python port of the ``mermaid`` package in the Java project
``sparql-examples-utils``. The primary entry point is :func:`to_mermaid`, which
takes a raw SPARQL query string.
"""

from __future__ import annotations

import logging

from .algebra import parse
from .collapse import collapse_empty_union_arms
from .errors import SparqlToMermaidError
from .naming import Namer, Scope
from .prefixes import PrefixMap
from .render import Renderer

__all__ = ["to_mermaid", "try_to_mermaid", "SparqlToMermaidError"]

_log = logging.getLogger(__name__)


def to_mermaid(
    query: str,
    prefixes: dict[str, str] | None = None,
    base: str = "https://example.org/",
    well_known: bool = True,
    collapse_empty_unions: bool = True,
    max_values: int | None = 3,
    portable: bool = False,
) -> str:
    """Return a Mermaid diagram for ``query``.

    ``prefixes`` (prefix-name -> namespace-IRI) supplements the ``PREFIX``
    declarations in the query itself when shortening IRIs. ``base`` is accepted
    for parity with the Java API; rdflib resolves relative IRIs against it during
    parsing when present in the query. ``well_known`` (default ``True``) also
    shortens common life-science / semantic-web IRIs the query didn't declare
    (e.g. ``MONDO:``, ``CHEBI:``, ``biolink:``); pass ``False`` to shorten only
    against the query's own prefixes.

    ``collapse_empty_unions`` (default ``True``) is a cosmetic pass: when both
    arms of a ``UNION`` reference the same nodes, Mermaid renders one arm as an
    empty box, so this unwraps that empty arm (keeping its edges) and drops the
    dangling ``or`` connector. Pass ``False`` for output identical to the Java
    tool, which leaves the empty box in place.

    ``max_values`` (default ``3``) caps how many values a ``VALUES`` clause draws:
    once a list has more than that, the first ``max_values`` are shown as nodes and
    the tail collapses into a single ``+N more`` node, so a long inline list doesn't
    fan out to one node per value. Pass ``None`` to draw every value (previous
    behaviour). Lists of ``max_values`` or fewer are unaffected.

    ``portable`` (default ``False``) trades a little fidelity for maximum renderer
    compatibility: IRIs with no known prefix are compacted to a synthetic CURIE
    (``reactome:R-HSA-163210``) instead of appearing as a raw ``https://...`` in a
    label, and the aggregate ``--as--o`` edge is emitted in the conventional
    ``--o|as|`` pipe-label form. Use it when a stricter or older Mermaid engine
    rejects the default output.

    Raises :class:`SparqlToMermaidError` if the query cannot be parsed/rendered.
    """
    algebra = parse(query)
    prefix_map = PrefixMap.from_query(
        query, prefixes, well_known, compact_unknown=portable
    )
    scope = Scope()
    Namer(scope).collect(algebra)

    lines = ["graph TD"]
    renderer = Renderer(scope, prefix_map, lines, max_values=max_values, portable=portable)
    renderer.prescan_aggregates(algebra)
    renderer.add_styles()
    renderer.render_variables()
    renderer.visit(algebra)
    if collapse_empty_unions:
        lines = collapse_empty_union_arms(lines)
    return "\n".join(lines)


def try_to_mermaid(
    query: str,
    prefixes: dict[str, str] | None = None,
    base: str = "https://example.org/",
    well_known: bool = True,
    max_values: int | None = 3,
    portable: bool = False,
) -> str | None:
    """Like :func:`to_mermaid` but returns ``None`` (and logs) on failure.

    Mirrors the Java behaviour of skipping queries that cannot be transformed.
    """
    try:
        return to_mermaid(
            query, prefixes, base, well_known,
            max_values=max_values, portable=portable,
        )
    except SparqlToMermaidError as exc:
        _log.info("Query can not be transformed to mermaid: %s", exc)
        return None
