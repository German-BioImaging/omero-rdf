.. image:: https://github.com/German-BioImaging/omero-rdf/workflows/OMERO/badge.svg
    :target: https://github.com/german-bioimaging/omero-rdf/actions

.. image:: https://badge.fury.io/py/omero-rdf.svg
    :target: https://badge.fury.io/py/omero-rdf

omero-rdf
=========

A plugin for exporting RDF from OMERO


Requirements
============

* OMERO 5.6.0 or newer
* Python 3.8 or newer


Installing from PyPI
====================

This section assumes that an `OMERO.py <https://github.com/ome/omero-py>`_ is already installed.

Install the command-line tool using `pip <https://pip.pypa.io/en/stable/>`_:

::

    $ pip install -U omero-rdf


Developer guidelines 
====================

Using `uv` (recommended):

1. Fork/clone the repository (e.g. ``gh repo fork https://github.com/German-BioImaging/omero-rdf``).
2. Create a virtualenv and activate it:

   ::

       uv venv .venv
       source .venv/bin/activate

   (or prefix commands with ``uv run`` instead of activating).

3. Install in editable mode with test dependencies (pulls the correct platform-specific ``zeroc-ice`` wheel):

   ::

       uv pip install -e ".[tests,dev]"

4. Run the test suite:

   ::

       pytest

5. Lint and format:

   ::

       ruff check 
       ruff format --check
       ruff format
 

Quick check against IDR
-----------------------

Assuming you have the `uv` environment active (`source .venv/bin/activate`), use
the public IDR server to confirm the CLI works (public/public credentials):

1. Log in once to create a session:

   ::

       omero login -s idr.openmicroscopy.org -u public -w public

2. Export RDF for a project on IDR (2902) and inspect the first triples:

   ::

       omero rdf -F=turtle Project:2902 -S=flat | head  -n 10       

Release process
---------------

This repository uses `versioneer <https://pypi.org/project/versioneer/>`_
to manage version numbers. A tag prefixed with `v` will be detected by
the library and used as the current version at runtime.

Remember to ``git push`` all commits and tags.

Funding
-------

Funded by the `Delta Tissue <https://wellcomeleap.org/delta-tissue/>`_
Program of `Wellcome Leap <https://wellcomeleap.org/>`_.

License
-------

This project, similar to many Open Microscopy Environment (OME) projects, is
licensed under the terms of the GNU General Public License (GPL) v2 or later.

Copyright
---------

2022-2024, German BioImaging
