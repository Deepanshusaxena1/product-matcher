"""Pull the JSON state that shop pages embed in a <script> for their own JavaScript.

Flipkart (`window.__INITIAL_STATE__`), Croma (`window.__INITIAL_DATA__`) and Myntra (`window.__myx`) all
render from such an object, and it is far more stable than their CSS class names. `dig` walks such an
object without trusting its shape.
"""

from __future__ import annotations

import json
from typing import Any

# strict=False: Croma embeds raw control characters (newlines) inside JSON strings.
_DECODER = json.JSONDecoder(strict=False)


def embedded_json(html: str, marker: str) -> Any:
    """The JSON object or array that starts right after `marker`, or None when there is none.

    Only that one value is decoded; whatever follows it in the script is ignored. Occurrences of `marker` that
    are not followed by a value (such as the start of a longer name, `window.__myx_deviceType__`) are skipped.
    """
    at = html.find(marker)
    while at >= 0:
        start = at + len(marker)
        while start < len(html) and (html[start].isspace() or html[start] == "="):
            start += 1
        if html[start : start + 1] in ("{", "["):
            try:
                value, _ = _DECODER.raw_decode(html, start)
            except json.JSONDecodeError:
                return None
            return value
        at = html.find(marker, at + 1)
    return None


def dig(value: Any, *path: str | int) -> Any:
    """`value[path[0]][path[1]]...`, or None as soon as a step is missing or of the wrong shape."""
    for step in path:
        if isinstance(step, int):
            value = value[step] if isinstance(value, list) and -len(value) <= step < len(value) else None
        else:
            value = value.get(step) if isinstance(value, dict) else None
        if value is None:
            return None
    return value
