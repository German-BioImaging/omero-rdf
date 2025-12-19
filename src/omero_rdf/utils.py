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


import contextlib
import gzip
import sys
from functools import wraps
from typing import Any, Callable, Dict, Generator, List, Tuple, Union
from omero.gateway import BlitzGateway

from rdflib import BNode, Literal, URIRef

# TYPE DEFINITIONS

Data = Dict[str, Any]
Subj = Union[BNode, URIRef]
Obj = Union[BNode, Literal, URIRef]
Triple = Tuple[Subj, URIRef, Obj]
Handlers = List[Callable[[URIRef, URIRef, Data], Generator[Triple, None, bool]]]


@contextlib.contextmanager
def open_with_default(filename=None, filehandle=None):
    """
    Open a file for writing if given and close on completion.

    No closing will happen if the file name is "-" since stdout will be used.
    If no filehandle is given, stdout will also be used.
    Otherwise return the given filehandle will be used.
    """
    close = False
    if filename:
        if filename == "-":
            fh = sys.stdout
        else:
            if filename.endswith(".gz"):
                fh = gzip.open(filename, "wt")
            else:
                fh = open(filename, "w")
            close = True
    else:
        if filehandle is None:
            filehandle = sys.stdout
        fh = filehandle

    try:
        yield fh
    finally:
        if close:
            fh.close()


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
