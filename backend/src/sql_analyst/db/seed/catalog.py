"""Catalog and people: categories, suppliers, products, customers, employees."""

import random
import re
from dataclasses import dataclass
from datetime import date, timedelta

from faker import Faker

from sql_analyst.db.calendar import DATA_END, DATA_START
from sql_analyst.db.seed.common import retail_price, rng_for
from sql_analyst.db.seed.reference import (
    BRANDS,
    CITY_NAME,
    CUSTOMER_REGION_WEIGHTS,
    LEAF_CATEGORIES,
    SUPPLIERS_PER_TOP,
    TOP_CATEGORIES,
)


def _faker(seed: int, domain: str) -> Faker:
    fake = Faker("id_ID")
    fake.seed_instance(rng_for(seed, domain).getrandbits(32))
    return fake


def _random_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _slug(name: str) -> str:
    """'Balidin Dongoran, S.T.' -> 'balidin.dongoran' (titles and degrees dropped)."""
    words = re.sub(r"[^a-z ]", "", name.split(",")[0].lower()).split()
    return ".".join(w for w in words[:2] if len(w) > 2) or "user"


def categories() -> list[tuple]:
    """category_id, parent_category_id, category_name, category_name_id, level."""
    rows = [(cid, None, en, idn, 1) for cid, en, idn, _, _ in TOP_CATEGORIES]
    rows += [(cid, parent, en, idn, 2) for cid, parent, en, idn, _ in LEAF_CATEGORIES]
    return rows


def suppliers(seed: int) -> list[tuple]:
    """supplier_id, name, region_id, lead_time_days, contact name/email/phone (PII)."""
    rng, fake = rng_for(seed, "suppliers"), _faker(seed, "suppliers")
    rows = []
    for _top in TOP_CATEGORIES:
        for _ in range(SUPPLIERS_PER_TOP):
            sid = len(rows) + 1
            contact = fake.name()
            rows.append(
                (
                    sid,
                    f"{fake.company()} ({sid:02d})",
                    rng.choice([1, 1, 1, 4, 5, 6, 9]),
                    rng.randint(3, 21),
                    contact,
                    f"{_slug(contact)}@supplier{sid:02d}.example.com",
                    fake.phone_number(),
                )
            )
    return rows


@dataclass(frozen=True)
class Product:
    product_id: int
    top_id: int
    leaf_id: int
    supplier_id: int
    unit_cost: int
    list_price: int
    launched: date
    discontinued: date | None  # last day it is sold (not stored; is_active=False)
    popularity: float


def products(seed: int) -> tuple[list[tuple], list[Product]]:
    """About 250 products. Returns table rows and lightweight objects for the sales generator."""
    rng = rng_for(seed, "products")
    top = {t[0]: t for t in TOP_CATEGORIES}
    rows, objs = [], []
    for leaf_id, top_id, _, _, nouns in LEAF_CATEGORIES:
        lo, hi = top[top_id][4]
        for _ in range(rng.randint(12, 17)):
            pid = len(rows) + 1
            brand = rng.choice(BRANDS[top_id])
            noun = rng.choice(nouns)
            model = f"{rng.choice('ABCDEFGHKMNPRSTX')}{rng.randint(1, 9)}{rng.randint(0, 9)}"
            price = retail_price(lo * (hi / lo) ** rng.random())
            cost = int(price * rng.uniform(0.55, 0.75))
            launched = _random_date(rng, date(2018, 1, 1), date(2026, 6, 30))
            if launched > DATA_START and rng.random() < 0.6:
                launched = _random_date(rng, date(2018, 1, 1), DATA_START)
            discontinued = None
            if rng.random() < 0.08:
                discontinued = _random_date(rng, max(launched, date(2024, 6, 1)), date(2026, 6, 30))
            supplier_id = (top_id - 1) * SUPPLIERS_PER_TOP + rng.randint(1, SUPPLIERS_PER_TOP)
            sku = f"{top_id}{leaf_id:02d}-{pid:04d}"
            rows.append(
                (
                    pid,
                    sku,
                    f"{brand} {noun} {model}",
                    brand,
                    leaf_id,
                    supplier_id,
                    cost,
                    price,
                    launched,
                    discontinued is None,
                )
            )
            objs.append(
                Product(
                    pid,
                    top_id,
                    leaf_id,
                    supplier_id,
                    cost,
                    price,
                    launched,
                    discontinued,
                    rng.paretovariate(1.6),
                )
            )
    return rows, objs


@dataclass(frozen=True)
class Customer:
    customer_id: int
    region_id: int
    segment: str
    signup: date


def customers(seed: int, n: int) -> tuple[list[tuple], list[Customer]]:
    """Customers sorted by signup date, so customer_id grows with signup."""
    rng, fake = rng_for(seed, "customers"), _faker(seed, "customers")
    regions = list(CUSTOMER_REGION_WEIGHTS)
    weights = list(CUSTOMER_REGION_WEIGHTS.values())
    span = (DATA_END - DATA_START).days
    specs = []
    for _ in range(n):
        if rng.random() < 0.3:
            signup = _random_date(rng, date(2021, 1, 1), DATA_START - timedelta(days=1))
        else:  # signups accelerate over time
            signup = DATA_START + timedelta(days=int(span * rng.random() ** 0.8))
        segment = rng.choices(["regular", "member", "vip"], [70, 25, 5])[0]
        specs.append((signup, rng.choices(regions, weights)[0], segment))
    specs.sort(key=lambda s: s[0])

    rows, objs = [], []
    for cid, (signup, region_id, segment) in enumerate(specs, start=1):
        gender = rng.choice(["female", "male"])
        name = fake.name_female() if gender == "female" else fake.name_male()
        address = f"{fake.street_address()}, {CITY_NAME[region_id]}"
        birth = _random_date(rng, date(1960, 1, 1), date(2006, 12, 31))
        email = f"{_slug(name)}{cid}@example.com"
        rows.append(
            (
                cid,
                name,
                email,
                fake.phone_number(),
                address,
                birth,
                gender,
                region_id,
                segment,
                signup,
            )
        )
        objs.append(Customer(cid, region_id, segment, signup))
    return rows, objs


SALARY = {
    "store_manager": (11_000_000, 16_000_000),
    "sales_associate": (5_000_000, 7_000_000),
    "cashier": (4_800_000, 6_000_000),
    "warehouse_staff": (4_800_000, 6_200_000),
    "cs_agent": (5_500_000, 8_000_000),
    "hq_analyst": (12_000_000, 20_000_000),
    "buyer": (10_000_000, 15_000_000),
}


@dataclass(frozen=True)
class Employee:
    employee_id: int
    store_id: int | None
    role: str
    hired: date
    terminated: date | None

    def active_on(self, d: date) -> bool:
        return self.hired <= d and (self.terminated is None or d <= self.terminated)


def employees(seed: int, store_rows: list[tuple]) -> tuple[list[tuple], list[Employee]]:
    """Store staff (manager, sales associates, cashiers, warehouse) plus HQ staff."""
    rng, fake = rng_for(seed, "employees"), _faker(seed, "employees")
    plan: list[tuple[int | None, str, date, date | None]] = []
    for store_id, *_, opened, closed in store_rows:
        roles = ["store_manager"] + ["sales_associate"] * rng.randint(3, 6)
        roles += ["cashier"] * 2 + ["warehouse_staff"]
        for role in roles:
            hired = max(opened, _random_date(rng, date(2015, 1, 1), date(2025, 12, 31)))
            if role == "store_manager":
                hired = opened if opened > DATA_START else min(hired, DATA_START)
            terminated = closed
            if terminated is None and role != "store_manager" and rng.random() < 0.15:
                terminated = _random_date(rng, max(hired, DATA_START), DATA_END)
            plan.append((store_id, role, hired, terminated))
        # replacements for staff who left, so stores keep sellers
        for store_emp in [p for p in plan if p[0] == store_id and p[3] and p[3] != closed]:
            if store_emp[3] < DATA_END:
                plan.append((store_id, store_emp[1], store_emp[3] + timedelta(days=14), None))
    for role, count in (("cs_agent", 18), ("hq_analyst", 8), ("buyer", 4)):
        for _ in range(count):
            plan.append((None, role, _random_date(rng, date(2016, 1, 1), date(2025, 6, 30)), None))

    rows, objs = [], []
    for eid, (store_id, role, hired, terminated) in enumerate(plan, start=1):
        name = fake.name()
        lo, hi = SALARY[role]
        rows.append(
            (
                eid,
                f"EMP-{eid:05d}",
                name,
                f"{_slug(name)}.{eid}@arunika.example.com",
                fake.phone_number(),
                store_id,
                role,
                hired,
                terminated,
                rng.randint(lo // 100_000, hi // 100_000) * 100_000,
            )
        )
        objs.append(Employee(eid, store_id, role, hired, terminated))
    return rows, objs
