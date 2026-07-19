"""Walk the rdflib algebra and emit Mermaid ``graph TD`` lines.

Ports the ``Render`` visitor. Instead of RDF4j's ``meet(...)`` overrides this
dispatches on ``CompValue.name``, but the emitted Mermaid grammar (arrows,
subgraphs, styles, escaping) mirrors the Java output.
"""

from __future__ import annotations

from rdflib.term import Literal, URIRef, Variable

from .algebra import expand_group_graph_pattern, name_of
from .expr import collect_vars, expr_to_string
from .naming import Namer, Scope, _is_synthetic
from .paths import is_path, path_to_string
from .prefixes import PrefixMap, classify, escape


class Renderer:
    def __init__(
        self,
        scope: Scope,
        prefixes: PrefixMap,
        lines: list[str],
        indent: int = 2,
        counters: dict | None = None,
        max_values: int | None = None,
    ):
        self.scope = scope
        self.prefixes = prefixes
        self.lines = lines
        self.indent = indent
        self.optional = False
        # cap on how many VALUES value nodes to draw (None = unlimited)
        self.max_values = max_values
        # counters shared across nested scopes so ids stay unique
        self.counters = counters if counters is not None else {}
        self.service_keys: dict = {}
        self.agg_map: dict = {}
        self.skip_agg: set = set()

    # ------------------------------------------------------------------ #
    def prescan_aggregates(self, node) -> None:
        """Populate ``agg_map``/``skip_agg`` up front so aggregate result names
        (rdflib's ``__agg_N__``) resolve cleanly wherever they are referenced,
        e.g. inside a HAVING filter that sits above the ``AggregateJoin``."""
        for agg_join in _find(node, "AggregateJoin"):
            for agg in agg_join.A:
                self.agg_map[str(agg.res)] = self._aggregate_string(agg)
                if name_of(agg) == "Aggregate_Sample":
                    self.skip_agg.add(str(agg.res))

    def _resolve_aggs(self, text: str) -> str:
        for res, agg_str in self.agg_map.items():
            text = text.replace(f"?{res}", agg_str)
        return text

    def _next(self, kind: str) -> int:
        n = self.counters.get(kind, 0)
        self.counters[kind] = n + 1
        return n

    def _pad(self) -> str:
        return " " * self.indent

    def _add(self, text: str) -> None:
        self.lines.append(self._pad() + text)

    def _id(self, term) -> str:
        return self.scope.id_of(term)

    # -- styling / variable declarations ------------------------------- #
    def add_styles(self) -> None:
        self.lines.append("classDef projected fill:lightgreen;")
        self.lines.append("classDef literal fill:orange;")
        self.lines.append("classDef iri fill:yellow;")

    def render_variables(self) -> None:
        for name in sorted(self.scope.var_ids):
            if _is_synthetic(Variable(name)):
                continue
            cls = ":::projected " if name in self.scope.projected else ""
            self._add(f'{self.scope.var_ids[name]}("?{name}"){cls}')
        for key in sorted(self.scope.bnode_ids):
            self._add(f'{self.scope.bnode_ids[key]}((" "))')
        self.render_constants()

    def render_constants(self) -> None:
        for term in sorted(self.scope.const_ids, key=str):
            if term not in self.scope.used_as_node:
                continue
            label = self.prefixes.term(term, quote='"')
            self._add(f"{self.scope.const_ids[term]}([{label}]){self._const_cls(term)}")

    def _const_cls(self, term) -> str:
        if isinstance(term, Literal):
            return ":::literal "
        if isinstance(term, URIRef):
            return ":::iri "
        return ""

    # -- dispatch ------------------------------------------------------- #
    def visit(self, node) -> None:
        name = name_of(node)
        if name is None:
            return
        handler = getattr(self, f"_{name}", None)
        if handler is not None:
            handler(node)
        else:
            for key in ("p", "p1", "p2"):
                if key in node:
                    self.visit(node[key])

    # top-level query wrappers
    def _SelectQuery(self, node):
        self.visit(node.p)

    _ConstructQuery = _SelectQuery
    _DescribeQuery = _SelectQuery
    _AskQuery = _SelectQuery

    def _Project(self, node):
        self.visit(node.p)

    _Distinct = _Project
    _Reduced = _Project
    _Slice = _Project
    _OrderBy = _Project
    _ToMultiSet = _Project
    _Group = _Project

    def _AggregateJoin(self, node):
        self.visit(node.p)

    def _aggregate_string(self, agg) -> str:
        fn = {
            "Aggregate_Count": "count",
            "Aggregate_Sum": "sum",
            "Aggregate_Avg": "average",
            "Aggregate_Min": "min",
            "Aggregate_Max": "max",
            "Aggregate_Sample": "sample",
            "Aggregate_GroupConcat": "group_concat",
        }.get(name_of(agg), "agg")
        if "vars" not in agg:
            return f"{fn}(*)"
        return f"{fn}({expr_to_string(agg['vars'], self.prefixes)})"

    def _Join(self, node):
        self.visit(node.p1)
        self.visit(node.p2)

    # -- BGP / triples -------------------------------------------------- #
    def _BGP(self, node):
        for s, p, o in node.triples:
            self._triple(s, p, o)

    def _triple(self, s, p, o):
        subj = self._id(s)
        obj = self._id(o)
        if is_path(p):
            label = path_to_string(p, self.prefixes)
            self._add(self._arrow(subj, obj, f'"{label}"'))
        elif classify(p) == "const" and p not in self.scope.used_as_node:
            pred = self.prefixes.term(p, quote='"')
            self._add(self._arrow(subj, obj, pred))
        else:
            pred = self._id(p)
            self._add(f"{subj} -->{pred}--> {obj}")

    def _arrow(self, subj, obj, pred) -> str:
        if self.optional:
            self.optional = False
            return f"{subj} -.{pred}.-> {obj}"
        return f"{subj} --{pred}--> {obj}"

    # -- FILTER --------------------------------------------------------- #
    def _Filter(self, node):
        filter_id = f"{self.scope.prefix}f{self._next('filter')}"
        text = self._resolve_aggs(expr_to_string(node.expr, self.prefixes))
        self._add(f'{filter_id}[["{text}"]]')
        self._filter_in_members(node.expr, filter_id)
        self._exists_in_expr(node.expr, filter_id)
        for var in collect_vars(node.expr):
            self._add(f"{filter_id} --> {self._id(var)}")
        self.visit(node.p)

    def _filter_in_members(self, expr, filter_id):
        for rel in _find(expr, "RelationalExpression"):
            if rel.op in ("IN", "NOT IN"):
                for member in rel.other or []:
                    if isinstance(member, (URIRef, Literal)):
                        self._add(f"{self._id(member)} --o {filter_id}")

    def _exists_in_expr(self, expr, parent_id):
        for ex in _find(expr, "Builtin_EXISTS") + _find(expr, "Builtin_NOTEXISTS"):
            self._render_exists(parent_id, ex)

    def _render_exists(self, parent_id, exists_node):
        exist_id = f"{self.scope.prefix}e{self._next('exist')}"
        sub = expand_group_graph_pattern(exists_node.graph)
        self._add(f'subgraph {parent_id}{exist_id}["Exists Clause"]')
        self.indent += 2
        self._add(f"style {parent_id}{exist_id} color:#000;")
        nested = Scope(prefix=exist_id)
        Namer(nested).collect(sub)
        r = Renderer(nested, self.prefixes, self.lines, self.indent, self.counters, self.max_values)
        r.visit(sub)
        r.render_variables()
        self.indent -= 2
        self._add("end")
        self._add(f"{parent_id}--EXISTS--> {parent_id}{exist_id}")

    # -- BIND (Extend) -------------------------------------------------- #
    def _Extend(self, node):
        self.visit(node.p)
        expr = node.expr
        if isinstance(expr, Variable) and str(expr) in self.skip_agg:
            return
        bind_id = f"{self.scope.prefix}bind{self._next('bind')}"
        if isinstance(expr, Variable) and str(expr) in self.agg_map:
            text = self.agg_map[str(expr)]
            source_vars = []
        else:
            text = expr_to_string(expr, self.prefixes)
            source_vars = collect_vars(expr)
        self._add(f'{bind_id}[/"{text}"/]')
        self._exists_in_expr(expr, bind_id)
        for var in source_vars:
            self._add(f"{self._id(var)} --o {bind_id}")
        if str(node.var) in self.scope.var_ids:
            self._add(f"{bind_id} --as--o {self.scope.var_ids[str(node.var)]}")

    # -- VALUES --------------------------------------------------------- #
    def _values(self, node):
        bind_id = f"{self.scope.prefix}bind{self._next('bind')}"
        names: list[str] = []
        for binding in node.res:
            for var in binding:
                if str(var) not in names:
                    names.append(str(var))
        names.sort()
        header = " ".join(f"?{n}" for n in names)
        # Quote the label so an annotated or unusual header (parentheses, etc.)
        # can't derail Mermaid's parser -- matches the quoted BIND node below.
        self._add(f'{bind_id}[/"VALUES {header}"/]')
        for n in names:
            self._add(f"{bind_id}-->{self.scope.var_id(n)}")
        vals = [val for binding in node.res for val in binding.values() if val is not None]
        # Collapse a long tail into a single "+N more" node so a big VALUES list
        # doesn't fan out to one node per value. The +1 guard avoids a pointless
        # "+1 more" node that would save nothing.
        limit = self.max_values
        if limit is not None and len(vals) > limit + 1:
            shown, remaining = vals[:limit], len(vals) - limit
        else:
            shown, remaining = vals, 0
        for value_n, val in enumerate(shown):
            vid = f"{bind_id}{value_n}"
            label = self.prefixes.term(val, quote='"')
            self._add(f"{vid}([{label}])")
            self._add(f"{vid} --> {bind_id}")
        if remaining:
            self._add(f"{bind_id}more([+{remaining} more])")
            self._add(f"{bind_id}more --> {bind_id}")

    # -- OPTIONAL / UNION / MINUS / SERVICE ----------------------------- #
    def _LeftJoin(self, node):
        self.visit(node.p1)
        self.optional = True
        opt_id = f"optional{self.scope.prefix}{self._next('optional')}"
        self._add(f'subgraph {opt_id}["(optional)"]')
        self._add(f"style {opt_id} fill:#bbf,stroke-dasharray: 5 5,color:#000;")
        self.indent += 2
        self.visit(node.p2)
        self.indent -= 2
        self._add("end")

    def _Union(self, node):
        uid = f"union{self.scope.prefix}{self._next('union')}"
        self._add(f'subgraph {uid}[" Union "]')
        self._add(f"style {uid} color:#000;")
        self._add(f'subgraph {uid}l[" "]')
        self.indent += 2
        self._add(f"style {uid}l fill:#abf,stroke-dasharray: 3 3;")
        self.visit(node.p2)
        self.indent -= 2
        self._add("end")
        self._add(f'subgraph {uid}r[" "]')
        self.indent += 2
        self._add(f"style {uid}r fill:#abf,stroke-dasharray: 3 3;")
        self.visit(node.p1)
        self.indent -= 2
        self._add("end")
        self._add(f"{uid}r <== or ==> {uid}l")
        self._add("end")

    def _Minus(self, node):
        self.visit(node.p1)
        key = f"minus{self._next('minus')}"
        self._add(f'subgraph {key}["MINUS"]')
        self.indent += 2
        self._add(f"style {key} stroke-width:6px,fill:pink,stroke:red,color:#000;")
        self.visit(node.p2)
        self.indent -= 2
        self._add("end")

    def _Graph(self, node):
        gid = f"graph{self.scope.prefix}{self._next('graph')}"
        self._add(f'subgraph {gid}["{self._graph_label(node.term)}"]')
        self.indent += 2
        # color:#000 forces the title text black; some viewer themes render
        # cluster labels in a light color that's unreadable on the box fill.
        self._add(f"style {gid} fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px,color:#000;")
        # A named graph draws with its own scope so its constants are boxed
        # locally (a shared reference IRI can't live in two Mermaid subgraphs at
        # once). Variables and blank nodes stay shared with the parent scope so
        # a variable joining across graph boundaries remains a single node.
        nested = Scope(prefix=gid)
        nested.var_ids = self.scope.var_ids
        nested.bnode_ids = self.scope.bnode_ids
        nested.projected = self.scope.projected
        Namer(nested).collect(node.p)
        r = Renderer(nested, self.prefixes, self.lines, self.indent, self.counters, self.max_values)
        r.agg_map = self.agg_map
        r.skip_agg = self.skip_agg
        r.render_constants()
        r.visit(node.p)
        self.indent -= 2
        self._add("end")

    def _graph_label(self, term) -> str:
        if isinstance(term, Variable):
            return f"GRAPH ?{term}"
        return "GRAPH " + escape(self.prefixes.shorten(str(term)))

    def _ServiceGraphPattern(self, node):
        term = node.term
        iri = str(term) if term is not None else "ERROR: Bad value"
        if term not in self.service_keys:
            self.service_keys[term] = (
                f"{self.scope.prefix}s{len(self.service_keys) + 1}"
            )
        key = self.service_keys[term]
        self._add(f'subgraph {key}["{iri}"]')
        self.indent += 2
        self._add(f"style {key} stroke-width:4px,color:#000;")
        self.visit(expand_group_graph_pattern(node.graph))
        self.indent -= 2
        self._add("end")


def _find(node, target_name: str) -> list:
    """Collect all descendant CompValues (and the node) with the given name."""
    out: list = []

    def walk(n):
        if isinstance(n, Variable) or isinstance(n, (URIRef, Literal)):
            return
        if name_of(n) is not None:
            if n.name == target_name:
                out.append(n)
            for key, value in n.items():
                if key != "_vars":
                    walk(value)
        elif isinstance(n, list):
            for item in n:
                walk(item)

    walk(node)
    return out
