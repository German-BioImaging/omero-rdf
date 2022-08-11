#!/usr/bin/env python
#
# Copyright (c) 2022 German BioImaging
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
import os

from setuptools import setup


def read(fname):
    """
    Utility function to read the README file.
    :rtype : String
    """
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


version = "0.1.0"
url = "https://github.com/german-bioimaging/omero-rdf"

setup(
    version=version,
    packages=["omero_rdf", "omero.plugins"],
    package_dir={"": "src"},
    name="omero-rdf",
    description="A plugin for exporting rdf from OMERO",
    long_description=read("README.rst"),
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Environment :: Plugins",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: GNU General Public License v2 " "or later (GPLv2+)",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],  # Get strings from
    # http://pypi.python.org/pypi?%3Aaction=list_classifiers
    author="OME Team",
    author_email="ome-team@openmicroscopy.org",
    license="GPL-2.0+",
    url="%s" % url,
    zip_safe=False,
    download_url=f"{url}/v{version}.tar.gz",
    install_requires=["omero-py>=5.8", "entrypoints", "future", "rdflib"],
    python_requires=">=3",
    keywords=["OMERO.CLI", "plugin"],
    tests_require=["pytest", "restview", "mox3"],
    entry_points={
        "omero_rdf.annotation_handler": [
            "idr_annotations = omero_rdf.idr_annotations:IDRAnnotationHandler"
        ]
    },
)
