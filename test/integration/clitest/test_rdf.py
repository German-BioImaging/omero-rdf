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



import omero
import pytest
from omero.testlib.cli import CLITest
from omero.plugins.rdfimport RdfControl


class TestRdf(CLITest):

    def setup_method(self, method):
        super(TestRdf, self).setup_method(method)
        self.cli.register("rdf", RdfControl, "TEST")
        self.args += ["rdf"]

    def rdf(self, capfd):
        self.cli.invoke(self.args, strict=True)
        return capfd.readouterr()[0]

    def test_rdf(self):
        name = self.uuid()
        oid = self.create_object("Project", name="my test")
        obj_arg = '%s%s:%s' % (object_type, model, oid)
        self.args += [obj_arg]
        out = self.rdf(capfd)
