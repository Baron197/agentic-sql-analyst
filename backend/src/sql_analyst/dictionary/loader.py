"""Load and validate data/dictionary.yaml."""

from functools import lru_cache
from pathlib import Path

import yaml

from sql_analyst.dictionary.models import Dictionary

REPO_ROOT = Path(__file__).resolve().parents[4]
DICTIONARY_PATH = REPO_ROOT / "data" / "dictionary.yaml"


def load_dictionary(path: Path = DICTIONARY_PATH) -> Dictionary:
    """Parse the YAML and validate it against the models (raises on any mismatch)."""
    with path.open(encoding="utf-8") as f:
        return Dictionary.model_validate(yaml.safe_load(f))


@lru_cache
def get_dictionary() -> Dictionary:
    return load_dictionary()
