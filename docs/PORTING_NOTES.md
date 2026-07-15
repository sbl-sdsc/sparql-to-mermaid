# Porting notes

`sparql-to-mermaid` is a pure-Python port of the SPARQL→Mermaid converter in the
Java project [`sparql-examples-utils`](https://github.com/sib-swiss/sparql-examples-utils)
— specifically the `swiss.sib.rdf.sparql.examples.mermaid` package (driven from
its `convert -m` CLI, which embeds the diagram in per-example Markdown). The port
exists so the same diagram generation is available to Python services (notably the
[mcp-okn](https://github.com/sbl-sdsc/mcp-okn) server) without a JVM.

## Design

- **rdflib algebra, not a custom parser.** Queries are parsed with
  `rdflib.plugins.sparql` and rendered by walking the algebra tree, mirroring how
  the Java code walks RDF4j's `TupleExpr` with a visitor.
- **Raw query string is the primary input** (`to_mermaid(query, prefixes=None)`),
  since callers such as mcp-okn already hold the query text. The Java tool instead
  reads the sparql-examples Turtle (`sh:select`/`sh:ask`) wrapper.
- **Fidelity bar: structural equivalence, not byte-for-byte identity.** rdflib
  normalizes the algebra differently from RDF4j, so node ids (`v1`, `c2`, …) and
  line ordering can differ, but the diagram shows the same nodes, edges, and
  structural blocks (OPTIONAL/UNION/FILTER/BIND/VALUES/SERVICE/MINUS/EXISTS) with
  the same visual grammar (arrows, subgraphs, `projected`/`iri`/`literal` styles,
  `rdf:type` → `"a"`, bracket escaping, datatype suffixes).

## Module map (Java → Python)

| Java | Python | Responsibility |
| --- | --- | --- |
| `Render.java` | `render.py` | the core algebra walker emitting Mermaid lines |
| `NameVariablesAndConstants` + `FindWhichConstantsAreNotOnlyUsedAsPredicates` | `naming.py` | assign `v`/`a`/`c` node ids; decide which constants are drawn as nodes |
| `ValueExprAsString` (inner visitor) | `expr.py` | stringify FILTER/BIND expressions, IN lists, aggregates |
| `prefix(...)` / `escape(...)` | `prefixes.py` | IRI shortening, escaping, literal formatting |
| — (no analog) | `paths.py` | render property-path predicates |
| `SparqlInRdfToMermaid` entry | `algebra.py` + `__init__.py` | parse + drive the passes |

## Differences from the Java original (worth knowing)

These are the places the port is **not** a mechanical translation, mostly because
rdflib's algebra differs from RDF4j's:

- **Algebra shape.** RDF4j yields a left-deep tree of individual `StatementPattern`
  nodes; rdflib yields `BGP` blocks of raw `(s,p,o)` term-triples in a different
  tree. The walker is re-authored against rdflib node names, so node numbering and
  triple ordering differ (hence structural, not byte, equivalence).
- **Term model.** RDF4j's unified `Var` (with `isConstant`/`isAnonymous`) becomes
  rdflib's distinct `Variable` / `URIRef` / `Literal` / `BNode`; the `v`/`a`/`c`
  classification is re-derived from those.
- **Property paths.** RDF4j desugars `*`/`+`/`/`/`^` into statement patterns (no
  path-specific Java code); rdflib keeps a `Path` object as the predicate, so the
  port adds explicit path rendering (`paths.py`) — a compact edge label like
  `rdfs:subClassOf*`.
- **SERVICE / EXISTS bodies** are left untranslated in rdflib's main tree; the port
  expands them via `translateGroupGraphPattern` before walking.
- **Aggregates.** rdflib injects a synthetic `SAMPLE` per `GROUP BY` key and
  renames results to `__agg_N__`; the port suppresses the sample noise and resolves
  the synthetic names so a `HAVING` reads e.g. `sum(?o) > '15^^xsd:integer'`.
- **Parser coverage** differs from RDF4j: some vendor-specific queries
  (Wikidata/Blazegraph extensions) that RDF4j accepts may fail here, and vice
  versa. `try_to_mermaid` skips such queries gracefully, mirroring the Java tool.

## Prefix shortening

IRIs are shortened first against the query's own `PREFIX` declarations (and any
caller-supplied prefixes), then against a curated fallback of well-known
life-science / semantic-web prefixes (`well_known.py`: MONDO, CHEBI, GO, HP, NCIT,
biolink, up, efo, …), longest-namespace-match first. Query-declared prefixes always
win; pass `well_known=False` to shorten only against the query's own prefixes.

## Tests

`tests/test_mermaid.py` ports the Java `ExamplesUsedInTest` fixtures as raw query
strings (with the same `contains(...)` assertions) and adds a structural-marker
check per SPARQL feature, plus regression tests for prefix shortening and the
rdflib `CompValue.get()` quirk (an absent key returns the key *name*, not `None`,
which had to be handled for optional args like REGEX flags and `COUNT(*)`).
