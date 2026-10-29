"""Pydantic models for data/dictionary.yaml. Unknown keys are errors, so typos fail loudly."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Synonyms(_Strict):
    en: list[str] = Field(default_factory=list)
    id: list[str] = Field(default_factory=list)

    def all(self) -> list[str]:
        return [*self.en, *self.id]


class Column(_Strict):
    name: str
    type: str
    description: str = Field(min_length=10)
    pii: bool = False
    categorical: bool = False
    free_text: bool = False
    examples: list[str] = Field(default_factory=list)
    synonyms: Synonyms = Field(default_factory=Synonyms)
    deprecated: str | None = None


class View(_Strict):
    name: str
    description: str = Field(min_length=10)
    grain: str
    synonyms: Synonyms = Field(default_factory=Synonyms)
    columns: list[Column]

    def column(self, name: str) -> Column:
        return next(c for c in self.columns if c.name == name)


class JoinPath(_Strict):
    from_: str = Field(alias="from")
    to: str
    note: str | None = None


class Label(_Strict):
    en: str
    id: str


class Metric(_Strict):
    name: str
    label: Label
    synonyms: Synonyms
    description: str = Field(min_length=10)
    sql: str


class DataWindow(_Strict):
    start: date
    end: date
    note: str


class Dictionary(_Strict):
    version: int
    company: str
    data_window: DataWindow
    business_rules: list[str]
    views: list[View]
    join_paths: list[JoinPath]
    glossary: list[Metric]

    def view(self, name: str) -> View:
        return next(v for v in self.views if v.name == name)

    def categorical_columns(self) -> list[tuple[str, str]]:
        """(view, column) pairs whose distinct values feed the value index."""
        return [(v.name, c.name) for v in self.views for c in v.columns if c.categorical]
