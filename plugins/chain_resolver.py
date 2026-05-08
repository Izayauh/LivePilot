"""Resolve chain plugin suggestions against the user's declared inventory."""

from __future__ import annotations


HOST_PREFERENCE = ("Waves", "Ableton Stock")


def resolve_plugin(plugin_suggestions: list[str], owned: dict) -> tuple[str, str]:
    """
    Given a chain step's plugin_suggestions list, return (plugin_name, host) of the
    first owned match. Prefer Waves over stock when both are listed. Raise
    ValueError if no suggestion is owned.
    """
    host_inventory = owned.get("host", {})

    for host in HOST_PREFERENCE:
        owned_names = set(host_inventory.get(host, []))
        for suggestion in plugin_suggestions:
            if suggestion in owned_names:
                return suggestion, host

    raise ValueError(f"No owned plugin found for suggestions: {plugin_suggestions}")
