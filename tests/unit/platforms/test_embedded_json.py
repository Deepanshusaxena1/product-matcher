import pytest

from app.platforms.embedded_json import embedded_json


def test_the_object_assigned_after_a_marker_is_decoded() -> None:
    html = '<script>window.__INITIAL_STATE__ = {"a": {"b": [1, 2]}, "c": "}"};window.other = 1;</script>'

    assert embedded_json(html, "window.__INITIAL_STATE__") == {"a": {"b": [1, 2]}, "c": "}"}


def test_control_characters_inside_strings_are_tolerated() -> None:
    # Croma's pages embed raw newlines in JSON strings, which strict JSON forbids.
    html = 'x = {"name": "line one\nline two"}'

    assert embedded_json(html, "x =") == {"name": "line one\nline two"}


def test_the_value_of_a_key_inside_a_script_can_be_targeted() -> None:
    html = 'window.__INITIAL_DATA__ = {...state, "pdpData": {"code": "303849"}, "other": f()}'

    assert embedded_json(html, '"pdpData":') == {"code": "303849"}


@pytest.mark.parametrize("html", ["", "<html>no state here</html>", "window.__INITIAL_STATE__ = undefined;"])
def test_a_missing_or_undecodable_object_is_none(html: str) -> None:
    assert embedded_json(html, "window.__INITIAL_STATE__") is None


def test_a_longer_name_that_starts_with_the_marker_is_skipped() -> None:
    # Myntra assigns `window.__myx_deviceType__` before `window.__myx`.
    html = "window.__myx_deviceType__ = 'desktop'; window.__myx = {\"searchData\": {}}"

    assert embedded_json(html, "window.__myx") == {"searchData": {}}
