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


from omero.testlib.cli import CLITest
from omero_rdf import RdfControl


class TestRdf(CLITest):
    def setup_method(self, method):
        super().setup_method(method)
        self.cli.register("rdf", RdfControl, "TEST")
        self.args += ["rdf"]

    def rdf(self, capfd):
        self.cli.invoke(self.args, strict=True)
        return capfd.readouterr()[0]

    def test_rdf(self, capfd):
        name = self.uuid()
        object_type = "Project"
        oid = self.create_object(object_type, name=f"{name}")
        obj_arg = f"{object_type}:{oid}"
        self.args += [obj_arg]
        out = self.rdf(capfd)
        assert out
