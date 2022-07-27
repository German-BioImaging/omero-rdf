#!/usr/bin/env python

#
# Copyright (c) 2022 University of Dundee.
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
from functools import wraps

from omero.cli import BaseControl, Parser, ProxyStringType
from omero.gateway import BlitzGateway
from omero.model import Dataset, Image, Plate, Project, Screen
from omero_marshal import get_encoder
from rdflib import BNode, Literal, URIRef

HELP = """A plugin for exporting rdf from OMERO

Examples:

    omero rdf Image:123

"""


def gateway_required(func):
    """
    Decorator which initializes a client (self.client),
    a BlitzGateway (self.gateway), and makes sure that
    all services of the Blitzgateway are closed again.

    FIXME: copied from omero-cli-render. move upstream
    """

    @wraps(func)
    def _wrapper(self, *args, **kwargs):
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
    def action(self, args):
        for ignore in self.descend(self.gateway, args.target, batch=1):
            pass

    def descend(self, gateway, target, batch=100, handler=None):
        """
        Copied from omero-cli-render. Should be moved upstream
        """

        handler = Handler(gateway)

        if isinstance(target, list):
            for x in target:
                for rv in self.descend(gateway, x, batch):
                    yield rv
        elif isinstance(target, Screen):
            scr = self._lookup(gateway, "Screen", target.id)
            handler(scr)
            for plate in scr.listChildren():
                for rv in self.descend(gateway, plate._obj, batch):
                    yield rv
        elif isinstance(target, Plate):
            plt = self._lookup(gateway, "Plate", target.id)
            handler(plt)
            rv = []
            for well in plt.listChildren():
                handler(well)  # No descend
                for idx in range(0, well.countWellSample()):
                    img = well.getImage(idx)
                    handler(img.getPrimaryPixels())
                    handler(img)  # No descend
                    if batch == 1:
                        yield img
                    else:
                        rv.append(img)
                        if len(rv) == batch:
                            yield rv
                            rv = []
            if rv:
                yield rv

        elif isinstance(target, Project):
            prj = self._lookup(gateway, "Project", target.id)
            handler(prj)
            for ds in prj.listChildren():
                for rv in self.descend(gateway, ds._obj, batch):
                    yield rv

        elif isinstance(target, Dataset):
            ds = self._lookup(gateway, "Dataset", target.id)
            handler(ds)
            rv = []
            for img in ds.listChildren():
                handler(list(img.listAnnotations(None))[0])
                handler(img.getPrimaryPixels())
                handler(img)  # No descend
                if batch == 1:
                    yield img
                else:
                    rv.append(img)
                    if len(rv) == batch:
                        yield rv
                        rv = []
            if rv:
                yield rv

        elif isinstance(target, Image):
            img = self._lookup(gateway, "Image", target.id)
            handler(img.getPrimaryPixels())
            handler(img)
            if batch == 1:
                yield img
            else:
                yield [img]
        else:
            self.ctx.die(111, "TBD: %s" % target.__class__.__name__)

    def _lookup(self, gateway, _type, oid):
        # TODO: move _lookup to a _configure type
        gateway.SERVICE_OPTS.setOmeroGroup("-1")
        obj = gateway.getObject(_type, oid)
        if not obj:
            self.ctx.die(110, f"No such {_type}: {oid}")
        return obj


class Handler:

    OME = "http://www.openmicroscopy.org/rdf/2016-06/ome_core/"
    OMERO = "http://www.openmicroscopy.org/TBD/omero/"

    def __init__(self, gateway):
        self.gateway = gateway
        self.cache = set()
        self.bnode = 0

        # Attempt to auto-detect server
        comm = self.gateway.c.getCommunicator()
        self.info = self.gateway.c.getRouter(comm).ice_getEndpoints()[0].getInfo()

    def get_identity(self, _type, _id):
        if _type.endswith("I"):
            _type = _type[0:-1]
        return URIRef(f"https://{self.info.host}/{_type}/{_id}")

    def get_bnode(self):
        try:
            return BNode()
            # return f":b{self.bnode}"
        finally:
            self.bnode += 1

    def ellide(self, v):
        if isinstance(v, str):
            v = str(v)
            if len(v) > 50:
                v = f"{v[0:24]}...{v[-20:-1]}"
        return Literal(v)

    def __call__(self, o):
        c = o._obj.__class__
        encoder = get_encoder(c)
        if encoder is None:
            raise Exception(f"unknown: {c}")
        else:
            data = encoder.encode(o)
            self.handle(data)

    def handle(self, data):
        """
        TODO: Add quad representation as an option
        """
        for output in self.rdf(data):
            if output:
                s, p, o = output
                try:
                    print(f"""{s.n3():50}\t{p.n3():60}\t{o.n3()} .""")
                except Exception as e:
                    raise Exception(f"failed to dump {o}") from e

    def rdf(self, data, _id=None):

        _type = data.get("@type").split("#")[-1]

        if not _id:
            _id = data.get("@id")
            _id = self.get_identity(_type, _id)
            if _id in self.cache:
                logging.debug(f"# skipping previously seen {_id}")
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
                        v_type = v.get("@type").split("#")[-1]
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
        annotations = data.get("Annotations", None)
        if annotations:
            for annotation in annotations:
                yield (
                    _id,
                    f"{self.OME}:annotation",
                    self.get_identity("AnnotationTBD", annotation["@id"]),
                )
                yield from self.rdf(annotation)
