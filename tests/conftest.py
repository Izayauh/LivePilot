"""Shared pytest fixtures."""

import pytest


@pytest.fixture
def offline_ableton(monkeypatch):
    """Give the lazy ``ableton`` singleton a controller that never binds UDP 11001.

    Dispatch tests only check routing and argument passing. Constructing the real
    controller binds 11001 exclusively, which fails whenever the MCP server or another
    pytest run holds the port. Patching the listener out keeps them off the network;
    queries that need a reply fail fast with "listener is not running".
    """
    from ableton_controls import controller

    monkeypatch.setattr(controller.AbletonController, "_start_response_listener",
                        lambda self: None)
    monkeypatch.setattr(controller.ableton, "_instance", None)
    yield controller.ableton
