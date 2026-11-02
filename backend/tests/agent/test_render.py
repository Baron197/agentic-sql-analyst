"""Number formatting and slot filling (agent/render.py) and the grounding rule."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from sql_analyst.agent.grounding import typed_numbers
from sql_analyst.agent.render import (
    RenderError,
    column_kind,
    fill,
    format_money,
    format_value,
    grounding_problems,
    strip_slots,
)


@pytest.mark.parametrize(
    ("value", "en", "id_"),
    [
        (950_000, "IDR 950,000", "Rp 950.000"),
        (1_234_567, "IDR 1.23M", "Rp 1,23 juta"),
        (Decimal("1234567890"), "IDR 1.23B", "Rp 1,23 miliar"),
        (12_345_678_901, "IDR 12.3B", "Rp 12,3 miliar"),
        (123_456_789_012, "IDR 123B", "Rp 123 miliar"),
        (2_500_000_000_000, "IDR 2.5T", "Rp 2,5 triliun"),
        (-5_000_000, "IDR -5M", "Rp -5 juta"),
    ],
)
def test_money_is_scaled_per_locale(value, en, id_):
    assert format_money(value, "en") == en
    assert format_money(value, "id") == id_


@pytest.mark.parametrize(
    ("column", "value", "en", "id_"),
    [
        ("return_rate", Decimal("0.0431"), "4.3%", "4,3%"),
        ("conversion_rate", 0.5, "50%", "50%"),
        ("growth_pct", Decimal("12.5"), "12.5%", "12,5%"),
        ("orders", 12345, "12,345", "12.345"),
        ("avg_orders_per_day", Decimal("163.4567"), "163.46", "163,46"),
        ("year", 2025, "2025", "2025"),
        ("store_id", 1234, "1234", "1234"),
        ("net_revenue_idr", 2_000_000, "IDR 2M", "Rp 2 juta"),
        ("total_amount", 950_000, "IDR 950,000", "Rp 950.000"),
        ("avg_csat", Decimal("4.1234"), "4.12", "4,12"),
        ("city", "Jakarta", "Jakarta", "Jakarta"),
        ("month", date(2025, 3, 1), "March 2025", "Maret 2025"),
        ("month_start", datetime(2025, 5, 1), "May 2025", "Mei 2025"),  # date_trunc on a timestamp
        ("bulan", date(2025, 8, 1), "August 2025", "Agustus 2025"),
        ("month", date(2025, 3, 15), "2025-03-15", "2025-03-15"),  # not a month start
        ("first_order_date", date(2025, 3, 1), "2025-03-01", "2025-03-01"),  # not a month column
        ("ordered_at", datetime(2025, 3, 1, 14, 5), "2025-03-01 14:05", "2025-03-01 14:05"),
        ("is_online", True, "yes", "ya"),
        ("net_revenue_idr", None, "no data", "tidak ada data"),
    ],
)
def test_values_are_formatted_by_column_name_and_locale(column, value, en, id_):
    assert format_value(value, column, "en") == en
    assert format_value(value, column, "id") == id_


def test_column_kinds():
    assert [column_kind(c) for c in ("share_of_orders", "units_sold", "aov_idr", "sku", "x")] == [
        "percent",
        "count",
        "money",
        "plain",
        "number",
    ]


def test_fill_supports_cells_aggregates_and_row_count():
    cols, rows = ["city", "orders"], [["Jakarta", 10], ["Bogor", 5], ["Depok", None]]
    out = fill(
        "{{r1.city}}: {{r1.orders}}; sum {{sum.orders}}, avg {{avg.orders}}, "
        "max {{ max.orders }}, min {{min.orders}}, n={{row_count}}",
        cols,
        rows,
        "en",
    )
    assert out == "Bogor: 5; sum 15, avg 7.5, max 10, min 5, n=3"


def test_column_lookup_is_case_insensitive():
    assert fill("{{r0.Orders}}", ["orders"], [[3]], "en") == "3"


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("{{r9.orders}}", "Row 9 does not exist"),
        ("{{r0.revenue}}", "Unknown column 'revenue'"),
        ("{{sum.city}}", "needs a numeric column"),
        ("{{median.orders}}", "Unknown slot"),
    ],
)
def test_bad_slots_raise(template, message):
    with pytest.raises(RenderError, match=message):
        fill(template, ["city", "orders"], [["Jakarta", 1]], "en")


def test_strip_slots_leaves_only_model_text():
    assert (
        strip_slots("In {{r0.city}} there were {{r0.orders}} orders.")
        == "In   there were   orders."
    )


def test_grounding_allows_numbers_from_the_question_only():
    assert typed_numbers("Top 5 stores in 2025 had 1,200 orders", "top 5 stores in 2025") == {
        "1,200"
    }
    assert grounding_problems("{{r0.x}} in Q2 2026", [], "Revenue in Q2 2026?") == []
    assert grounding_problems("{{r0.x}} orders", ["Data ends in 2026."], "orders?") == ["2026"]


@pytest.mark.parametrize(
    ("template", "lang", "expected"),
    [
        ("sebesar Rp{{r0.net_revenue_idr}}", "id", "sebesar Rp 8,81 miliar"),
        ("({{r0.net_revenue_idr}} IDR)", "en", "(IDR 8.81B)"),
        ("IDR {{sum.net_revenue_idr}} total", "en", "IDR 8.81B total"),
        ("{{r0.orders}} rupiah", "id", "5 rupiah"),  # only money slots carry a currency
    ],
)
def test_currency_written_next_to_a_money_slot_is_not_doubled(template, lang, expected):
    """Live run 2026-10-30: the model wrote "Rp{{…}}", which rendered as "RpRp 8,81 miliar"."""
    assert fill(template, ["net_revenue_idr", "orders"], [[8_810_000_000, 5]], lang) == expected
