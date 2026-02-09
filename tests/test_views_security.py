from views import _legacy_badge_html


def test_legacy_badge_html_escapes_payload() -> None:
    payload = "<img src=x onerror=alert(1)>"
    rendered = _legacy_badge_html(payload)
    assert "<img" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
