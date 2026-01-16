#!/usr/bin/env python

#
# Copyright (c) 2022 - 2025 German BioImaging
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

"""Traversal and RDF triple generation for OMERO objects.

Annotation handler plugins can be registered via the
"omero_rdf.annotation_handler" entry-point group.
"""

import sys
import logging
from typing import Any, Generator, Optional, Set

from importlib.metadata import entry_points
from omero.gateway import BlitzGateway, BlitzObjectWrapper
from omero_marshal import get_encoder
from omero.model import Dataset, Image, IObject, Plate, Project, Screen
from omero.sys import ParametersI

from rdflib import BNode, Literal, URIRef


from rdflib.namespace import DCTERMS, RDF

from omero_rdf.utils import Handlers, Data, Triple, Subj
from omero_rdf.formats import Format


class HandlerError(Exception):
    """
    Raised when Handler encounters an unrecoverable condition.
    Carries an exit-status-like code for the caller to interpret.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class Handler:
    """
    Instances are used to generate triples.

    Methods which can be subclassed:
        TBD

    """

    OME = "http://www.openmicroscopy.org/rdf/2016-06/ome_core/"
    OMERO = "http://www.openmicroscopy.org/TBD/omero/"

    def __init__(
        self,
        gateway: BlitzGateway,
        formatter: Format,
        trim_whitespace=False,
        use_ellide=False,
        first_handler_wins=False,
        descent="recursive",
        filehandle=sys.stdout,
    ) -> None:
        self.gateway = gateway
        self.cache: Set[URIRef] = set()
        self.bnode = 0
        self.formatter = formatter
        self.trim_whitespace = trim_whitespace
        self.use_ellide = use_ellide
        self.first_handler_wins = first_handler_wins
        self.descent = descent
        self._descent_level = 0
        self.annotation_handlers = self.load_handlers()
        self.info = self.load_server()
        self.filehandle = filehandle

    def skip_descent(self):
        return self.descent != "recursive" and self._descent_level > 0

    def descending(self):
        self._descent_level += 1

    def load_handlers(self) -> Handlers:
        """Load annotation handlers from entry points."""
        annotation_handlers: Handlers = []
        eps = entry_points()

        # Extensions to OMERO rdf can provide custom annotation handling.
        # They can be accessed through entry points.
        # See https://github.com/German-BioImaging/omero-rdf-wikidata/

        # Python 3.10 deprecated eps.get(), changing to eps.select()
        for ep in eps.select(group="omero_rdf.annotation_handler"):
            ah_loader = ep.load()
            annotation_handlers.append(ah_loader(self))
        return annotation_handlers

    def load_server(self) -> Any:
        """Detect server connection info used for URI construction."""
        # Attempt to auto-detect server
        comm = self.gateway.c.getCommunicator()
        return self.gateway.c.getRouter(comm).ice_getEndpoints()[0].getInfo()

    def get_identity(self, _type: str, _id: Any) -> URIRef:
        """Return the subject URI for a given OMERO type and id."""
        if _type.endswith("I") and _type != ("ROI"):
            _type = _type[0:-1]
        return URIRef(f"https://{self.info.host}/{_type}/{_id}")

    def get_bnode(self) -> BNode:
        try:
            return BNode()
            # return f":b{self.bnode}"
        finally:
            self.bnode += 1

    def get_key(self, key: str) -> Optional[URIRef]:
        if key in ("@type", "@id", "omero:details", "Annotations"):
            # Types that we want to omit fo
            return None
        else:
            if key.startswith("omero:"):
                return URIRef(f"{self.OMERO}{key[6:]}")
            else:
                return URIRef(f"{self.OME}{key}")

    def get_type(self, data: Data) -> str:
        return data.get("@type", "UNKNOWN").split("#")[-1]

    def literal(self, v: Any) -> Literal:
        """
        Prepare Python objects for use as literals
        """
        if isinstance(v, str):
            v = str(v)
            if self.use_ellide and len(v) > 50:
                v = f"{v[0:24]}...{v[-20:-1]}"
            elif v.startswith(" ") or v.endswith(" "):
                if self.trim_whitespace:
                    v = v.strip()
                else:
                    logging.warning(
                        "string has whitespace that needs trimming: '%s'", v
                    )
        return Literal(v)

    def get_class(self, o):
        if isinstance(o, IObject):
            c = o.__class__
        else:  # Wrapper
            c = o._obj.__class__
        return c

    def __call__(self, o: BlitzObjectWrapper) -> URIRef:
        """Encode an OMERO object and emit RDF, returning its subject URI."""
        c = self.get_class(o)
        encoder = get_encoder(c)
        if encoder is None:
            raise Exception(f"unknown: {c}")
        else:
            data = encoder.encode(o)
            return self.handle(data)

    def annotations(self, obj, objid):
        """
        Loop through all annotations and handle them individually.
        """
        if isinstance(obj, IObject):
            # Not a wrapper object
            for annotation in obj.linkedAnnotationList():
                annid = self(annotation)
                self.contains(objid, annid)
        else:
            for annotation in obj.listAnnotations(None):
                obj._loadAnnotationLinks()
                annid = self(annotation)
                self.contains(objid, annid)

    def handle(self, data: Data) -> URIRef:
        """
        Parses the data object into RDF triples.

        Returns the id for the data object itself
        """
        # TODO: Add quad representation as an option

        str_id = data.get("@id")
        if not str_id:
            raise Exception(f"missing id: {data}")

        # TODO: this call is likely redundant
        _type = self.get_type(data)
        _id = self.get_identity(_type, str_id)

        for triple in self.rdf(_id, data):
            if triple:
                if None in triple:
                    logging.debug("skipping None value: %s %s %s", triple)
                else:
                    self.emit(triple)

        return _id

    def contains(self, parent, child):
        """
        Use emit to generate isPartOf and hasPart triples

        TODO: add an option to only choose one of the two directions.
        """
        self.emit((child, DCTERMS.isPartOf, parent))
        self.emit((parent, DCTERMS.hasPart, child))

    def emit(self, triple: Triple):
        if self.formatter.streaming:
            print(self.formatter.serialize_triple(triple), file=self.filehandle)
        else:
            self.formatter.add(triple)

    def close(self):
        if not self.formatter.streaming:
            serialized_graph = self.formatter.serialize_graph()
            print(serialized_graph, file=self.filehandle)

    def rdf(
        self,
        _id: Subj,
        data: Data,
    ) -> Generator[Triple, None, None]:
        """Yield RDF triples for an encoded object, including annotations."""
        _type = self.get_type(data)

        # Temporary workaround while deciding how to pass annotations
        if "Annotation" in str(_type):
            for ah in self.annotation_handlers:
                handled = yield from ah(
                    None,
                    None,
                    data,
                )
                if self.first_handler_wins and handled:
                    return
        # End workaround

        if _id in self.cache:
            logging.debug("# skipping previously seen %s", _id)
            return
        else:
            self.cache.add(_id)

        for k, v in sorted(data.items()):
            if k == "@type":
                yield (_id, RDF.type, URIRef(v))
            elif k in ("@id", "omero:details", "Annotations"):
                # Types that we want to omit for now
                pass
            else:
                if k.startswith("omero:"):
                    key = URIRef(f"{self.OMERO}{k[6:]}")
                else:
                    key = URIRef(f"{self.OME}{k}")

                if isinstance(v, dict):
                    # This is an object
                    if "@id" in v:
                        yield from self.yield_object_with_id(_id, key, v)
                    else:
                        # Without an identity, use a bnode
                        # TODO: store by value for re-use?
                        bnode = self.get_bnode()
                        yield (_id, key, bnode)
                        yield from self.rdf(bnode, v)

                elif isinstance(v, list):
                    # This is likely the [[key, value], ...] structure?
                    # can also be shapes
                    for item in v:
                        if isinstance(item, dict) and "@id" in item:
                            yield from self.yield_object_with_id(_id, key, item)
                        elif isinstance(item, list) and len(item) == 2:
                            bnode = self.get_bnode()
                            # TODO: KVPs need ordering info, also no use of "key" here.
                            yield (_id, URIRef(f"{self.OME}Map"), bnode)
                            yield (
                                bnode,
                                URIRef(f"{self.OME}Key"),
                                self.literal(item[0]),
                            )
                            yield (
                                bnode,
                                URIRef(f"{self.OME}Value"),
                                self.literal(item[1]),
                            )
                        else:
                            raise Exception(f"unknown list item: {item}")
                else:
                    yield (_id, key, self.literal(v))

        # Special handling for Annotations
        annotations = data.get("Annotations", [])
        for annotation in annotations:
            handled = False
            for ah in self.annotation_handlers:
                handled = yield from ah(
                    _id, URIRef(f"{self.OME}annotation"), annotation
                )
                if handled:
                    break

            if not handled:  # TODO: could move to a default handler
                aid = self.get_identity("AnnotationTBD", annotation["@id"])
                yield (_id, URIRef(f"{self.OME}annotation"), aid)
                yield from self.rdf(aid, annotation)

    def yield_object_with_id(self, _id, key, v):
        """
        Yields a link to the object as well as its representation.
        """
        v_type = self.get_type(v)
        val = self.get_identity(v_type, v["@id"])
        yield (_id, key, val)
        yield from self.rdf(_id, v)

    def _get_rois(self, gateway, img):
        params = ParametersI()
        params.addId(img.id)
        query = """select r from Roi r
                left outer join fetch r.annotationLinks as ral
                left outer join fetch ral.child as rann
                left outer join fetch r.shapes as s
                left outer join fetch s.annotationLinks as sal
                left outer join fetch sal.child as sann
                     where r.image.id = :id"""
        return gateway.getQueryService().findAllByQuery(
            query, params, {"omero.group": str(img.details.group.id.val)}
        )

    def _lookup(
        self, gateway: BlitzGateway, _type: str, oid: int
    ) -> BlitzObjectWrapper:
        # TODO: move _lookup to a _configure type
        gateway.SERVICE_OPTS.setOmeroGroup("-1")
        obj = gateway.getObject(_type, oid)
        if not obj:
            raise HandlerError(110, f"No such {_type}: {oid}")
        return obj

    def descend(
        self,
        gateway: BlitzGateway,
        target: IObject,
    ) -> URIRef:
        """
        Copied from omero-cli-render. Should be moved upstream
        """

        if isinstance(target, list):
            return [self.descend(gateway, t) for t in target]

        # "descent" doesn't apply to a list
        if self.skip_descent():
            objid = self(target)
            logging.debug("skip descent: %s", objid)
            return objid
        else:
            self.descending()

        if isinstance(target, Screen):
            scr = self._lookup(gateway, "Screen", target.id)
            scrid = self(scr)
            for plate in scr.listChildren():
                pltid = self.descend(gateway, plate._obj)
                self.contains(scrid, pltid)
            self.annotations(scr, scrid)
            return scrid

        elif isinstance(target, Plate):
            plt = self._lookup(gateway, "Plate", target.id)
            pltid = self(plt)
            self.annotations(plt, pltid)
            for well in plt.listChildren():
                wid = self(well)  # No descend
                self.contains(pltid, wid)
                for idx in range(0, well.countWellSample()):
                    img = well.getImage(idx)
                    imgid = self.descend(gateway, img._obj)
                    self.contains(wid, imgid)
            return pltid

        elif isinstance(target, Project):
            prj = self._lookup(gateway, "Project", target.id)
            prjid = self(prj)
            self.annotations(prj, prjid)
            for ds in prj.listChildren():
                dsid = self.descend(gateway, ds._obj)
                self.contains(prjid, dsid)
            return prjid

        elif isinstance(target, Dataset):
            ds = self._lookup(gateway, "Dataset", target.id)
            dsid = self(ds)
            self.annotations(ds, dsid)
            for img in ds.listChildren():
                imgid = self.descend(gateway, img._obj)
                self.contains(dsid, imgid)
            return dsid

        elif isinstance(target, Image):
            img = self._lookup(gateway, "Image", target.id)
            imgid = self(img)
            if img.getPrimaryPixels() is not None:
                pixid = self(img.getPrimaryPixels())
                self.contains(imgid, pixid)
            self.annotations(img, imgid)
            for roi in self._get_rois(gateway, img):
                roiid = self(roi)
                self.annotations(roi, roiid)
                self.contains(pixid, roiid)
                for shape in roi.iterateShapes():
                    shapeid = self(shape)
                    self.annotations(shape, shapeid)
                    self.contains(roiid, shapeid)
            return imgid

        else:
            raise HandlerError(111, "unknown target: %s" % target.__class__.__name__)
