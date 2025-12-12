from omero.gateway import BlitzGateway
from rdflib import Literal, URIRef

from omero_rdf import Triplyfier


def test_rdf_library_returns_expected_triples():
    with BlitzGateway(
        username="public",
        passwd="public",
        host="idr.openmicroscopy.org",
        port="4064",
        secure=True,
    ) as conn:
        lib = Triplyfier(conn)
        g = lib.export_graph(output="rdflib", target="Image:14000745")

    sample_expected_triples = [
        (
            URIRef("https://idr.openmicroscopy.org/Image/14000745"),
            URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            URIRef("http://www.openmicroscopy.org/Schemas/OME/2016-06#Image"),
        ),
        (
            URIRef("https://idr.openmicroscopy.org/Pixels/14000745"),
            URIRef("http://purl.org/dc/terms/isPartOf"),
            URIRef("https://idr.openmicroscopy.org/Image/14000745"),
        ),
        (
            URIRef("https://idr.openmicroscopy.org/Pixels/14000745"),
            URIRef("http://www.openmicroscopy.org/rdf/2016-06/ome_core/SizeY"),
            Literal(
                "34673",
                datatype=URIRef("http://www.w3.org/2001/XMLSchema#integer"),
            ),
        ),
    ]

    for triple in sample_expected_triples:
        assert triple in g, f"Missing triple: {triple}"
