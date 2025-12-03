import logging
from argparse import Namespace

from omero_rdf import RdfControl


class DummyCtx:
    def out(self, msg):
        pass

    def err(self, msg):
        pass


def test_warns_for_nt_when_turtle(caplog):
    ctrl = RdfControl()
    ctrl.ctx = DummyCtx()
    args = Namespace(file="out.nt", format="turtle", pretty=False, yes=True)

    with caplog.at_level(logging.WARNING):
        ctrl._validate_extensions(args)

    assert ".nt' does not match format 'turtle'" in caplog.text


def test_warns_when_pretty_overrides_extension(caplog):
    ctrl = RdfControl()
    ctrl.ctx = DummyCtx()
    args = Namespace(file="out.nt", format="ntriples", pretty=True, yes=True)

    with caplog.at_level(logging.WARNING):
        ctrl._validate_extensions(args)

    assert "--pretty sets output format to Turtle" in caplog.text


def test_allows_matching_extension(caplog):
    ctrl = RdfControl()
    ctrl.ctx = DummyCtx()
    args = Namespace(file="out.nt", format="ntriples", pretty=False, yes=True)

    with caplog.at_level(logging.WARNING):
        ctrl._validate_extensions(args)

    assert not caplog.records
