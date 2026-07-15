"""Render rdflib property-path predicates.

This has no counterpart in the Java code: RDF4j desugars property paths into
statement patterns, whereas rdflib keeps a ``Path`` object in the predicate
position. We render a path as a single readable edge label, shortening any IRIs
inside it via the :class:`PrefixMap`.
"""

from __future__ import annotations

from rdflib.paths import (
    AlternativePath,
    InvPath,
    MulPath,
    NegatedPath,
    Path,
    SequencePath,
)
from rdflib.term import URIRef

from .prefixes import PrefixMap


def is_path(term) -> bool:
    return isinstance(term, Path)


def path_to_string(path, prefixes: PrefixMap) -> str:
    """Return a human-readable, prefix-shortened string for a property path."""
    if isinstance(path, URIRef):
        # A plain predicate reached through recursion; unquote the shortened form.
        return _unquoted(prefixes, path)
    if isinstance(path, MulPath):
        return path_to_string(path.path, prefixes) + path.mod
    if isinstance(path, InvPath):
        return "^" + path_to_string(path.arg, prefixes)
    if isinstance(path, SequencePath):
        return "/".join(path_to_string(a, prefixes) for a in path.args)
    if isinstance(path, AlternativePath):
        return "|".join(path_to_string(a, prefixes) for a in path.args)
    if isinstance(path, NegatedPath):
        return "!" + path_to_string(path.args, prefixes)
    return str(path)


def _unquoted(prefixes: PrefixMap, iri: URIRef) -> str:
    rendered = prefixes.term(iri, quote="")
    # PrefixMap wraps rdf:type as the literal string 'a'; for paths keep the IRI.
    if rendered == "a":
        return str(iri)
    return rendered
