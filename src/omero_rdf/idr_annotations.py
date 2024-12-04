#!/usr/bin/env python

#
# Copyright (c) 2022 German BioImaging
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

import logging
from typing import Any, Dict, Generator

from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.namespace import DC, RDF
from wikidataintegrator import wdi_core

from . import Data, Handler, Triple

HPAS = Namespace("http://www.proteinatlas.org/search/")
OMERO = Namespace("https://idr.openmicroscopy.org/webclient/img_detail/")
WD = Namespace("http://www.wikidata.org/entity/")
WDP = Namespace("http://www.wikidata.org/prop/direct/")


class IDRAnnotationHandler:
    """
    This method parses known IDR annotation namespaces into a more
    searchable format, rather than bnodes with "Key" and "Name" properties.
    """

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.wikidata: Dict[Any, URIRef] = {}

    def __call__(
        self, container: URIRef, pred: URIRef, data: Data
    ) -> Generator[Triple, None, bool]:

        ns = data.get("Namespace")
        logging.debug("# handling %s", ns)

        _type = data.get("@type")
        _id = data.get("@id")

        # Workaround matched with change in the main handler
        if _type is None or "MapAnnotation" not in _type:
            logging.debug("# skipping non-map: %s", _type)
            return False
        # End workaround

        if _id is None:
            thing = BNode()
        else:
            thing = self.handler.get_identity("MapAnnotation", data.get("@id"))

        if container is not None:
            yield (
                container,
                WDP.P180,
                thing,
            )  # Container depicts thing described in annotation

        yield (thing, RDF.type, WD.Q35120)  # Q35120 = THING

        kvps = data.get("Value", [])

        for name, value in kvps:

            cached = self.wikidata.get(value)

            if name == "Organism":
                if cached is not None:
                    yield (thing, WDP.P703, cached)  # taxa -> Wikidata
                else:
                    query = f"""
                    SELECT * WHERE {{
                    ?taxon wdt:P225 "{value}"
                    }}
                    """
                    result = wdi_core.WDFunctionsEngine.execute_sparql_query(query)
                    if len(result["results"]["bindings"]) > 0:
                        cached = URIRef(
                            result["results"]["bindings"][0]["taxon"]["value"]
                        )
                        self.wikidata[value] = cached
                    else:
                        logging.warning("# missing %s in wikidata", value)
                    yield (thing, WDP.P703, cached)

            elif name == "Pathology Identifier":
                yield (
                    thing,
                    WDP.P1050,
                    URIRef("http://purl.bioontology.org/ontology/SNMI/" + value),
                )

            elif name == "Pathology":

                # Fix a typo
                if value == "Carcinoma, endometroid":
                    value = "Carcinoma, endometrioid"

                # list for curation
                tocurate = [
                    "Malignant lymphoma, non-Hodgkin's type, Low grade",
                    "Malignant melanoma, NOS"  # isn't melanoma malignant by default?
                    "Malignant melanoma, Metastatic site",
                    "Malignant melanoma, NOS",
                    "Malignant melanoma, Metastatic site",
                    "Adenocarcinoma, Low grade",
                    "Carcinoid, malignant, NOS",
                    "Normal tissue, NOS",
                ]

                if value in tocurate:
                    continue

                if cached is not None:
                    yield (
                        thing,
                        WDP.P1050,
                        cached,
                    )  # P1050 = medical condition in Wikidata

                else:
                    query = f"""

                    SELECT * WHERE {{
                    VALUES ?pathology {{wd:Q12136}}
                    {{?disease  wdt:P31 ?pathology .}}
                        UNION
                        {{?disease  wdt:P279 ?pathology .}}
                        UNION
                        {{?disease  wdt:P279/wdt:P31 ?pathology .}}
                        UNION
                        {{?disease  wdt:P279+ ?pathology .}}
                    {{?disease rdfs:label "{value.lower()}"@en}}
                    UNION
                    {{?disease skos:altLabel "{value.lower()}"@en}}
                    }}
                    """
                    result = wdi_core.WDFunctionsEngine.execute_sparql_query(query)
                    if len(result["results"]["bindings"]) > 0:
                        cached = URIRef(
                            result["results"]["bindings"][0]["disease"]["value"]
                        )
                        self.wikidata[value] = cached
                    else:
                        logging.warning("missing %s in wikidata", value)
                    yield (thing, WDP.P827, cached)  # FIXIE P1080?

            elif name == "Organism Part Identifier":
                yield (
                    thing,
                    WDP.P361,
                    URIRef("http://purl.bioontology.org/ontology/SNMI/" + value),
                )  # P361 part of

            elif name == "Organism Part":
                if cached is not None:
                    yield (thing, WDP.P361, cached)  # P361 is part of

                else:
                    query = f"""

                    SELECT * WHERE {{
                    VALUES ?organ {{wd:Q103812529 wd:Q4936952 wd:Q712378
                                    wd:Q24060765 wd:Q103843025 wd:Q27162596}}
                    {{?anatomical_structure  wdt:P31 ?organ .}}
                        UNION
                        {{?anatomical_structure  wdt:P279 ?organ .}}
                        UNION
                        {{?anatomical_structure  wdt:P279/wdt:P31 ?organ .}}
                        UNION
                        {{?anatomical_structure  wdt:P279+ ?organ .}}
                    {{?anatomical_structure rdfs:label "{value.lower()}"@en}}
                    UNION
                    {{?anatomical_structure skos:altLabel "{value.lower()}"@en}}
                    }}
                    """
                    result = wdi_core.WDFunctionsEngine.execute_sparql_query(query)
                    if len(result["results"]["bindings"]) > 0:
                        cached = URIRef(
                            result["results"]["bindings"][0]["anatomical_structure"][
                                "value"
                            ]
                        )
                        self.wikidata[value] = cached
                    else:
                        logging.warning("missing %s in wikidata", value)
                    yield (thing, WDP.P827, cached)

            elif name == "Sex":
                if value == "Female":
                    yield (thing, WDP.P21, WD.Q6581072)
                elif value == "Male":
                    yield (thing, WDP.P21, WD.Q6581097)
                else:
                    logging.warning("unmapped sex value: %s", value)

            elif name == "Age":
                yield (thing, WDP.P3629, Literal(value))

            elif name == "Antibody Identifier URL":
                yield (thing, DC.identifier, URIRef(value))

            elif name == "Gene Symbol":
                yield (thing, WDP.P353, Literal(value))  # as1Gsumes homo sapiens

            elif name == "Gene Identifier URL":
                yield (thing, DC.identifier, URIRef(value))

            else:
                logging.warning("# unknown key: %s", name)

        return True
