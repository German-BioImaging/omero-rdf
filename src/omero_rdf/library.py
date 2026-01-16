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

"""Programmatic API for RDF export."""

from omero_rdf.handler import Handler, HandlerError
from omero_rdf.formats import TurtleFormat


class Triplyfier:
    """Export RDF for OMERO objects using an existing gateway connection."""

    def __init__(self, connection):
        self.connection = connection

    def export_graph(self, **kwargs):
        """
        Returns the populated rdflib.Graph for a target OMERO object.
        """
        target = kwargs.get("target")
        if isinstance(target, str) and ":" in target:
            target_type, target_id = target.split(":", 1)
            obj = self.connection.getObject(target_type, int(target_id))
            if obj is None:
                raise HandlerError(110, f"No such {target_type}: {target_id}")
            target = obj._obj if hasattr(obj, "_obj") else obj

        turtle_format = TurtleFormat()
        handler = Handler(
            gateway=self.connection,
            formatter=turtle_format,
            trim_whitespace=False,
            use_ellide=False,
            first_handler_wins=False,
            descent="recursive",
        )
        handler.descend(self.connection, target)
        return turtle_format.graph
