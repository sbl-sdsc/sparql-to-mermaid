"""IRI shortening, escaping, and literal formatting.

Ports the ``prefix(...)``, ``escape(...)`` and literal-datatype logic from the
Java ``Render`` class.
"""

from __future__ import annotations

import re

from rdflib.namespace import RDF, XSD
from rdflib.term import BNode, Literal, URIRef, Variable

from .well_known import WELL_KNOWN_PREFIXES

_PREFIX_DECL = re.compile(r"(?im)^\s*PREFIX\s+([^:\s]*)\s*:\s*<([^>]*)>")

# Datatype namespace -> the prefix used in the ``^^`` suffix, mirroring the Java
# CoreDatatype handling (xsd:, rdf:, geo:).
_GEO = "http://www.opengis.net/ont/geosparql#"


class PrefixMap:
    """Namespace-IRI -> ``prefix:`` lookup used to shorten IRIs.

    Two tiers: the query's own ``PREFIX`` declarations plus any caller-supplied
    prefixes are consulted first; a curated set of well-known life-science /
    semantic-web prefixes fills gaps for IRIs the query didn't declare. Within
    each tier the *longest* matching namespace wins, so an OBO id shortens to its
    conventional CURIE (``MONDO:0005148``).
    """

    def __init__(
        self,
        namespaces: dict[str, str],
        fallback: dict[str, str] | None = None,
        compact_unknown: bool = False,
    ):
        self._items = self._sorted(namespaces)
        self._fallback = self._sorted(fallback or {})
        # In "portable" mode, an IRI that matches no known prefix is shortened to
        # a synthetic ``segment:local`` CURIE instead of being emitted in full, so
        # a raw ``https://...`` never lands inside a Mermaid label (stricter/older
        # renderers can choke on the ``://`` and length).
        self._compact_unknown = compact_unknown

    @staticmethod
    def _sorted(namespaces: dict[str, str]) -> list[tuple[str, str]]:
        # list of (namespace, "prefix:") sorted longest-namespace-first.
        items = [(ns, f"{name}:") for name, ns in namespaces.items()]
        items.sort(key=lambda kv: (-len(kv[0]), kv[0]))
        return items

    @classmethod
    def from_query(
        cls,
        query: str,
        extra: dict[str, str] | None = None,
        well_known: bool = True,
        compact_unknown: bool = False,
    ) -> "PrefixMap":
        namespaces: dict[str, str] = {}
        if extra:
            namespaces.update(extra)
        for name, ns in _PREFIX_DECL.findall(query):
            namespaces[name] = ns
        fallback = dict(WELL_KNOWN_PREFIXES) if well_known else None
        return cls(namespaces, fallback, compact_unknown=compact_unknown)

    def _shorten_iri(self, iri: str) -> str | None:
        for items in (self._items, self._fallback):
            for ns, prefix in items:
                if iri.startswith(ns):
                    return prefix + iri[len(ns) :]
        return None

    def shorten(self, iri: str) -> str:
        """Return ``prefix:local`` if a namespace matches, else the full IRI.

        Unquoted form, for contexts like function/cast names in an expression.
        In portable mode an unmatched IRI is compacted to a synthetic CURIE
        rather than returned in full.
        """
        short = self._shorten_iri(str(iri))
        if short is not None:
            return short
        return self._compact_iri(str(iri)) if self._compact_unknown else str(iri)

    @staticmethod
    def _compact_iri(iri: str) -> str:
        """Best-effort short label for an IRI with no known prefix.

        Uses the final path/fragment segment as the local name and the segment
        before it as a lightweight pseudo-prefix for context, so
        ``https://identifiers.org/reactome/R-HSA-163210`` becomes
        ``reactome:R-HSA-163210`` and ``https://purl.org/okn/frink/kg/prokn``
        becomes ``kg:prokn``. Falls back to the full IRI if it has no usable
        segment.
        """
        s = str(iri).rstrip("/#")
        if "#" in s:
            head, local = s.rsplit("#", 1)
        else:
            head, _, local = s.rpartition("/")
        if not local:
            return str(iri)
        prev = head.rpartition("/")[2] if head else ""
        # Skip a scheme/host-looking segment (``https:``, ``purl.org``) as prefix.
        if prev and ":" not in prev and "." not in prev:
            return f"{prev}:{local}"
        return local

    def term(self, value, quote: str = '"') -> str:
        """Render a term (IRI/Literal/BNode) shortened and quoted like Java."""
        if value is None:
            return "ERROR: Bad value"
        if isinstance(value, URIRef):
            return self._iri(value, quote)
        if isinstance(value, Literal):
            return self._literal(value, quote)
        return str(value)

    def _iri(self, iri: URIRef, quote: str) -> str:
        if iri == RDF.type:
            return '"a"'
        short = self._shorten_iri(str(iri))
        if short is not None:
            return quote + short + quote
        # An IRI with no matching prefix is emitted in full (or, in portable mode,
        # compacted to a synthetic CURIE so no raw URL lands in a label) -- still
        # quote it so a stray '(' or other special character can't break Mermaid.
        text = self._compact_iri(str(iri)) if self._compact_unknown else str(iri)
        return quote + escape(text) + quote

    def _literal(self, lit: Literal, quote: str) -> str:
        dt = lit.datatype
        if dt is None or dt == XSD.string:
            return quote + escape(str(lit)) + quote
        dt_str = str(dt)
        local = _local_name(dt_str)
        if dt_str.startswith(str(XSD)):
            return f"{quote}{lit}^^xsd:{local}{quote}"
        if dt_str.startswith(str(RDF)):
            return f"{quote}{lit}^^rdf:{local}{quote}"
        if dt_str.startswith(_GEO):
            return f"{quote}{lit}^^geo:{local}{quote}"
        return f"{quote}{escape(str(lit))}^^<{dt}>{quote}"


def _local_name(iri: str) -> str:
    for sep in ("#", "/"):
        if sep in iri:
            return iri.rsplit(sep, 1)[1]
    return iri


def escape(text: str) -> str:
    """Replace ``[`` and ``]`` with their Mermaid HTML entities."""
    return text.replace("[", "#91;").replace("]", "#93;")


def classify(term):
    """Return ``"var"``, ``"anon"`` or ``"const"`` for a term.

    Mirrors ``Var.isAnonymous()/isConstant()``: named variables are ``var``,
    blank nodes are ``anon``, and IRIs/literals are ``const``.
    """
    if isinstance(term, Variable):
        return "var"
    if isinstance(term, BNode):
        return "anon"
    return "const"
