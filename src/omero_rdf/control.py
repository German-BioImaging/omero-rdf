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
from omero.cli import BaseControl, Parser, ProxyStringType
from omero.gateway import BlitzGateway, BlitzObjectWrapper
from omero.model import Dataset, Image, IObject, Plate, Project, Screen
from omero.sys import ParametersI

from rdflib import URIRef

from omero_rdf.formats import format_list, format_mapping, TurtleFormat
from omero_rdf.utils import gateway_required, open_with_default
from omero_rdf.handler import Handler


class RdfControl(BaseControl):
    def _configure(self, parser: Parser) -> None:
        parser.add_login_arguments()
        rdf_type = ProxyStringType("Image")
        rdf_help = "Object to be exported to RDF"
        parser.add_argument("target", type=rdf_type, nargs="+", help=rdf_help)
        format_group = parser.add_mutually_exclusive_group()
        format_group.add_argument(
            "--pretty",
            action="store_true",
            default=False,
            help="Shortcut for --format=turtle",
        )
        format_group.add_argument(
            "--format",
            "-F",
            default="ntriples",
            choices=format_list(),
        )
        parser.add_argument(
            "--descent",
            "-S",
            default="recursive",
            help="Descent strategy to use: recursive, flat",
        )
        parser.add_argument(
            "--ellide", action="store_true", default=False, help="Shorten strings"
        )
        parser.add_argument(
            "--first-handler-wins",
            "-1",
            action="store_true",
            default=False,
            help="Don't duplicate annotations",
        )
        parser.add_argument(
            "--trim-whitespace",
            action="store_true",
            default=False,
            help="Remove leading and trailing whitespace from literals",
        )
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Write RDF triples to the specified file",
        )
        parser.set_defaults(func=self.action)

    @gateway_required
    def action(self, args: Namespace) -> None:
        self._validate_extensions(args)

        # Support hidden --pretty flag
        if args.pretty:
            args.format = TurtleFormat()
        else:
            args.format = format_mapping()[args.format]

        with open_with_default(args.file) as fh:
            handler = Handler(
                self.gateway,
                formatter=args.format,
                use_ellide=args.ellide,
                trim_whitespace=args.trim_whitespace,
                first_handler_wins=args.first_handler_wins,
                descent=args.descent,
                filehandle=fh,
            )
            self.descend(self.gateway, args.target, handler)
            handler.close()

    def _validate_extensions(self, args):
        extension_map = {
            "ntriples": ["nt"],
            "turtle": ["ttl"],
            "jsonld": ["jsonld", "json"],
            "ro-crate": ["jsonld", "json"],
        }

        if args.file and args.file != "-":
            filename = args.file.lower()

            if filename.endswith(".gz"):
                filename = filename.replace(".gz", "")
            file_extension = filename.split(".")[-1]

            format_string = str(args.format)
            valid_exts = extension_map.get(format_string, [])

            if args.pretty:
                if format_string != "turtle" or file_extension != "ttl":
                    logging.warning(
                        "--pretty sets output format to Turtle."
                        " This may be conflicting with the "
                        "'--format' or '--file. settings"
                    )

            if valid_exts and file_extension not in valid_exts:
                logging.warning(
                    f".{file_extension}' does not match format '{format_string}'"
                    f"(expected: {', '.join(f'.{e}' for e in valid_exts)})",
                )

            if not getattr(args, "yes", False):  # hidden --yes
                self.ctx.out("This may cause incorrect output formatting.")
                reply = input("Continue anyway? [y/N]: ").strip().lower()
                if reply not in ("y", "yes"):
                    self.ctx.err("Aborted by user.")
                    return

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
            return [self.descend(gateway, t, handler) for t in target]

        # "descent" doesn't apply to a list
        if handler.skip_descent():
            objid = handler(target)
            logging.debug("skip descent: %s", objid)
            return objid
        else:
            handler.descending()

        if isinstance(target, Screen):
            scr = self._lookup(gateway, "Screen", target.id)
            scrid = handler(scr)
            for plate in scr.listChildren():
                pltid = self.descend(gateway, plate._obj, handler)
                handler.contains(scrid, pltid)
            handler.annotations(scr, scrid)
            return scrid

        elif isinstance(target, Plate):
            plt = self._lookup(gateway, "Plate", target.id)
            pltid = handler(plt)
            handler.annotations(plt, pltid)
            for well in plt.listChildren():
                wid = handler(well)  # No descend
                handler.contains(pltid, wid)
                for idx in range(0, well.countWellSample()):
                    img = well.getImage(idx)
                    imgid = self.descend(gateway, img._obj, handler)
                    handler.contains(wid, imgid)
            return pltid

        elif isinstance(target, Project):
            prj = self._lookup(gateway, "Project", target.id)
            prjid = handler(prj)
            handler.annotations(prj, prjid)
            for ds in prj.listChildren():
                dsid = self.descend(gateway, ds._obj, handler)
                handler.contains(prjid, dsid)
            return prjid

        elif isinstance(target, Dataset):
            ds = self._lookup(gateway, "Dataset", target.id)
            dsid = handler(ds)
            handler.annotations(ds, dsid)
            for img in ds.listChildren():
                imgid = self.descend(gateway, img._obj, handler)
                handler.contains(dsid, imgid)
            return dsid

        elif isinstance(target, Image):
            img = self._lookup(gateway, "Image", target.id)
            imgid = handler(img)
            if img.getPrimaryPixels() is not None:
                pixid = handler(img.getPrimaryPixels())
                handler.contains(imgid, pixid)
            handler.annotations(img, imgid)
            for roi in self._get_rois(gateway, img):
                roiid = handler(roi)
                handler.annotations(roi, roiid)
                handler.contains(pixid, roiid)
                for shape in roi.iterateShapes():
                    shapeid = handler(shape)
                    handler.annotations(shape, shapeid)
                    handler.contains(roiid, shapeid)
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
