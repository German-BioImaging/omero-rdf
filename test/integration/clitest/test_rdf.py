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
from omero.model import LabelI, RoiI, CommentAnnotationI
from omero.rtypes import rstring

from rdflib import Graph, Namespace, RDF
from rdflib.namespace import DCTERMS


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

    def test_rois(self, capfd):

        update = self.client.sf.getUpdateService()

        # Setup a test image with a roi
        pix = self.create_pixels()
        img = pix.image
        roi_ann = CommentAnnotationI()
        roi_ann.setTextValue(rstring("my roi annotation"))
        roi = RoiI()
        roi.setDescription(rstring("please check me"))
        roi.linkAnnotation(roi_ann)
        label_ann = CommentAnnotationI()
        label_ann.setTextValue(rstring("my label annotation"))
        label = LabelI()
        label.setTextValue(rstring("this is the label"))
        label.linkAnnotation(label_ann)
        roi.addShape(label)
        img.addRoi(roi)
        img = update.saveAndReturnObject(img)

        # Export the test image
        object_type = "Image"
        obj_arg = f"{object_type}:{img.id.val}"
        self.args += ["-Fturtle", obj_arg]
        out = self.rdf(capfd)

        # Check that it contains the roi linked to the image (issue#42)
        g = Graph()
        g.parse(data=out, format="ttl")

        xml = Namespace("http://www.openmicroscopy.org/Schemas/OME/2016-06#")

        found = False
        for s, p, o in g.triples((None, DCTERMS.isPartOf, None)):
            print(s, p, o)
            if (s, RDF.type, xml.ROI) in g and (o, RDF.type, xml.Pixels) in g:
                found = True

        assert found, "no link between pixels and ROI:" + g.serialize()
