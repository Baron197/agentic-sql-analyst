"""docs/SECURITY.md: every threat in the threat table maps to tests that exist."""

import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[1]
SECURITY_MD = TESTS_DIR.parents[1] / "docs" / "SECURITY.md"
REF = re.compile(r"`([\w/]+\.py)::(test_\w+)`")


def _threat_rows() -> list[str]:
    text = SECURITY_MD.read_text(encoding="utf-8")
    section = text.split("## Threat model", 1)[1].split("### Threats covered in later phases", 1)[0]
    return [
        line
        for line in section.splitlines()
        if line.startswith("| ") and not line.startswith("| Threat")
    ]


def test_threat_table_is_not_empty():
    assert len(_threat_rows()) >= 12


def test_every_threat_maps_to_at_least_one_test():
    for row in _threat_rows():
        assert REF.search(row), f"threat without a test: {row[:80]}"


def test_every_referenced_test_exists():
    for row in _threat_rows():
        for path, name in REF.findall(row):
            source = (TESTS_DIR / path).read_text(encoding="utf-8")
            assert re.search(rf"^def {name}\(", source, re.MULTILINE), f"{path}::{name} not found"
