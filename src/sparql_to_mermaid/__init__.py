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
    collapse_empty_unions: bool = False,
) -> str:
    """Return a Mermaid diagram for ``query``.

    ``prefixes`` (prefix-name -> namespace-IRI) supplements the ``PREFIX``
    declarations in the query itself when shortening IRIs. ``base`` is accepted
    for parity with the Java API; rdflib resolves relative IRIs against it during
    parsing when present in the query. ``well_known`` (default ``True``) also
    shortens common life-science / semantic-web IRIs the query didn't declare
    (e.g. ``MONDO:``, ``CHEBI:``, ``biolink:``); pass ``False`` to shorten only
    against the query's own prefixes.

    ``collapse_empty_unions`` (default ``False``, off for parity with the Java
    tool) is a cosmetic pass: when both arms of a ``UNION`` reference the same
    nodes, Mermaid renders one arm as an empty box; enabling this unwraps that
    empty arm and drops the dangling ``or`` connector.

    Raises :class:`SparqlToMermaidError` if the query cannot be parsed/rendered.
    """
    algebra = parse(query)
    prefix_map = PrefixMap.from_query(query, prefixes, well_known)
    scope = Scope()
    Namer(scope).collect(algebra)

    lines = ["graph TD"]
    renderer = Renderer(scope, prefix_map, lines)
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
) -> str | None:
    """Like :func:`to_mermaid` but returns ``None`` (and logs) on failure.

    Mirrors the Java behaviour of skipping queries that cannot be transformed.
    """
    try:
        return to_mermaid(query, prefixes, base, well_known)
    except SparqlToMermaidError as exc:
        _log.info("Query can not be transformed to mermaid: %s", exc)
        return None
