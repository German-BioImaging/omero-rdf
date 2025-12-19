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

from omero_rdf.library import Triplyfier as Triplyfier
from omero_rdf.control import RdfControl as RdfControl

HELP = """A plugin for exporting RDF from OMERO

omero-rdf creates a stream of RDF triples from the starting object that
it is given. This may be one of: Image, Dataset, Project, Plate, and Screen.

Examples:

  omero rdf Image:123                # Streams each triple found in N-Triples format

  omero rdf -F=jsonld Image:123      # Collects all triples and prints formatted output
  omero rdf -S=flat Project:123      # Do not recurse into containers ("flat-strategy")
  omero rdf --trim-whitespace ...    # Strip leading and trailing whitespace from text
  omero rdf --first-handler-wins ... # First mapping wins; others will be ignored

  omero rdf --file - ...             # Write RDF triples to stdout
  omero rdf --file output.nt ...     # Write RDF triples to the specified file
  omero rdf --file output.nt.gz      # Write RDF triples to the specified file, gzipping

"""
