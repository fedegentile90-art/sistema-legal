from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_FILES = [ROOT / "app.py", ROOT / "ui.py", ROOT / "views.py"]

# Patrones típicos de mojibake UTF-8 mal decodificado en CP1252/Latin-1.
BAD_PATTERNS = [
    "\u00c3",  # Ã
    "\u00c2",  # Â
    "\u00e2\u20ac",  # â€
    "\u00f0\u0178",  # ðŸ
    "â€¢",
    "ï¸",
]


def test_runtime_text_has_no_mojibake_patterns() -> None:
    for path in RUNTIME_FILES:
        text = path.read_text(encoding="utf-8", errors="strict")
        for token in BAD_PATTERNS:
            assert token not in text, f"Patron mojibake detectado en {path.name}: {token!r}"
