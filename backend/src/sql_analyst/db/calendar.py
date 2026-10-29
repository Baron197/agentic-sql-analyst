"""Business calendar: fiscal year, Ramadan/Lebaran, Harbolnas, and a few holidays.

Ramadan and Idulfitri dates are the Indonesian government's (Kemenag sidang isbat)
decisions; sources are listed in docs/DATA.md. The fiscal year starts on 1 April
and is named after the calendar year it starts in: FY2025 = 1 Apr 2025 - 31 Mar 2026.
"""

from datetime import date, timedelta

DATA_START = date(2024, 1, 1)
DATA_END = date(2026, 9, 30)
CALENDAR_START = date(2024, 1, 1)
CALENDAR_END = date(2027, 3, 31)

# (first day of Ramadan, Idulfitri = 1 Syawal); Ramadan ends the day before Idulfitri.
RAMADAN = {
    2024: (date(2024, 3, 12), date(2024, 4, 10)),
    2025: (date(2025, 3, 1), date(2025, 3, 31)),
    2026: (date(2026, 2, 19), date(2026, 3, 21)),
}

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def fiscal_year(d: date) -> int:
    return d.year if d.month >= 4 else d.year - 1


def fiscal_quarter(d: date) -> int:
    return (d.month - 4) % 12 // 3 + 1


def fiscal_month(d: date) -> int:
    return (d.month - 4) % 12 + 1


def ramadan_day(d: date) -> int | None:
    """1-based day of Ramadan, or None outside Ramadan."""
    start, eid = RAMADAN.get(d.year, (None, None))
    if start is None or not (start <= d < eid):
        return None
    return (d - start).days + 1


def lebaran_day(d: date) -> int | None:
    """1 or 2 on the two Idulfitri public holidays (1-2 Syawal), else None."""
    _, eid = RAMADAN.get(d.year, (None, None))
    if eid is None or not (eid <= d <= eid + timedelta(days=1)):
        return None
    return (d - eid).days + 1


def is_harbolnas(d: date) -> bool:
    """National Online Shopping Day (11.11) and its 12.12 follow-up."""
    return (d.month, d.day) in {(11, 11), (12, 12)}


def holiday_name(d: date) -> str | None:
    if lebaran_day(d):
        return "Idulfitri (Lebaran)"
    if ramadan_day(d) == 1:
        return "Awal Ramadan"
    fixed = {
        (1, 1): "Tahun Baru",
        (8, 17): "Hari Kemerdekaan",
        (11, 11): "Harbolnas 11.11",
        (12, 12): "Harbolnas 12.12",
        (12, 25): "Natal",
    }
    return fixed.get((d.month, d.day))


def days(start: date, end: date):
    """Inclusive date range."""
    for i in range((end - start).days + 1):
        yield start + timedelta(days=i)


def calendar_rows() -> list[tuple]:
    rows = []
    for d in days(CALENDAR_START, CALENDAR_END):
        iso_dow = d.isoweekday()
        rows.append(
            (
                d,
                d.year,
                (d.month - 1) // 3 + 1,
                d.month,
                MONTH_NAMES[d.month - 1],
                d.day,
                iso_dow,
                DAY_NAMES[iso_dow - 1],
                iso_dow >= 6,
                fiscal_year(d),
                fiscal_quarter(d),
                fiscal_month(d),
                ramadan_day(d) is not None,
                lebaran_day(d) is not None,
                is_harbolnas(d),
                holiday_name(d),
            )
        )
    return rows


CALENDAR_COLUMNS = (
    "date_key", "year", "quarter", "month", "month_name", "day_of_month", "iso_day_of_week",
    "day_name", "is_weekend", "fiscal_year", "fiscal_quarter", "fiscal_month",
    "is_ramadan", "is_lebaran", "is_harbolnas", "holiday_name",
)  # fmt: skip
