"""Every relative link in the Markdown docs points to a file that exists, and every
`#anchor` to a heading in it (GitHub's heading ids). External links are not fetched here."""

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCS = sorted(
    [
        *(ROOT / name for name in ("README.md", "PROGRESS.md", "BUILD_GUIDE.md", "CLAUDE.md")),
        *(ROOT / "docs").glob("*.md"),
        *(ROOT / "eval" / "results").glob("*.md"),
    ]
)
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")


def _slug(heading: str) -> str:
    """GitHub's id for a heading: lower case, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"[`*_]|\[([^\]]*)\]\([^)]*\)", r"\1", heading.strip()).lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    seen: dict[str, int] = {}
    out = set()
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE):
        base = _slug(m.group(1))
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.add(base if n == 0 else f"{base}-{n}")
    return out


def _links(path: Path) -> list[str]:
    text = INLINE_CODE.sub("", FENCE.sub("", path.read_text(encoding="utf-8")))
    return LINK.findall(text)


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_resolve(doc: Path):
    broken = []
    for target in _links(doc):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # http:, https:, mailto:
            continue
        file_part, _, anchor = target.partition("#")
        dest = (doc.parent / unquote(file_part)).resolve() if file_part else doc
        if not dest.exists():
            broken.append(f"{target} (no such file)")
        elif anchor and dest.suffix == ".md" and anchor not in _anchors(dest):
            broken.append(f"{target} (no such heading)")
    assert not broken, f"{doc.name}: {broken}"


def test_slug_matches_github():
    assert _slug("Run it locally (keyless)") == "run-it-locally-keyless"
    assert _slug("6. Check it, then switch live mode on") == "6-check-it-then-switch-live-mode-on"
    assert _slug("D054: The demo runs in Sydney") == "d054-the-demo-runs-in-sydney"
