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
from argparse import Namespace
from functools import wraps
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple, Union

import entrypoints
from omero.cli import BaseControl, Parser, ProxyStringType
from omero.gateway import BlitzGateway, BlitzObjectWrapper
from omero.model import Dataset, Image, IObject, Plate, Project, Screen
from omero.sys import ParametersI
from omero_marshal import get_encoder
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF

HELP = """A plugin for exporting rdf from OMERO

omero-rdf creates a stream of RDF triples from the starting object that
it is given. This may be one of: Image, Dataset, Project, Plate, and Screen.

Examples:

    omero rdf Image:123

"""

# TYPE DEFINITIONS

Data = Dict[str, Any]
Subj = Union[BNode, URIRef]
Obj = Union[BNode, Literal, URIRef]
Triple = Tuple[Subj, URIRef, Obj]
Handlers = List[Callable[[URIRef, URIRef, Data], Generator[Triple, None, bool]]]


def gateway_required(func: Callable) -> Callable:  # type: ignore
    """
    Decorator which initializes a client (self.client),
    a BlitzGateway (self.gateway), and makes sure that
    all services of the Blitzgateway are closed again.

    FIXME: copied from omero-cli-render. move upstream
    """

    @wraps(func)
    def _wrapper(self, *args: Any, **kwargs: Any):  # type: ignore
        self.client = self.ctx.conn(*args)
        self.gateway = BlitzGateway(client_obj=self.client)

        try:
            return func(self, *args, **kwargs)
        finally:
            if self.gateway is not None:
                self.gateway.close(hard=False)
                self.gateway = None
                self.client = None

    return _wrapper


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
        pretty_print=False,
        trim_whitespace=False,
        use_ellide=False,
    ) -> None:
        self.gateway = gateway
        self.cache: Set[URIRef] = set()
        self.bnode = 0
        self.pretty_print = pretty_print
        self.trim_whitespace = trim_whitespace
        self.use_ellide = use_ellide
        self.annotation_handlers = self.load_handlers()
        self.info = self.load_server()

        if self.pretty_print:
            self.graph = Graph()
            self.graph.bind("wd", "http://www.wikidata.org/prop/direct/")
            self.graph.bind(
                "ome", "http://www.openmicroscopy.org/rdf/2016-06/ome_core/"
            )
            self.graph.bind(
                "ome-xml", "http://www.openmicroscopy.org/Schemas/OME/2016-06#"
            )  # FIXME
            self.graph.bind("omero", "http://www.openmicroscopy.org/TBD/omero/")
            # self.graph.bind("xs", XMLSCHEMA)
            # TODO: Allow handlers to register namespaces

    def load_handlers(self) -> Handlers:
        annotation_handlers: Handlers = []
        for ep in entrypoints.get_group_all("omero_rdf.annotation_handler"):
            ah_loader = ep.load()
            annotation_handlers.append(ah_loader(self))
        # We know there are some built in handlers
        assert len(annotation_handlers) >= 1
        return annotation_handlers

    def load_server(self) -> Any:
        # Attempt to auto-detect server
        comm = self.gateway.c.getCommunicator()
        return self.gateway.c.getRouter(comm).ice_getEndpoints()[0].getInfo()

    def get_identity(self, _type: str, _id: Any) -> URIRef:
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
        c = self.get_class(o)
        encoder = get_encoder(c)
        if encoder is None:
            raise Exception(f"unknown: {c}")
        else:
            data = encoder.encode(o)
            return self.handle(data)

    def handle(self, data: Data) -> URIRef:
        """
        Parses the data object into RDF triples.

        Returns the id for the data object itself
        """
        # TODO: Add quad representation as an option
        output: Triple

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

    def emit(self, triple: Triple):
        if self.pretty_print:
            self.graph.add(triple)
        else:
            # Streaming
            s, p, o = triple
            print(f"""{s.n3()}\t{p.n3()}\t{o.n3()} .""")

    def close(self):
        if self.pretty_print:
            print(self.graph.serialize())

    def rdf(
        self,
        _id: Subj,
        data: Data,
    ) -> Generator[Triple, None, None]:

        _type = self.get_type(data)

        # Temporary workaround while deciding how to pass annotations
        if "Annotation" in str(_type):
            for ah in self.annotation_handlers:
                handled = yield from ah(
                    None,
                    None,
                    data,
                )
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


class RdfControl(BaseControl):
    def _configure(self, parser: Parser) -> None:
        parser.add_login_arguments()
        rdf_type = ProxyStringType("Image")
        rdf_help = "Object to be exported to RDF"
        parser.add_argument("target", type=rdf_type, nargs="+", help=rdf_help)
        parser.add_argument(
            "--pretty",
            action="store_true",
            default=False,
            help="Print in NT, prevents streaming",
        )
        parser.add_argument(
            "--ellide", action="store_true", default=False, help="Shorten strings"
        )
        parser.add_argument(
            "--trim-whitespace",
            action="store_true",
            default=False,
            help="Remove leading and trailing whitespace from literals",
        )
        parser.set_defaults(func=self.action)

    @gateway_required
    def action(self, args: Namespace) -> None:
        handler = Handler(
            self.gateway,
            pretty_print=args.pretty,
            use_ellide=args.ellide,
            trim_whitespace=args.trim_whitespace,
        )
        self.descend(self.gateway, args.target, handler)
        handler.close()

    # TODO: move to handler?
    def descend(
        self,
        gateway: BlitzGateway,
        target: IObject,
        handler: Handler,
    ) -> URIRef:
        """
        Copied from omero-cli-render. Should be moved upstream
        """

        if isinstance(target, list):
            return([self.descend(gateway, t, handler) for t in target])

        elif isinstance(target, Screen):
            scr = self._lookup(gateway, "Screen", target.id)
            scrid = handler(scr)
            for plate in scr.listChildren():
                pltid = self.descend(gateway, plate._obj, handler)
                handler.emit((pltid, DCTERMS.isPartOf, scrid))
                handler.emit((scrid, DCTERMS.hasPart, pltid))
            for annotation in scr.listAnnotations(None):
                annid = handler(annotation)
                handler.emit((annid, DCTERMS.isPartOf, scrid))
            return scrid

        elif isinstance(target, Plate):
            plt = self._lookup(gateway, "Plate", target.id)
            pltid = handler(plt)
            for annotation in plt.listAnnotations(None):
                annid = handler(annotation)
                handler.emit((annid, DCTERMS.isPartOf, pltid))
            for well in plt.listChildren():
                wid = handler(well)  # No descend
                handler.emit((wid, DCTERMS.isPartOf, pltid))
                for idx in range(0, well.countWellSample()):
                    img = well.getImage(idx)
                    imgid = self.descend(gateway, img._obj, handler)
                    handler.emit((imgid, DCTERMS.isPartOf, wid))
                    handler.emit((wid, DCTERMS.hasPart, imgid))
            return pltid

        elif isinstance(target, Project):
            prj = self._lookup(gateway, "Project", target.id)
            prjid = handler(prj)
            for annotation in prj.listAnnotations(None):
                annid = handler(annotation)
                handler.emit((annid, DCTERMS.isPartOf, prjid))
            for ds in prj.listChildren():
                dsid = self.descend(gateway, ds._obj, handler)
                handler.emit((dsid, DCTERMS.isPartOf, prjid))
                handler.emit((prjid, DCTERMS.hasPart, dsid))
            return prjid

        elif isinstance(target, Dataset):
            ds = self._lookup(gateway, "Dataset", target.id)
            dsid = handler(ds)
            for annotation in ds.listAnnotations(None):
                annid = handler(annotation)
                handler.emit((annid, DCTERMS.isPartOf, dsid))
            for img in ds.listChildren():
                imgid = self.descend(gateway, img._obj, handler)
                handler.emit((imgid, DCTERMS.isPartOf, dsid))
                handler.emit((dsid, DCTERMS.hasPart, imgid))
            return dsid

        elif isinstance(target, Image):
            img = self._lookup(gateway, "Image", target.id)
            imgid = handler(img)
            pixid = handler(img.getPrimaryPixels())
            handler.emit((pixid, DCTERMS.isPartOf, imgid))
            handler.emit((imgid, DCTERMS.hasPart, pixid))
            for annotation in img.listAnnotations(None):
                img._loadAnnotationLinks()
                annid = handler(annotation)
                handler.emit((annid, DCTERMS.isPartOf, imgid))
            for roi in self._get_rois(gateway, img):
                handler(roi)
            return imgid

        else:
            self.ctx.die(111, "unknown target: %s" % target.__class__.__name__)

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
            self.ctx.die(110, f"No such {_type}: {oid}")
        return obj
