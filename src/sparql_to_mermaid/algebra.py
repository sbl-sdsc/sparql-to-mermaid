"""Parse SPARQL into rdflib's query algebra and expose helpers."""

from __future__ import annotations

from rdflib.plugins.sparql import algebra as _alg
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.parserutils import CompValue

from .errors import SparqlToMermaidError


def parse(query: str):
    """Parse a SPARQL query string and return its translated algebra tree.

    Returns the top algebra node (e.g. ``SelectQuery``). Raises
    :class:`SparqlToMermaidError` on any parse/translate failure, mirroring the
    Java behaviour of skipping queries it cannot handle.
    """
    try:
        return _alg.translateQuery(parseQuery(query)).algebra
    except Exception as exc:  # noqa: BLE001 - rdflib raises many exception types
        raise SparqlToMermaidError(str(exc)) from exc


def expand_group_graph_pattern(ggp):
    """Translate a raw ``GroupGraphPatternSub`` into proper algebra.

    rdflib leaves the graph of ``SERVICE`` and ``EXISTS`` untranslated in the
    main tree; this turns it into the same algebra shape as the rest.
    """
    try:
        return _alg.translateGroupGraphPattern(ggp)
    except Exception:  # noqa: BLE001
        return ggp


def name_of(node) -> str | None:
    """Return the algebra node name (``CompValue.name``) or ``None``."""
    if isinstance(node, CompValue):
        return node.name
    return None
