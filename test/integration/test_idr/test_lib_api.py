from omero.gateway import BlitzGateway

from omero_rdf import RdfLibrary

with BlitzGateway(
    username="public",
    passwd="public",
    host="idr.openmicroscopy.org",
    port="4064",
    secure=True,
) as conn:
    lib = RdfLibrary(conn)
    args = {"target": "Image:14000745"}

    g = lib.action(output="rdflib", **args)

    # Check if first triple is <https://idr.openmicroscopy.org/Image/14000745> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>       <http://www.openmicroscopy.org/Schemas/OME/2016-06#Image>
    for triple in sorted(g):
        print(triple)
