"""Assign Mermaid node ids to variables/blank-nodes/constants.

Ports ``NameVariablesAndConstants`` (id assignment) and
``FindWhichConstantsAreNotOnlyUsedAsPredicates`` (deciding which constants are
drawn as nodes) from the Java implementation.
"""

from __future__ import annotations

from rdflib.term import Literal, URIRef, Variable

from .algebra import expand_group_graph_pattern, name_of
from .paths import is_path
from .prefixes import classify


class Scope:
    """Holds the id maps for one rendering scope (top query or one EXISTS)."""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.var_ids: dict[str, str] = {}
        self.bnode_ids: dict[str, str] = {}
        self.const_ids: dict = {}
        self.used_as_node: set = set()
        self.projected: set[str] = set()

    # -- id assignment (mirrors the "v/a/c<N>" scheme, per-scope prefixed) --
    def var_id(self, name: str) -> str:
        key = str(name)
        if key not in self.var_ids:
            self.var_ids[key] = f"{self.prefix}v{len(self.var_ids) + 1}"
        return self.var_ids[key]

    def bnode_id(self, bnode) -> str:
        key = str(bnode)
        if key not in self.bnode_ids:
            self.bnode_ids[key] = f"{self.prefix}a{len(self.bnode_ids) + 1}"
        return self.bnode_ids[key]

    def const_id(self, term) -> str:
        if term not in self.const_ids:
            self.const_ids[term] = f"{self.prefix}c{len(self.const_ids) + 1}"
        return self.const_ids[term]

    def id_of(self, term) -> str:
        kind = classify(term)
        if kind == "var":
            return self.var_id(term)
        if kind == "anon":
            return self.bnode_id(term)
        return self.const_id(term)


def _is_synthetic(term) -> bool:
    """rdflib introduces vars like ``__agg_1__``; don't draw them as nodes."""
    return isinstance(term, Variable) and str(term).startswith("__")


class Namer:
    """Pre-pass that populates a :class:`Scope` from an algebra subtree."""

    def __init__(self, scope: Scope):
        self.scope = scope

    def collect(self, node) -> None:
        self._visit(node)

    # ------------------------------------------------------------------ #
    def _register(self, term, *, as_node: bool) -> None:
        if is_path(term) or _is_synthetic(term):
            return
        self.scope.id_of(term)
        if as_node and classify(term) == "const":
            self.scope.used_as_node.add(term)

    def _visit(self, node) -> None:
        name = name_of(node)
        if name is None:
            return
        if name in ("SelectQuery", "ConstructQuery", "DescribeQuery", "AskQuery"):
            if name == "SelectQuery":
                for v in node.get("PV", []) or []:
                    if not _is_synthetic(v):
                        self.scope.projected.add(str(v))
            self._visit(node.p)
        elif name in ("Project", "Distinct", "Reduced", "Slice", "OrderBy",
                      "Group", "ToMultiSet", "Graph"):
            self._visit(node.p)
        elif name == "AggregateJoin":
            for agg in node.A:
                self.scope.var_id(agg.res)
            self._visit(node.p)
        elif name == "Extend":
            self.scope.var_id(node.var)
            self._visit_expr(node.expr)
            self._visit(node.p)
        elif name == "BGP":
            for s, p, o in node.triples:
                self._register(s, as_node=True)
                self._register(p, as_node=False)
                self._register(o, as_node=True)
        elif name == "Filter":
            self._visit_expr(node.expr)
            self._visit(node.p)
        elif name in ("Join", "Union", "Minus", "LeftJoin"):
            self._visit(node.p1)
            self._visit(node.p2)
            if name == "LeftJoin" and "expr" in node:
                self._visit_expr(node.expr)
        elif name == "ServiceGraphPattern":
            self._visit(expand_group_graph_pattern(node.graph))
        elif name == "values":
            for binding in node.res:
                for var, val in binding.items():
                    self.scope.var_id(var)
                    if val is not None:
                        self._register(val, as_node=True)
        else:
            for key in ("p", "p1", "p2"):
                if key in node:
                    self._visit(node[key])

    def _visit_expr(self, expr) -> None:
        if isinstance(expr, Variable):
            if not _is_synthetic(expr):
                self.scope.var_id(expr)
            return
        if isinstance(expr, (URIRef, Literal)):
            return
        name = name_of(expr)
        if name is None:
            return
        if name == "Builtin_EXISTS" or name == "Builtin_NOTEXISTS":
            return  # nested EXISTS gets its own scope in the renderer
        if name == "RelationalExpression" and expr.op in ("IN", "NOT IN"):
            self._visit_expr(expr.expr)
            for member in expr.other or []:
                if isinstance(member, (URIRef, Literal)):
                    self._register(member, as_node=True)
                else:
                    self._visit_expr(member)
            return
        for key, value in expr.items():
            if key == "_vars":
                continue
            self._visit_children(value)

    def _visit_children(self, value) -> None:
        if isinstance(value, Variable):
            if not _is_synthetic(value):
                self.scope.var_id(value)
        elif isinstance(value, (URIRef, Literal)):
            return
        elif isinstance(value, list):
            for item in value:
                self._visit_children(item)
        elif name_of(value) is not None:
            self._visit_expr(value)
