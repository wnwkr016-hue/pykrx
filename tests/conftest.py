import urllib.parse

import pytest
import vcr


def form_body_matcher(r1, r2):
    """Order-insensitive form body matcher for application/x-www-form-urlencoded.

    - Parses body into key/value pairs so parameter order differences do not cause mismatches.
    - Falls back to direct equality when parsing fails (e.g., non-form bodies).
    """

    def _normalize(body):
        if body is None:
            return None
        if isinstance(body, bytes):
            body = body.decode()
        parsed = urllib.parse.parse_qsl(body, keep_blank_values=True)
        return sorted(parsed)

    b1 = _normalize(r1.body)
    b2 = _normalize(r2.body)

    # If both bodies are None or parsing failed, compare raw bodies
    if b1 is None or b2 is None:
        return r1.body == r2.body
    return b1 == b2


custom_vcr = vcr.VCR(
    cassette_library_dir="tests/cassettes",
    record_mode="once",
    match_on=["uri", "method", "form_body"],
)
custom_vcr.register_matcher("form_body", form_body_matcher)


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "cassette_library_dir": "tests/cassettes",
        "record_mode": "once",
        "match_on": ["uri", "method", "form_body"],
    }


@pytest.fixture
def use_cassette(vcr_config, request):
    """
    Pytest fixture that conditionally wraps a test in a vcrpy cassette.
    If the requesting test is marked with @pytest.mark.cassette('<name>'),
    this fixture creates a vcr.VCR(**vcr_config) and uses its use_cassette
    context manager with the provided cassette name for the duration of the
    test. If no such marker is present, the fixture yields without applying
    any cassette.
    Parameters
    ----------
    vcr_config : dict
        Keyword arguments forwarded to vcr.VCR(...) when creating the VCR
        instance (e.g., serializer, cassette_library_dir, record_mode).
    request : _pytest.fixtures.FixtureRequest
        Pytest request object used to inspect the test for a 'cassette' marker.
    Yields
    ------
    None
        Control is yielded to the test body; teardown occurs after the test
        completes and after the cassette context (if any) exits.
    Notes
    -----
    The cassette name is taken from the first positional argument of the
    'cassette' marker. Any exceptions raised by the test propagate normally.
    """
    """자동으로 cassette을 적용하는 fixture"""
    marker = request.node.get_closest_marker("cassette")
    if not marker:
        yield
        return

    cassette_name = marker.args[0]
    with custom_vcr.use_cassette(cassette_name, **vcr_config):
        yield
