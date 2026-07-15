# sparql-to-mermaid

Render a SPARQL query as a [Mermaid](https://mermaid.js.org) `graph TD` diagram.

This is a pure-Python port of the SPARQL→Mermaid converter in the Java project
[`sparql-examples-utils`](https://github.com/sib-swiss/sparql-examples-utils)
(the `convert -m` / `mermaid` package). It is built on
[rdflib](https://rdflib.readthedocs.io)'s SPARQL algebra, so it needs no JVM and
can be used directly from Python services such as the
[`mcp-okn`](https://github.com/sbl-sdsc/mcp-okn) server.

## Install

```bash
uv sync            # or: pip install -e .
```

Requires Python ≥ 3.10 and rdflib ≥ 7.

## Usage

```python
from sparql_to_mermaid import to_mermaid

diagram = to_mermaid("""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX SWISSLIPID: <https://swisslipids.org/rdf/SLM_>
SELECT ?category ?label WHERE {
  ?category SWISSLIPID:rank SWISSLIPID:Category .
  ?category rdfs:label ?label .
}
""")
print(diagram)
```

- `to_mermaid(query, prefixes=None, base=...)` returns the diagram string and
  raises `SparqlToMermaidError` if the query cannot be parsed.
- `try_to_mermaid(query, ...)` returns `None` (and logs) instead of raising —
  mirroring the Java behaviour of skipping queries it cannot transform.
- `prefixes` (a `{name: namespace}` dict) supplements the query's own `PREFIX`
  declarations when shortening IRIs.
- `collapse_empty_unions=True` (default `False`, off for parity with the Java
  tool) is a cosmetic pass: when both arms of a `UNION` reference the same nodes,
  Mermaid renders one arm as an empty box; enabling this unwraps that empty arm
  (keeping its edges) and drops the dangling `or` connector.

### Command line

````text
sparql-to-mermaid query.rq                       # prints the diagram
sparql-to-mermaid query.rq --fence               # wraps it in a ```mermaid code fence
sparql-to-mermaid query.rq --collapse-empty-unions  # drop empty UNION arm boxes
cat query.rq | sparql-to-mermaid                 # reads stdin
````

## What is rendered

The same visual grammar as the Java tool: basic graph patterns (constant
predicates as edge labels, `rdf:type` as `"a"`), `OPTIONAL` (dotted arrows in a
blue dashed subgraph), `UNION`, `FILTER` (with `EXISTS` and `IN`), `BIND`,
`VALUES`, `SERVICE`, `MINUS`, aggregates, and property paths. Projected
variables, IRIs and literals get the `projected` / `iri` / `literal` styles.

Named graphs (`GRAPH <iri> { … }` or `GRAPH ?g { … }`) render as a titled
purple subgraph box. Constants are scoped to their box, so a reference IRI that
appears in several `GRAPH` blocks is drawn once inside each — a single shared
node cannot belong to two Mermaid subgraphs and would make the boxes overlap.
Variables stay shared across boxes, so a variable that joins two named graphs
remains one node with edges crossing the box boundaries.

The same single-node limitation shows up in `UNION`: when both arms reference the
same nodes (e.g. one triple written in both directions), Mermaid can only place
those nodes in one arm, so the other arm renders as an empty box tied on by the
`or` connector. This is faithful to the Java tool and left as-is by default; pass
`collapse_empty_unions=True` (or `--collapse-empty-unions`) to unwrap the empty
arm and drop the connector.

### Example: a single named graph

A query against one named graph of the pancreas knowledge graph
[`pankgraph`](https://frink.renci.org/), combining a basic graph pattern with an
`OPTIONAL`, a compound `FILTER` (booleans, arithmetic and typed literals), and
several `BIND` steps — including `xsd:double(…)` casts and a `REPLACE(…)` that
strips a gene IRI down to its Ensembl id:

```sparql
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX pk: <https://purl.org/okn/frink/kg/pankgraph/schema/>
PREFIX biolink: <https://w3id.org/biolink/vocab/>
SELECT ?g ?t2d ?nd ?t1d WHERE {
  GRAPH <https://purl.org/okn/frink/kg/pankgraph> {
    ?stmt rdf:subject ?ocr ; rdf:object <http://purl.obolibrary.org/obo/CL_0002079> ;
          pk:type_2_diabetes__OCR_GeneActivityScore_mean ?t2d ;
          pk:non_diabetic__OCR_GeneActivityScore_mean ?nd .
    ?ocr biolink:located_in ?gene .
    OPTIONAL { ?stmt pk:type_1_diabetes__OCR_GeneActivityScore_mean ?t1d }
    BIND(xsd:double(?t2d) AS ?a) BIND(xsd:double(?nd) AS ?b)
    FILTER(?b > 0 && ?a > 0 && (?a/?b >= 2.0 || ?a/?b <= 0.5))
    BIND(REPLACE(STR(?gene), "http://identifiers.org/ensembl/", "") AS ?g)
  }
}
```

The whole pattern sits inside the single `GRAPH` box; the `OPTIONAL` nests as a
blue dashed subgraph, the `FILTER` node feeds the variables it constrains, and
each `BIND` reshapes a value with `--o` inputs and an `--as--o` output:

```mermaid
graph TD
classDef projected fill:lightgreen;
classDef literal fill:orange;
classDef iri fill:yellow;
  v2("?a")
  v1("?b")
  v3("?g"):::projected 
  v4("?gene")
  v5("?nd"):::projected 
  v8("?ocr")
  v7("?stmt")
  v9("?t1d"):::projected 
  v6("?t2d"):::projected 
  subgraph graph0["GRAPH https://purl.org/okn/frink/kg/pankgraph"]
    style graph0 fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px;
    graph0c2(["CL:0002079"]):::iri 
    graph0f0[["?b > '0^^xsd:integer' && ?a > '0^^xsd:integer' && (?a / ?b >= '2.0^^xsd:decimal' || ?a / ?b <= '0.5^^xsd:decimal')"]]
    graph0f0 --> v1
    graph0f0 --> v2
    v7 --"rdf:object"--> graph0c2
    v7 --"rdf:subject"--> v8
    v7 --"pk:non_diabetic__OCR_GeneActivityScore_mean"--> v5
    v7 --"pk:type_2_diabetes__OCR_GeneActivityScore_mean"--> v6
    v8 --"biolink:located_in"--> v4
    subgraph optionalgraph00["(optional)"]
    style optionalgraph00 fill:#bbf,stroke-dasharray: 5 5;
      v7 -."pk:type_1_diabetes__OCR_GeneActivityScore_mean".-> v9
    end
    graph0bind0[/"xsd:double(?t2d)"/]
    v6 --o graph0bind0
    graph0bind0 --as--o v2
    graph0bind1[/"xsd:double(?nd)"/]
    v5 --o graph0bind1
    graph0bind1 --as--o v1
    graph0bind2[/"replace(str(?gene),'http://identifiers.org/ensembl/','')"/]
    v4 --o graph0bind2
    graph0bind2 --as--o v3
  end
```

### Example: a multi-graph federated query

This query starts from a disease *label*, resolves it to a DOID in `spoke-okn`,
crosswalks that to the equivalent MONDO id through `ubergraph`, then pulls the
related genes from `rdkg` — three named graphs of the
[Proto-OKN](https://frink.renci.org/) federation joined on shared variables:

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX biolink: <https://w3id.org/biolink/vocab/>
SELECT DISTINCT ?doid ?mondo ?gene ?symbol WHERE {
  GRAPH <https://purl.org/okn/frink/kg/spoke-okn> {
    ?doid a biolink:Disease ; rdfs:label "autism spectrum disorder" .
    FILTER(STRSTARTS(STR(?doid), 'http://purl.obolibrary.org/obo/DOID_'))
  }
  GRAPH <https://purl.org/okn/frink/kg/ubergraph> {
    ?mondo skos:exactMatch ?doid .
    FILTER(STRSTARTS(STR(?mondo), 'http://purl.obolibrary.org/obo/MONDO_'))
  }
  GRAPH <https://purl.org/okn/frink/kg/rdkg> {
    { ?mondo biolink:related_to ?gene } UNION { ?gene biolink:related_to ?mondo }
    ?gene a biolink:Gene .
    OPTIONAL { ?gene rdfs:label ?symbol }
  }
}
```

Each `GRAPH` becomes a self-contained box. The `?doid` and `?mondo` variables are
shared across boxes, so the `skos:exactMatch` and `biolink:related_to` joins draw
as edges crossing the box boundaries, and each `FILTER(STRSTARTS(…))` renders as a
node feeding the variable it constrains. The `rdkg` `UNION` writes the same triple
in both directions, so its two arms reference the same nodes and Mermaid leaves one
arm as an empty box (pass `--collapse-empty-unions` to drop it):

```mermaid
graph TD
classDef projected fill:lightgreen;
classDef literal fill:orange;
classDef iri fill:yellow;
  v1("?doid"):::projected 
  v3("?gene"):::projected 
  v2("?mondo"):::projected 
  v4("?symbol"):::projected 
  subgraph graph0["GRAPH https://purl.org/okn/frink/kg/spoke-okn"]
    style graph0 fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px;
    graph0c2(["autism spectrum disorder"]):::literal 
    graph0c4(["biolink:Disease"]):::iri 
    graph0f0[["strstarts(str(?doid),'http://purl.obolibrary.org/obo/DOID_')"]]
    graph0f0 --> v1
    v1 --"rdfs:label"--> graph0c2
    v1 --"a"--> graph0c4
  end
  subgraph graph1["GRAPH https://purl.org/okn/frink/kg/ubergraph"]
    style graph1 fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px;
    graph1f1[["strstarts(str(?mondo),'http://purl.obolibrary.org/obo/MONDO_')"]]
    graph1f1 --> v2
    v2 --"skos:exactMatch"--> v1
  end
  subgraph graph2["GRAPH https://purl.org/okn/frink/kg/rdkg"]
    style graph2 fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px;
    graph2c3(["biolink:Gene"]):::iri 
    subgraph uniongraph20[" Union "]
    subgraph uniongraph20l[" "]
      style uniongraph20l fill:#abf,stroke-dasharray: 3 3;
      v3 --"biolink:related_to"--> v2
    end
    subgraph uniongraph20r[" "]
      style uniongraph20r fill:#abf,stroke-dasharray: 3 3;
      v2 --"biolink:related_to"--> v3
    end
    uniongraph20r <== or ==> uniongraph20l
    end
    v3 --"a"--> graph2c3
    subgraph optionalgraph20["(optional)"]
    style optionalgraph20 fill:#bbf,stroke-dasharray: 5 5;
      v3 -."rdfs:label".-> v4
    end
  end
```

## Fidelity

The bar is **structural equivalence**, not byte-for-byte identity with the Java
output. rdflib normalizes the SPARQL algebra differently from RDF4j, so node ids
(`v1`, `c2`, …) and line ordering can differ, but the diagram shows the same
nodes, edges and structural blocks. Notable differences from the Java port:

- **Property paths** (`*`, `+`, `/`, `^`, `|`) are rendered as a single edge
  label (e.g. `rdfs:subClassOf*`). RDF4j desugars these into separate patterns;
  rdflib keeps them as a path object, which reads more compactly.
- **Aggregates:** rdflib adds a synthetic `SAMPLE` per `GROUP BY` key; those are
  suppressed so only user-written aggregates appear.
- **Parser coverage** differs from RDF4j: some vendor-specific queries
  (Wikidata/Blazegraph extensions) that RDF4j accepts may fail to parse here, and
  vice versa. Use `try_to_mermaid` to skip such queries gracefully.
- **Named graphs (`GRAPH`)** — a port addition for multi-graph queries — render
  as titled subgraph boxes (see the [multi-graph example](#example-a-multi-graph-federated-query)).
  Constants are scoped per box, so a reference IRI shared across `GRAPH` blocks is
  drawn once inside each (a single node cannot span two Mermaid subgraphs);
  variables stay shared, so a variable joining two graphs stays one node with
  edges crossing the box boundaries.

See [`docs/PORTING_NOTES.md`](docs/PORTING_NOTES.md) for the full Java→Python
module map and the design decisions behind the port.

## Tests

```bash
uv run pytest
```

The suite ports the Java unit-test fixtures (as raw query strings) and adds a
structural marker check for each SPARQL feature.

## License

This project's own code is released under the [BSD 3-Clause License](LICENSE)
(© Structural Bioinformatics Laboratory).

The SPARQL→Mermaid rendering logic is a port of the `mermaid` package of
[`sparql-examples-utils`](https://github.com/sib-swiss/sparql-examples-utils),
which is distributed under the MIT License (© 2024 SIB Swiss Institute of
Bioinformatics). That upstream copyright and permission notice is retained in
the [NOTICE](NOTICE) file, as the MIT License requires.

## Citation & acknowledgments

This work would not exist without the
[`sparql-examples-utils`](https://github.com/sib-swiss/sparql-examples-utils)
project by the SIB Swiss Institute of Bioinformatics — its `mermaid` converter
is the original this port faithfully reproduces. If you use `sparql-to-mermaid`,
please also cite the upstream work:

> Bolleman J., Emonet V., Altenhoff A., *et al.* *A large collection of
> bioinformatics question-query pairs over federated knowledge graphs:
> methodology and applications.* GigaScience, 2024.
> doi:[10.1093/gigascience/giaf045](https://doi.org/10.1093/gigascience/giaf045)

A [`CITATION.cff`](CITATION.cff) is provided for GitHub's "Cite this repository"
feature; it references both this software and the paper above.
