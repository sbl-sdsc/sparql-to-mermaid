"""Turn an rdflib value-expression into a readable string.

Ports the inner ``ValueExprAsString`` visitor from Java. Because rdflib's
expression algebra differs substantially from RDF4j's, the common node types are
handled explicitly and anything unrecognised falls back to a generic
``name(args...)`` rendering.
"""

from __future__ import annotations

from rdflib.term import BNode, Literal, URIRef, Variable

from .algebra import name_of
from .prefixes import PrefixMap

_XPATH_FN = "http://www.w3.org/2005/xpath-functions#"

_REL_OPS = {
    "=": " = ",
    "!=": " != ",
    "<": " < ",
    ">": " > ",
    "<=": " <= ",
    ">=": " >= ",
    "IN": " in ",
    "NOT IN": " not in ",
}

_IS_FUNCS = {
    "Builtin_isIRI": "isIRI",
    "Builtin_isURI": "isIRI",
    "Builtin_isBLANK": "isBlank",
    "Builtin_isLITERAL": "isLiteral",
    "Builtin_isNUMERIC": "isNumeric",
}

_AGGREGATES = {
    "Aggregate_Count": "count",
    "Aggregate_Sum": "sum",
    "Aggregate_Avg": "average",
    "Aggregate_Min": "min",
    "Aggregate_Max": "max",
    "Aggregate_Sample": "sample",
    "Aggregate_GroupConcat": "group_concat",
}


def expr_to_string(expr, prefixes: PrefixMap) -> str:
    return _E(prefixes).render(expr)


def collect_vars(expr):
    """Ordered, de-duplicated list of Variables referenced by an expression."""
    found: list = []
    seen: set = set()

    def walk(node):
        if isinstance(node, Variable):
            if str(node) not in seen and not str(node).startswith("__"):
                seen.add(str(node))
                found.append(node)
        elif isinstance(node, (URIRef, Literal, BNode)):
            return
        elif name_of(node) in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
            # EXISTS bodies get their own rendering scope; their variables are
            # not nodes in the enclosing graph.
            return
        elif name_of(node) is not None:
            for key, value in node.items():
                if key != "_vars":
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(expr)
    return found


class _E:
    def __init__(self, prefixes: PrefixMap):
        self.p = prefixes

    def render(self, e) -> str:
        if isinstance(e, Variable):
            return "?" + str(e) if not str(e).startswith("__") else "?" + str(e)
        if isinstance(e, BNode):
            return " [] "
        if isinstance(e, (URIRef, Literal)):
            return self.p.term(e, quote="'")
        name = name_of(e)
        if name is None:
            return str(e)
        handler = getattr(self, f"_{name}", None)
        if handler is not None:
            return handler(e)
        if name in _IS_FUNCS:
            return f"{_IS_FUNCS[name]}({self.render(e.arg)})"
        if name in _AGGREGATES:
            return self._aggregate(e, _AGGREGATES[name])
        if name.startswith("Builtin_"):
            return self._generic(name[len("Builtin_"):].lower(), e)
        return self._generic(name, e)

    # -- boolean / comparison ------------------------------------------ #
    def _RelationalExpression(self, e) -> str:
        left = self.render(e.expr)
        op = _REL_OPS.get(e.op, f" {e.op} ")
        if e.op in ("IN", "NOT IN"):
            members = ", ".join(self.render(m) for m in (e.other or []))
            return f"{left}{op}({members})"
        return f"{left}{op}{self.render(e.other)}"

    def _ConditionalAndExpression(self, e) -> str:
        parts = [self.render(e.expr)] + [self.render(o) for o in e.other]
        return " && ".join(parts)

    def _ConditionalOrExpression(self, e) -> str:
        parts = [self.render(e.expr)] + [self.render(o) for o in e.other]
        return "(" + " || ".join(parts) + ")"

    def _UnaryNot(self, e) -> str:
        return "not " + self.render(e.expr)

    def _UnaryMinus(self, e) -> str:
        return "-" + self.render(e.expr)

    def _UnaryPlus(self, e) -> str:
        return "+" + self.render(e.expr)

    # -- arithmetic ----------------------------------------------------- #
    def _additive(self, e) -> str:
        out = self.render(e.expr)
        for op, other in zip(e.op, e.other):
            out += f" {op} {self.render(other)}"
        return out

    _AdditiveExpression = _additive
    _MultiplicativeExpression = _additive

    # -- builtins ------------------------------------------------------- #
    def _Builtin_STR(self, e) -> str:
        return f"str({self.render(e.arg)})"

    def _Builtin_BOUND(self, e) -> str:
        return f"bound({self.render(e.arg)})"

    def _Builtin_LANGMATCHES(self, e) -> str:
        return f"langmatch({self.render(e.arg1)},{self.render(e.arg2)})"

    def _Builtin_SAMETERM(self, e) -> str:
        return f"sameterm({self.render(e.arg1)},{self.render(e.arg2)})"

    def _Builtin_REGEX(self, e) -> str:
        out = f"regex({self.render(e.text)},{self.render(e.pattern)}"
        # NB: rdflib's CompValue.get returns the key *name* for absent keys, so
        # test membership, not `is not None`.
        if "flags" in e and e["flags"] is not None:
            out += f",{self.render(e['flags'])}"
        return out + ")"

    def _Builtin_IF(self, e) -> str:
        return (
            f"if({self.render(e.arg1)},{self.render(e.arg2)},{self.render(e.arg3)})"
        )

    def _Builtin_EXISTS(self, e) -> str:
        return " "

    def _Builtin_NOTEXISTS(self, e) -> str:
        return " "

    # -- functions & aggregates ---------------------------------------- #
    def _Function(self, e) -> str:
        iri = str(e.iri)
        if iri.startswith(_XPATH_FN):
            name = iri[len(_XPATH_FN):]
        else:
            # e.g. an xsd:double(...) cast -> shorten via the query's prefixes
            name = self.p.shorten(iri)
        args = ",".join(self.render(a) for a in (e.expr or []))
        return f"{name}({args})"

    def _aggregate(self, e, fn) -> str:
        if fn == "count" and "vars" not in e:
            return "count(*)"
        return f"{fn}({self.render(e['vars'])})"

    def _generic(self, fn: str, e) -> str:
        args = []
        for key, value in e.items():
            if key in ("_vars", "distinct"):
                continue
            args.append(self.render(value))
        return f"{fn}({','.join(args)})"
