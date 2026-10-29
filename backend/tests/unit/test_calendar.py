from datetime import date, timedelta

import pytest

from sql_analyst.db.calendar import (
    calendar_rows,
    fiscal_month,
    fiscal_quarter,
    fiscal_year,
    holiday_name,
    lebaran_day,
    ramadan_day,
)


@pytest.mark.parametrize(
    ("d", "fy", "fq", "fm"),
    [
        (date(2025, 3, 31), 2024, 4, 12),
        (date(2025, 4, 1), 2025, 1, 1),
        (date(2025, 9, 30), 2025, 2, 6),
        (date(2025, 12, 31), 2025, 3, 9),
        (date(2026, 1, 1), 2025, 4, 10),
        (date(2026, 3, 31), 2025, 4, 12),
    ],
)
def test_fiscal_year_starts_in_april(d, fy, fq, fm):
    assert (fiscal_year(d), fiscal_quarter(d), fiscal_month(d)) == (fy, fq, fm)


@pytest.mark.parametrize(
    ("first_day", "eid"),
    [
        (date(2024, 3, 12), date(2024, 4, 10)),
        (date(2025, 3, 1), date(2025, 3, 31)),
        (date(2026, 2, 19), date(2026, 3, 21)),
    ],
)
def test_ramadan_and_lebaran_match_government_dates(first_day, eid):
    day = timedelta(days=1)
    assert ramadan_day(first_day) == 1
    assert ramadan_day(first_day - day) is None
    assert ramadan_day(eid - day) in (29, 30)
    assert ramadan_day(eid) is None
    assert lebaran_day(eid) == 1
    assert lebaran_day(eid + day) == 2
    assert lebaran_day(eid + 2 * day) is None


def test_holidays_and_harbolnas():
    assert holiday_name(date(2025, 11, 11)) == "Harbolnas 11.11"
    assert holiday_name(date(2025, 8, 17)) == "Hari Kemerdekaan"
    assert holiday_name(date(2025, 3, 31)) == "Idulfitri (Lebaran)"
    assert holiday_name(date(2025, 6, 3)) is None


def test_calendar_covers_data_and_fy2026_without_gaps():
    rows = calendar_rows()
    dates = [r[0] for r in rows]
    assert dates[0] == date(2024, 1, 1)
    assert dates[-1] == date(2027, 3, 31)
    assert len(dates) == (dates[-1] - dates[0]).days + 1
