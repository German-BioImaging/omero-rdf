import logging

from omero.gateway import BlitzGateway
from rdflib import Literal, URIRef

from omero_rdf import Triplyfier

# Basic logging to terminal
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_rdf_library_returns_expected_triples():
    logger.info("Preparing to connect to IDR server")

    with BlitzGateway(
        username="public",
        passwd="public",
        host="idr.openmicroscopy.org",
        port="4064",
        secure=True,
    ) as conn:
        logger.info("Connected to IDR, creating Triplyfier")
        lib = Triplyfier(conn)
        target = "Image:14000745"
        logger.info("Exporting graph for target: %s", target)
        g = lib.export_graph(output="rdflib", target=target)
        logger.info("Exported graph contains %d triples", len(g))

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
        if triple not in g:
            logger.error("Missing triple: %s", triple)
        assert triple in g, f"Missing triple: {triple}"
