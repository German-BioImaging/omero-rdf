#!/usr/bin/env python

#
# Copyright (c) 2022 - 2026 German BioImaging
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""RDF serialization formats used by omero-rdf.

References:
- N-Triples: https://www.w3.org/TR/n-triples/
- Turtle: https://www.w3.org/TR/turtle/
- JSON-LD: https://www.w3.org/TR/json-ld11/
- RO-Crate: https://www.researchobject.org/ro-crate/
"""

from pyld import jsonld
from rdflib import Graph
from rdflib_pyld_compat import pyld_jsonld_from_rdflib_graph
import json


class Format:
    """
    Output mechanisms split into two types: streaming and non-streaming.
    Critical methods include:

        - streaming:
            - serialize_triple: return a representation of the triple
        - non-streaming:
            - add: store a triple for later serialization
            - serialize_graph: return a representation of the graph

    See the subclasses for more information.
    """

    def __init__(self):
        self.streaming = None

    def __str__(self):
        return self.__class__.__name__[:-6].lower()

    def __lt__(self, other):
        return str(self) < str(other)

    def add(self, triple):
        raise NotImplementedError()

    def serialize_triple(self, triple):
        raise NotImplementedError()

    def serialize_graph(self):
        raise NotImplementedError()


class StreamingFormat(Format):
    def __init__(self):
        super().__init__()
        self.streaming = True

    def add(self, triple):
        raise RuntimeError("adding not supported during streaming")

    def serialize_graph(self):
        raise RuntimeError("graph serialization not supported during streaming")


class NTriplesFormat(StreamingFormat):
    def __init__(self):
        super().__init__()

    def serialize_triple(self, triple):
        s, p, o = triple
        escaped = o.n3().encode("unicode_escape").decode("utf-8")
        return f"""{s.n3()}\t{p.n3()}\t{escaped} ."""


class NonStreamingFormat(Format):
    def __init__(self):
        super().__init__()
        self.streaming = False
        self.graph = Graph()
        self.graph.bind("wd", "http://www.wikidata.org/prop/direct/")
        self.graph.bind("ome", "http://www.openmicroscopy.org/rdf/2016-06/ome_core/")
        self.graph.bind(
            "ome-xml", "http://www.openmicroscopy.org/Schemas/OME/2016-06#"
        )  # FIXME
        self.graph.bind("omero", "http://www.openmicroscopy.org/TBD/omero/")
        # self.graph.bind("xs", XMLSCHEMA)
        # TODO: Allow handlers to register namespaces

    def add(self, triple):
        self.graph.add(triple)

    def serialize_triple(self, triple):
        raise RuntimeError("triple serialization not supported during streaming")


class TurtleFormat(NonStreamingFormat):
    def __init__(self):
        super().__init__()

    def serialize_graph(self) -> None:
        return self.graph.serialize()


class JSONLDFormat(NonStreamingFormat):
    def __init__(self):
        super().__init__()

    def context(self):
        # TODO: allow handlers to add to this
        return {
            "@wd": "http://www.wikidata.org/prop/direct/",
            "@ome": "http://www.openmicroscopy.org/rdf/2016-06/ome_core/",
            "@ome-xml": "http://www.openmicroscopy.org/Schemas/OME/2016-06#",
            "@omero": "http://www.openmicroscopy.org/TBD/omero/",
            "@idr": "https://idr.openmicroscopy.org/",
        }

    def serialize_graph(self) -> None:
        return self.graph.serialize(
            format="json-ld",
            context=self.context(),
            indent=4,
        )


class ROCrateFormat(JSONLDFormat):
    def __init__(self):
        super().__init__()

    def context(self):
        ctx = super().context()
        ctx["@rocrate"] = "https://w3id.org/ro/crate/1.1/context"
        return ctx

    def serialize_graph(self):
        ctx = self.context()
        j = pyld_jsonld_from_rdflib_graph(self.graph)
        j = jsonld.flatten(j, ctx)
        j = jsonld.compact(j, ctx)
        if "@graph" not in j:
            raise Exception(j)
        j["@graph"][0:0] = [
            {
                "@id": "./",
                "@type": "Dataset",
                "rocrate:license": "https://creativecommons.org/licenses/by/4.0/",
            },
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "rocrate:conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                "rocrate:about": {"@id": "./"},
            },
        ]
        return json.dumps(j, indent=4)


def format_mapping():
    return {
        "ntriples": NTriplesFormat(),
        "jsonld": JSONLDFormat(),
        "turtle": TurtleFormat(),
        "ro-crate": ROCrateFormat(),
    }


def format_list():
    return format_mapping().keys()
