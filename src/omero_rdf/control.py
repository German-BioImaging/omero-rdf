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

"""CLI control for the `omero rdf` command."""

import logging
from argparse import Namespace
from omero.cli import BaseControl, Parser, ProxyStringType

from omero_rdf.formats import format_list, format_mapping, TurtleFormat
from omero_rdf.utils import gateway_required, open_with_default
from omero_rdf.handler import Handler, HandlerError


class RdfControl(BaseControl):
    """CLI control for RDF export as an omero CLI plugin.

    This class is created when running e.g. `omero rdf Image:123` in the command line.

    """

    def _configure(self, parser: Parser) -> None:
        """Register CLI arguments for RDF export."""
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
        """Run RDF export for the requested target(s).

        Writes to stdout or the configured file path.
        """
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
            try:
                handler.descend(self.gateway, args.target)
                handler.close()
            except HandlerError as err:
                self.ctx.die(err.status, str(err))

    def _validate_extensions(self, args):
        """Warn or prompt when output file extensions do not match the format."""
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
