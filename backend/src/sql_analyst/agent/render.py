"""Fill answer-template slots from the query result, with locale-aware number formatting.

Slots (the only way a figure reaches the answer):
- `{{r<i>.<column>}}`: the cell in row i (0-based) of the result;
- `{{sum.<column>}}`, `{{avg.<column>}}`, `{{min.<column>}}`, `{{max.<column>}}`: over all rows;
- `{{row_count}}`: the number of rows returned.

Formatting follows the column name: rupiah as `IDR 1.23B` (en) / `Rp 1,23 miliar` (id),
rates and shares as percentages, counts with thousands separators, and identifiers such
as years or codes as they are.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from sql_analyst.agent.grounding import typed_numbers

Lang = Literal["en", "id"]

SLOT = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
_CELL = re.compile(r"^r(\d+)\.(.+)$")
_AGG = re.compile(r"^(sum|avg|min|max)\.(.+)$")

_PLAIN = re.compile(
    r"(^|_)(id|code|number|year|month|quarter|week|day|hour|level|sku)$"
    r"|^(year|month|quarter|fiscal_year|fiscal_quarter|fiscal_month|day_of_month|iso_day_of_week)"
)
_PERCENT = re.compile(r"rate|ratio|share|pct|percent|conversion|margin|persen")
_COUNT = re.compile(r"count|qty|quantity|units|orders|customers|visitors|sessions|tickets|jumlah")
_MONEY = re.compile(r"_idr$|^idr_|revenue|sales|amount|aov|price|spend|fee|cost|omzet|pendapatan")

_SCALES = {
    "en": [(10**12, "T"), (10**9, "B"), (10**6, "M")],
    "id": [(10**12, " triliun"), (10**9, " miliar"), (10**6, " juta")],
}
_NO_DATA = {"en": "no data", "id": "tidak ada data"}
_BOOL = {"en": ("yes", "no"), "id": ("ya", "tidak")}


class RenderError(ValueError):
    """The template refers to a slot that does not exist or cannot be computed."""


def column_kind(column: str) -> Literal["plain", "percent", "count", "money", "number"]:
    """How to format a numeric column, judged from its name (the SQL alias)."""
    name = column.lower()
    if _PLAIN.search(name):
        return "plain"
    return _measure_kind(name)


def _measure_kind(name: str) -> Literal["percent", "count", "money", "number"]:
    if _PERCENT.search(name):
        return "percent"
    if _COUNT.search(name):
        return "count"
    if _MONEY.search(name):
        return "money"
    return "number"


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _group(digits: str, sep: str) -> str:
    out = ""
    while len(digits) > 3:
        out = sep + digits[-3:] + out
        digits = digits[:-3]
    return digits + out


def format_number(value: float | int | Decimal, lang: Lang, decimals: int = 2) -> str:
    """Thousands separators and up to `decimals` decimals (trailing zeros trimmed)."""
    thousands, point = (",", ".") if lang == "en" else (".", ",")
    q = round(Decimal(str(value)), decimals)
    sign = "-" if q < 0 else ""
    whole, _, frac = f"{abs(q):f}".partition(".")
    frac = frac.rstrip("0")
    return sign + _group(whole, thousands) + (point + frac if frac else "")


def format_money(value: float | int | Decimal, lang: Lang) -> str:
    prefix = "IDR " if lang == "en" else "Rp "
    v = Decimal(str(value))
    for size, suffix in _SCALES[lang]:
        if abs(v) >= size:
            scaled = v / size
            decimals = 2 if abs(scaled) < 10 else (1 if abs(scaled) < 100 else 0)
            return prefix + format_number(scaled, lang, decimals) + suffix
    return prefix + format_number(v, lang, 0)


def format_value(value: Any, column: str, lang: Lang) -> str:
    if value is None:
        return _NO_DATA[lang]
    if isinstance(value, bool):
        return _BOOL[lang][0 if value else 1]
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if not _is_number(value):
        return str(value)
    kind = column_kind(column)
    if kind == "plain":
        if Decimal(str(value)) == int(value):  # years, ids, codes: shown as they are
            return str(int(value))
        kind = _measure_kind(column.lower())  # e.g. avg_orders_per_day
    if kind == "money":
        return format_money(value, lang)
    if kind == "percent":
        v = Decimal(str(value))
        pct = v * 100 if abs(v) <= Decimal("1.5") and "pct" not in column.lower() else v
        return format_number(pct, lang, 1) + "%"
    return format_number(value, lang, 2)


def _column_index(columns: list[str], name: str) -> int:
    if name in columns:
        return columns.index(name)
    lowered = [c.lower() for c in columns]
    if name.lower() in lowered:
        return lowered.index(name.lower())
    raise RenderError(f"Unknown column {name!r}. Columns: {', '.join(columns)}")


def slot_value(slot: str, columns: list[str], rows: list[list[Any]], lang: Lang) -> str:
    if slot == "row_count":
        return format_number(len(rows), lang, 0)
    if m := _CELL.match(slot):
        i, j = int(m.group(1)), _column_index(columns, m.group(2).strip())
        if i >= len(rows):
            raise RenderError(f"Row {i} does not exist: the result has {len(rows)} row(s).")
        return format_value(rows[i][j], columns[j], lang)
    if m := _AGG.match(slot):
        fn, j = m.group(1), _column_index(columns, m.group(2).strip())
        values = [r[j] for r in rows if r[j] is not None]
        if not values:
            return _NO_DATA[lang]
        if not all(_is_number(v) for v in values):
            raise RenderError(f"{fn}.{columns[j]} needs a numeric column.")
        nums = [Decimal(str(v)) for v in values]
        result = {
            "sum": sum(nums),
            "avg": sum(nums) / len(nums),
            "min": min(nums),
            "max": max(nums),
        }[fn]
        return format_value(result, columns[j], lang)
    raise RenderError(
        f"Unknown slot {{{{{slot}}}}}: use r<i>.<column>, sum|avg|min|max.<column>, or row_count."
    )


def strip_slots(template: str) -> str:
    """The text the model typed: the template with every slot removed."""
    return SLOT.sub(" ", template)


def fill(template: str, columns: list[str], rows: list[list[Any]], lang: Lang) -> str:
    """Replace every slot with its formatted value. Raises RenderError on a bad slot."""
    return SLOT.sub(lambda m: slot_value(m.group(1), columns, rows, lang), template)


def grounding_problems(template: str, caveats: list[str], question: str) -> list[str]:
    """Numbers the model typed outside slots (template prose and caveats)."""
    typed = typed_numbers(strip_slots(template) + " " + " ".join(caveats), question)
    return sorted(typed)
