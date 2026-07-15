"""Curated fallback prefixes for common life-science / semantic-web IRIs.

These are used only to shorten IRIs that a query did not itself declare a
``PREFIX`` for. A query's own declarations (and any caller-supplied prefixes)
always take precedence, so this never overrides what the author intended.

Ordering: the longest matching namespace wins, so an OBO id shortens to its
conventional CURIE (``MONDO:0005148``) rather than the generic ``obo:MONDO_…``.
"""

from __future__ import annotations

WELL_KNOWN_PREFIXES: dict[str, str] = {
    # --- core semantic web ---------------------------------------------- #
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "prov": "http://www.w3.org/ns/prov#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "schema": "https://schema.org/",
    # --- OBO family: specific id spaces (longest match -> nice CURIEs) --- #
    "obo": "http://purl.obolibrary.org/obo/",
    "MONDO": "http://purl.obolibrary.org/obo/MONDO_",
    "DOID": "http://purl.obolibrary.org/obo/DOID_",
    "CHEBI": "http://purl.obolibrary.org/obo/CHEBI_",
    "GO": "http://purl.obolibrary.org/obo/GO_",
    "HP": "http://purl.obolibrary.org/obo/HP_",
    "NCIT": "http://purl.obolibrary.org/obo/NCIT_",
    "UBERON": "http://purl.obolibrary.org/obo/UBERON_",
    "CL": "http://purl.obolibrary.org/obo/CL_",
    "PR": "http://purl.obolibrary.org/obo/PR_",
    "SO": "http://purl.obolibrary.org/obo/SO_",
    "OBI": "http://purl.obolibrary.org/obo/OBI_",
    "RO": "http://purl.obolibrary.org/obo/RO_",
    "oboInOwl": "http://www.geneontology.org/formats/oboInOwl#",
    # --- other life-science vocabularies -------------------------------- #
    "up": "http://purl.uniprot.org/core/",
    "uniprotkb": "http://purl.uniprot.org/uniprot/",
    "taxon": "http://purl.uniprot.org/taxonomy/",
    "efo": "http://www.ebi.ac.uk/efo/EFO_",
    "sio": "http://semanticscience.org/resource/SIO_",
    "edam": "http://edamontology.org/",
    "bao": "http://www.bioassayontology.org/bao#BAO_",
    "biolink": "https://w3id.org/biolink/vocab/",
    "wikidata": "http://www.wikidata.org/entity/",
    "wdt": "http://www.wikidata.org/prop/direct/",
}
