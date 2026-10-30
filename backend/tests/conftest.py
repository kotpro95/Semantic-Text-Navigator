import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.parsing.classify import parse_document  # noqa: E402
from app.resolver import build_registry  # noqa: E402

DOCS = ROOT.parent / "documents"
AS_OF = date(2026, 3, 10)


def sample_texts() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(DOCS.glob("*.txt"))}


def run(texts: dict[str, str], as_of: date = AS_OF):
    docs = [parse_document(name, text) for name, text in texts.items()]
    views, flags = build_registry(docs, as_of)
    return {v.number: v for v in views}, flags, docs


@pytest.fixture
def texts():
    return sample_texts()
