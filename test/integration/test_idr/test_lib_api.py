from omero.gateway import BlitzGateway

from omero_rdf import RdfLibrary
from rdflib import Graph

with BlitzGateway(
    username="public",
    passwd="public",
    host="idr.openmicroscopy.org",
    port="4064",
    secure=True,
) as conn:
    lib = RdfLibrary(conn)
    args = {"target": "Image:123"}

    g = lib.action(**args, output="rdflib")

    for triple in sorted(g):
        print(triple)
