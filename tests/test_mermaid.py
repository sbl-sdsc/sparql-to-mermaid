"""Structural-equivalence tests for the SPARQL->Mermaid port.

The first group mirrors the Java unit tests (weak ``contains`` assertions on the
same query bodies from ``ExamplesUsedInTest``). The rest assert the structural
markers for each SPARQL feature.
"""

import pytest

from sparql_to_mermaid import SparqlToMermaidError, to_mermaid, try_to_mermaid
from sparql_to_mermaid.__main__ import main

PFX = (
    "PREFIX ex: <http://example.org/>\n"
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
)

# --- fixtures ported from ExamplesUsedInTest ------------------------------- #

SIMPLE = """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX SWISSLIPID: <https://swisslipids.org/rdf/SLM_>
SELECT ?category ?label
WHERE {
  ?category SWISSLIPID:rank SWISSLIPID:Category .
  ?category rdfs:label ?label .
}"""

RHEA9 = """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rh: <http://rdf.rhea-db.org/>
PREFIX ec: <http://purl.uniprot.org/enzyme/>
SELECT ?ec ?ecNumber ?rhea ?accession ?equation
WHERE {
  ?rhea rdfs:subClassOf rh:Reaction .
  ?rhea rh:accession ?accession .
  ?rhea rh:ec ?ec .
  BIND(strafter(str(?ec),str(ec:)) as ?ecNumber)
  ?rhea rh:isTransport ?isTransport .
  ?rhea rh:equation ?equation .
}"""

RHEA9_ANON = """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rh: <http://rdf.rhea-db.org/>
PREFIX ec: <http://purl.uniprot.org/enzyme/>
SELECT ?ec ?ecNumber ?rhea
WHERE {
  ?rhea rdfs:subClassOf rh:Reaction .
  ?rhea rh:accession 'lala' .
  ?rhea rh:ec ?ec .
  BIND(strafter(str(?ec),str(ec:)) as ?ecNumber)
  ?rhea rh:isTransport ?isTransport .
  ?rhea rh:equation [] .
  FILTER(?isTransport = true)
  FILTER(contains(?isTransport, "true"))
}"""

FILTER_IN = """PREFIX ex: <http://example.org/>
SELECT ?ex
WHERE {
  [] ex:pred ?ex .
  FILTER( ?ex IN ( ex:left , ex:right ))
}"""


def test_simple_contains_prefix():
    assert "SWISSLIPID:" in to_mermaid(SIMPLE)


def test_rhea9_contains_predicate():
    assert "rh:ec" in to_mermaid(RHEA9)


def test_rhea9_anon_contains_predicate():
    assert "rh:ec" in to_mermaid(RHEA9_ANON)


def test_filter_in_contains_in():
    assert "in" in to_mermaid(FILTER_IN)


# --- every diagram is a well-formed graph TD ------------------------------- #


@pytest.mark.parametrize("q", [SIMPLE, RHEA9, RHEA9_ANON, FILTER_IN])
def test_starts_with_graph_td_and_styles(q):
    out = to_mermaid(q)
    assert out.startswith("graph TD")
    assert "classDef projected fill:lightgreen;" in out


# --- per-feature structural markers ---------------------------------------- #


def test_bgp_constant_predicate_is_edge_label():
    out = to_mermaid(SIMPLE)
    assert '--"SWISSLIPID:rank"-->' in out
    assert ":::projected" in out  # projected variables highlighted
    assert ":::iri" in out  # constant node styled


def test_rdf_type_rendered_as_a():
    out = to_mermaid(PFX + "SELECT ?s WHERE { ?s a ex:Thing }")
    assert '--"a"-->' in out


def test_optional_uses_subgraph_and_dotted_arrow():
    out = to_mermaid(PFX + "SELECT ?s WHERE { ?s ex:a ?o OPTIONAL { ?s ex:b ?x } }")
    assert "subgraph optional0" in out
    assert "stroke-dasharray: 5 5" in out
    assert '-."ex:b".->' in out


def test_union_wraps_both_sides():
    # collapse_empty_unions is on by default and these arms share all their nodes,
    # so disable it to assert the faithful two-arm wrapping.
    out = to_mermaid(
        PFX + "SELECT ?s WHERE { { ?s ex:a ?o } UNION { ?s ex:b ?o } }",
        collapse_empty_unions=False,
    )
    assert "subgraph union0" in out
    assert "<== or ==>" in out


def test_filter_node_and_edges():
    out = to_mermaid(PFX + "SELECT ?s WHERE { ?s ex:a ?o FILTER(?o > 1) }")
    assert "[[" in out and "]]" in out  # filter node shape
    assert "?o >" in out
    # typed literals carry their datatype suffix, exactly like the Java output
    assert "xsd:integer" in out
    assert "f0 --> " in out  # filter connects to the variable it constrains


def test_filter_in_members_and_blank_node():
    out = to_mermaid(FILTER_IN)
    assert " in " in out
    assert "--o" in out  # IN member connects to the filter
    assert '((" "))' in out  # blank-node [] rendered as an anonymous node


def test_bind_node_and_as_edge():
    out = to_mermaid(RHEA9)
    assert "[/" in out and "/]" in out  # bind node shape
    assert "--as--o" in out
    assert "strafter(" in out


def test_variadic_builtin_args_are_rendered():
    # Regression: variadic builtins (CONCAT, COALESCE, ...) store their args in
    # a list; that list must be rendered element-by-element, not str()-ed into a
    # raw `[rdflib.term.Literal(...), rdflib.term.Variable(...)]` repr.
    out = to_mermaid(
        PFX + "SELECT ?y WHERE { ?x ex:p ?z BIND(CONCAT('a/', STR(?x)) AS ?y) }"
    )
    assert "concat('a/',str(?x))" in out
    assert "rdflib.term" not in out


def test_values_node():
    out = to_mermaid(PFX + "SELECT ?s WHERE { VALUES ?s { ex:a ex:b } ?s ex:p ?o }")
    assert "VALUES ?s" in out
    # the label is quoted so annotations/special characters can't break parsing
    assert '[/"VALUES ?s"/]' in out


def test_unshortened_iri_node_and_edge_are_quoted():
    # An IRI with no matching prefix is emitted in full; it must still be quoted
    # (node label and edge-label predicate alike) so a stray '(' -- as in some
    # Reactome/PubChem IRIs -- can't break Mermaid parsing.
    out = to_mermaid(
        "SELECT ?s WHERE { ?s <http://ex/p> <http://ex/o(1)> }", well_known=False
    )
    assert '(["http://ex/o(1)"])' in out
    assert '--"http://ex/p"-->' in out


def test_values_iri_has_no_orphan_constant_node():
    # Regression: a VALUES value used only in the VALUES clause must not also be
    # emitted as a dangling top-level constant node. Previously the Namer
    # registered it with as_node=True, producing a duplicate `cN([...]):::iri`
    # with no edges alongside the value node that _values() draws itself.
    out = to_mermaid(PFX + "SELECT ?s WHERE { VALUES ?sub { ex:x } ?s ex:p ?sub }")
    assert '[/"VALUES ?sub"/]' in out
    # the value appears exactly once (only inside the VALUES value node)
    assert out.count("ex:x") == 1
    # ex:x is drawn only as a VALUES value node, never as a styled iri constant
    assert ":::iri" not in out


# A 12-value VALUES list, used to exercise the max_values cap.
_TWELVE = " ".join(f"ex:v{i}" for i in range(12))
_MANY_VALUES = PFX + f"SELECT ?s WHERE {{ VALUES ?s {{ {_TWELVE} }} ?s ex:p ?o }}"


def test_values_collapses_long_list_by_default():
    out = to_mermaid(_MANY_VALUES)  # default max_values=3
    assert '[/"VALUES ?s"/]' in out
    # exactly 3 value nodes are drawn, then one "+N more" summary node
    assert out.count("([\"ex:v") == 3
    assert "([+9 more])" in out
    # the 4th value (index 3) and beyond are not drawn
    assert "ex:v3" not in out
    assert "ex:v11" not in out


def test_values_below_threshold_unchanged():
    out = to_mermaid(PFX + "SELECT ?s WHERE { VALUES ?s { ex:a ex:b ex:c } ?s ex:p ?o }")
    assert out.count("([\"ex:") == 3
    assert "more])" not in out


def test_values_no_cap_shows_all():
    out = to_mermaid(_MANY_VALUES, max_values=None)
    assert out.count("([\"ex:v") == 12
    assert "more])" not in out


def test_values_collapsed_value_has_no_orphan_constant():
    # A value that is dropped by the cap and appears only in the VALUES clause
    # must not resurface as a styled iri constant node elsewhere.
    out = to_mermaid(_MANY_VALUES)
    assert ":::iri" not in out
    assert out.count("ex:v11") == 0


def test_service_subgraph():
    out = to_mermaid(
        PFX + "SELECT ?s WHERE { ?s ex:a ?o SERVICE <http://ep/sparql> { ?s ex:b ?x } }"
    )
    assert "http://ep/sparql" in out
    assert "stroke-width:4px" in out


def test_minus_subgraph():
    out = to_mermaid(PFX + "SELECT ?s WHERE { ?s ex:a ?o MINUS { ?s ex:c ?y } }")
    assert 'subgraph minus0["MINUS"]' in out
    assert "fill:pink" in out


def test_graph_named_iri_subgraph():
    out = to_mermaid(PFX + "SELECT ?s WHERE { GRAPH ex:g { ?s ex:p ?o } }")
    assert 'subgraph graph0["GRAPH ex:g"]' in out  # IRI shortened via prefixes
    assert "fill:#f3e5f5" in out
    assert "color:#000" in out  # title text forced black for theme readability
    assert '--"ex:p"-->' in out  # inner pattern rendered inside the box


def test_graph_variable_name():
    out = to_mermaid(PFX + "SELECT ?s ?g WHERE { GRAPH ?g { ?s ex:p ?o } }")
    assert 'GRAPH ?g' in out


def test_graph_constants_are_scoped_per_block():
    # An IRI used inside two different GRAPH blocks must be drawn as its own node
    # inside each block -- a node can't belong to two Mermaid subgraphs at once,
    # so a single shared node would make the boxes overlap. There must also be no
    # orphan copy declared at the top level.
    out = to_mermaid(
        PFX
        + "SELECT ?s WHERE { GRAPH ex:g1 { ?s ex:p ex:x } GRAPH ex:g2 { ?s ex:q ex:x } }"
    )
    assert 'subgraph graph0["GRAPH ex:g1"]' in out
    assert 'subgraph graph1["GRAPH ex:g2"]' in out
    # one local copy of ex:x per box (two total), not a single shared node
    assert out.count('(["ex:x"])') == 2
    # both copies are prefixed with their owning box's id (no bare top-level node)
    assert "graph0c" in out and "graph1c" in out


def test_exists_subgraph():
    out = to_mermaid(PFX + "SELECT ?s WHERE { ?s ex:a ?o FILTER EXISTS { ?s ex:b ?x } }")
    assert "Exists Clause" in out
    assert "--EXISTS-->" in out
    # nested scope ids are prefixed so they do not clash with the outer scope
    assert "e0v" in out


def test_property_paths_as_edge_labels():
    out = to_mermaid(
        PFX + "SELECT ?s WHERE { ?s rdfs:subClassOf* ex:Root . ?s ex:a/ex:b ?o }"
    )
    assert "rdfs:subClassOf*" in out
    assert "ex:a/ex:b" in out


def test_count_star():
    # rdflib's CompValue.get() quirk once made this render as count(vars).
    out = to_mermaid(PFX + "SELECT (COUNT(*) AS ?n) WHERE { ?s ex:a ?o }")
    assert "count(*)" in out
    assert "vars" not in out


def test_regex_without_flags_has_no_none_arg():
    out = to_mermaid(PFX + 'SELECT ?s WHERE { ?s ex:a ?o FILTER regex(?o, "^x") }')
    assert "regex(" in out
    assert ",None" not in out
    assert ",flags" not in out


def test_well_known_fallback_shortens_undeclared_iri():
    # query declares only rdfs; the full OBO MONDO IRI still shortens.
    q = (
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "SELECT ?t WHERE { ?t rdfs:subClassOf "
        "<http://purl.obolibrary.org/obo/MONDO_0005148> }"
    )
    assert "MONDO:0005148" in to_mermaid(q)
    assert "http://purl.obolibrary.org/obo/MONDO_0005148" not in to_mermaid(q)


def test_well_known_can_be_disabled():
    q = (
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "SELECT ?t WHERE { ?t rdfs:subClassOf "
        "<http://purl.obolibrary.org/obo/MONDO_0005148> }"
    )
    out = to_mermaid(q, well_known=False)
    assert "MONDO:0005148" not in out
    assert "http://purl.obolibrary.org/obo/MONDO_0005148" in out


def test_declared_prefix_beats_well_known():
    # the author's own prefix for the MONDO id space wins over the built-in one.
    q = (
        "PREFIX dis: <http://purl.obolibrary.org/obo/MONDO_>\n"
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "SELECT ?t WHERE { ?t rdfs:subClassOf dis:0005148 }"
    )
    out = to_mermaid(q)
    assert "dis:0005148" in out
    assert "MONDO:0005148" not in out


def test_function_iri_is_prefix_shortened():
    q = (
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
        "PREFIX ex: <http://example.org/>\n"
        "SELECT ?s WHERE { ?s ex:a ?val BIND(xsd:double(?val) AS ?d) }"
    )
    out = to_mermaid(q)
    assert "xsd:double(?val)" in out
    assert "http://www.w3.org/2001/XMLSchema#double" not in out


def test_aggregate_bind():
    out = to_mermaid(PFX + "SELECT ?s (COUNT(?o) AS ?n) WHERE { ?s ex:a ?o } GROUP BY ?s")
    assert "count(?o)" in out
    # the synthetic SAMPLE aggregate rdflib adds for the group key is suppressed
    assert "sample(" not in out


def test_no_dangling_node_references():
    """Every edge endpoint id must be declared as a node somewhere in output."""
    out = to_mermaid(PFX + "SELECT ?s WHERE { ?s ex:a ?o FILTER EXISTS { ?s ex:b ?x } }")
    # ?x lives only inside EXISTS; it must not leak into an outer-scope edge.
    assert "f0 --> v3" not in out


# --- error handling -------------------------------------------------------- #


def test_malformed_query_raises():
    with pytest.raises(SparqlToMermaidError):
        to_mermaid("this is not sparql")


def test_try_variant_returns_none_on_error():
    assert try_to_mermaid("this is not sparql") is None


# --- collapse_empty_unions ------------------------------------------------- #

# Both arms are the same triple in opposite directions, so they reference the
# same nodes (?s, ex:X). Mermaid places those nodes in the later arm, leaving the
# earlier arm's box empty -- exactly what the collapse pass cleans up.
BIDIR_UNION = PFX + "SELECT ?s WHERE { { ?s ex:a ex:X } UNION { ex:X ex:a ?s } }"
# Each arm has a node the other lacks (?o vs ?p), so neither box is ever empty.
DISTINCT_UNION = PFX + "SELECT ?s WHERE { { ?s ex:a ?o } UNION { ?s ex:c ?p } }"


def test_collapse_drops_empty_arm_and_connector_by_default():
    out = to_mermaid(BIDIR_UNION)
    # The arm Mermaid would render empty is unwrapped, style line and all ...
    assert "subgraph union0l" not in out
    assert "style union0l" not in out
    # ... together with the now-dangling `or` connector ...
    assert "<== or ==>" not in out
    # ... but the outer Union box, the populated arm and *both* edges survive.
    assert "subgraph union0[" in out
    assert "subgraph union0r" in out
    assert 'c2 --"ex:a"--> v1' in out
    assert 'v1 --"ex:a"--> c2' in out


def test_collapse_leaves_no_dangling_reference_to_dropped_arm():
    out = to_mermaid(BIDIR_UNION)
    assert "union0l" not in out


def test_collapse_disabled_keeps_empty_arm():
    out = to_mermaid(BIDIR_UNION, collapse_empty_unions=False)
    assert "subgraph union0l" in out
    assert "subgraph union0r" in out
    assert "<== or ==>" in out


def test_collapse_leaves_distinct_node_unions_untouched():
    # Neither arm is empty, so the collapse pass is a no-op: the default output
    # matches the faithful (uncollapsed) one, both arms and the connector intact.
    faithful = to_mermaid(DISTINCT_UNION, collapse_empty_unions=False)
    default = to_mermaid(DISTINCT_UNION)
    assert default == faithful
    assert "subgraph union0l" in default
    assert "subgraph union0r" in default
    assert "<== or ==>" in default


def test_cli_drops_empty_arm_by_default(tmp_path, capsys):
    qf = tmp_path / "q.rq"
    qf.write_text(BIDIR_UNION)
    assert main([str(qf)]) == 0
    out = capsys.readouterr().out
    assert "subgraph union0l" not in out
    assert "<== or ==>" not in out


def test_cli_no_collapse_flag_keeps_empty_arm(tmp_path, capsys):
    qf = tmp_path / "q.rq"
    qf.write_text(BIDIR_UNION)
    assert main([str(qf), "--no-collapse-empty-unions"]) == 0
    out = capsys.readouterr().out
    assert "subgraph union0l" in out
    assert "<== or ==>" in out


def test_cli_collapses_values_by_default(tmp_path, capsys):
    qf = tmp_path / "q.rq"
    qf.write_text(_MANY_VALUES)
    assert main([str(qf)]) == 0
    out = capsys.readouterr().out
    assert out.count("([\"ex:v") == 3
    assert "([+9 more])" in out


def test_cli_no_max_values_flag_shows_all(tmp_path, capsys):
    qf = tmp_path / "q.rq"
    qf.write_text(_MANY_VALUES)
    assert main([str(qf), "--no-max-values"]) == 0
    out = capsys.readouterr().out
    assert out.count("([\"ex:v") == 12
    assert "more])" not in out


def test_cli_max_values_flag_sets_threshold(tmp_path, capsys):
    qf = tmp_path / "q.rq"
    qf.write_text(_MANY_VALUES)
    assert main([str(qf), "--max-values", "5"]) == 0
    out = capsys.readouterr().out
    assert out.count("([\"ex:v") == 5
    assert "([+7 more])" in out
