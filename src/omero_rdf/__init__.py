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
from omero_marshal import get_encoder
from rdflib import BNode, Literal, URIRef

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

    def __init__(self, gateway: BlitzGateway) -> None:
        self.gateway = gateway
        self.cache: Set[URIRef] = set()
        self.bnode = 0
        self.annotation_handlers: List[
            Callable[[URIRef, URIRef, Data], Generator[Triple, None, bool]]
        ] = []
        for ep in entrypoints.get_group_all("omero_rdf.annotation_handler"):
            ah_loader = ep.load()
            self.annotation_handlers.append(ah_loader(self))
        # We know there are some built in handlers
        assert len(self.annotation_handlers) >= 1

        # Attempt to auto-detect server
        comm = self.gateway.c.getCommunicator()
        self.info = self.gateway.c.getRouter(comm).ice_getEndpoints()[0].getInfo()

    def get_identity(self, _type: str, _id: Any) -> URIRef:
        if _type.endswith("I"):
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

    def ellide(self, v: Any) -> Literal:
        if isinstance(v, str):
            v = str(v)
            if len(v) > 50:
                v = f"{v[0:24]}...{v[-20:-1]}"
        return Literal(v)

    def __call__(self, o: BlitzObjectWrapper) -> None:
        c = o._obj.__class__
        encoder = get_encoder(c)
        if encoder is None:
            raise Exception(f"unknown: {c}")
        else:
            data = encoder.encode(o)
            self.handle(data)

    def handle(self, data: Data) -> None:
        """
        TODO: Add quad representation as an option
        """
        output: Triple
        for output in self.rdf(data):
            if output:
                s, p, o = output
                if None in (s, p, o):
                    logging.debug("skipping None value: %s %s %s", s, p, o)
                else:
                    print(f"""{s.n3()}\t{p.n3()}\t{o.n3()} .""")

    def rdf(
        self, data: Data, _id: Optional[Subj] = None
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

        if not _id:
            str_id = data.get("@id")
            if not str_id:
                raise Exception(f"missing id: {data}")
            _id = self.get_identity(_type, str_id)
            if _id in self.cache:
                logging.debug("# skipping previously seen %s", _id)
                return
            else:
                self.cache.add(_id)

        for k, v in sorted(data.items()):

            if k in ("@type", "@id", "omero:details", "Annotations"):
                # Types that we want to omit fo
                pass
            else:

                if k.startswith("omero:"):
                    key = URIRef(f"{self.OMERO}{k[6:]}")
                else:
                    key = URIRef(f"{self.OME}{k}")

                if isinstance(v, dict):
                    # This is an object
                    if "@id" in v:
                        # With an identity, use a reference
                        v_type = self.get_type(v)
                        val = self.get_identity(v_type, v["@id"])
                        yield (_id, key, val)
                        yield from self.rdf(v)
                    else:
                        # Without an identity, use a bnode
                        # TODO: store by value for re-use?
                        bnode = self.get_bnode()
                        yield (_id, key, bnode)
                        yield from self.rdf(v, _id=bnode)

                elif isinstance(v, list):
                    # This is likely the [[key, value], ...] structure?
                    for item in v:
                        bnode = self.get_bnode()
                        # TODO: KVPs need ordering info
                        yield (_id, URIRef(f"{self.OME}Map"), bnode)
                        yield (bnode, URIRef(f"{self.OME}Key"), self.ellide(item[0]))
                        yield (bnode, URIRef(f"{self.OME}Value"), self.ellide(item[1]))
                else:
                    yield (_id, key, self.ellide(v))  # TODO: Use Literal

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
                yield (
                    _id,
                    URIRef(f"{self.OME}annotation"),
                    self.get_identity("AnnotationTBD", annotation["@id"]),
                )
                yield from self.rdf(annotation)


class RdfControl(BaseControl):
    def _configure(self, parser: Parser) -> None:
        parser.add_login_arguments()
        parser.add_argument(
            "--force",
            "-f",
            default=False,
            action="store_true",
            help="Actually do something. Default: false.",
        )
        parser.add_argument(
            "--block-size",
            "-b",
            default=100,
            action="store_true",
            help="Actually do something. Default: false.",
        )
        rdf_type = ProxyStringType("Image")
        rdf_help = "Object to be exported to RDF"
        parser.add_argument("target", type=rdf_type, help=rdf_help)
        parser.set_defaults(func=self.action)

    @gateway_required
    def action(self, args: Namespace) -> None:
        self.descend(self.gateway, args.target, batch=1)

    def descend(
        self,
        gateway: BlitzGateway,
        target: IObject,
        batch: int = 100,
        handler: Optional[Handler] = None,
    ) -> None:
        """
        Copied from omero-cli-render. Should be moved upstream
        """

        if handler is None:
            handler = Handler(gateway)

        if isinstance(target, list):
            for x in target:
                self.descend(gateway, x, batch)
        elif isinstance(target, Screen):
            scr = self._lookup(gateway, "Screen", target.id)
            handler(scr)
            for plate in scr.listChildren():
                self.descend(gateway, plate._obj, batch)
            for annotation in scr.listAnnotations(None):
                handler(annotation)
        elif isinstance(target, Plate):
            plt = self._lookup(gateway, "Plate", target.id)
            handler(plt)
            for annotation in plt.listAnnotations(None):
                handler(annotation)
            for well in plt.listChildren():
                handler(well)  # No descend
                for idx in range(0, well.countWellSample()):
                    img = well.getImage(idx)
                    handler(img.getPrimaryPixels())
                    handler(img)  # No descend

        elif isinstance(target, Project):
            prj = self._lookup(gateway, "Project", target.id)
            handler(prj)
            for annotation in prj.listAnnotations(None):
                handler(annotation)
            for ds in prj.listChildren():
                self.descend(gateway, ds._obj, batch)

        elif isinstance(target, Dataset):
            ds = self._lookup(gateway, "Dataset", target.id)
            handler(ds)
            for annotation in ds.listAnnotations(None):
                handler(annotation)
            for img in ds.listChildren():
                handler(img)  # No descend
                handler(img.getPrimaryPixels())
                for annotation in img.listAnnotations(None):
                    handler(annotation)

        elif isinstance(target, Image):
            img = self._lookup(gateway, "Image", target.id)
            handler(img)
            handler(img.getPrimaryPixels())
            for annotation in img.listAnnotations(None):
                handler(annotation)

        else:
            self.ctx.die(111, "TBD: %s" % target.__class__.__name__)

    def _lookup(
        self, gateway: BlitzGateway, _type: str, oid: int
    ) -> BlitzObjectWrapper:
        # TODO: move _lookup to a _configure type
        gateway.SERVICE_OPTS.setOmeroGroup("-1")
        obj = gateway.getObject(_type, oid)
        if not obj:
            self.ctx.die(110, f"No such {_type}: {oid}")
        return obj
