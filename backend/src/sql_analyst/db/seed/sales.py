"""Orders and everything hanging off them, generated one WIB business day at a time.

Patterns: weekday/weekend rhythm, payday (tanggal gajian), the Ramadan build-up and
the Lebaran dip, Harbolnas 11.11/12.12 online spikes, a growing online share.
Traps for the agent (documented in docs/DATA.md):
- `ordered_at` is UTC; late-night WIB orders (00:00-06:59) fall on the previous UTC date.
- cancelled orders keep their lines and must be excluded from revenue.
- `orders.region_code` is deprecated: stale for customers who moved, NULL after 2025-07-01.
- orders use `total_amount`, payments use `amount_idr`.
"""

import random
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sql_analyst.db.calendar import DATA_END, DATA_START, days, lebaran_day, ramadan_day
from sql_analyst.db.seed.catalog import Customer, Employee, Product
from sql_analyst.db.seed.common import (
    Table,
    WeightedPicker,
    poisson,
    retail_price,
    rng_for,
    round_to,
    wib_to_utc,
)
from sql_analyst.db.seed.reference import (
    APP,
    CITY_CODE,
    COURIERS,
    DELIVERY_DAYS,
    FORMAT_WEIGHT,
    LEAF_CATEGORIES,
    MARKETPLACE,
    PAYMENT_METHODS,
    RETURN_REASONS,
    STORE,
    TOP_CATEGORIES,
    WEBSITE,
)

REGION_CODE_DEPRECATED_ON = date(2025, 7, 1)
WALK_IN_SHARE = 0.4
STORE_HOURS = list(range(10, 22))
STORE_HOUR_WEIGHTS = [5, 7, 10, 10, 7, 6, 7, 9, 11, 11, 8, 4]
ONLINE_HOUR_WEIGHTS = [3, 2, 1, 1, 1, 1, 2, 3, 4, 5, 6, 7, 9, 8, 7, 6, 6, 7, 8, 10, 11, 10, 8, 5]
SAHUR_BOOST = {2: 4, 3: 6, 4: 4}  # online shopping around the pre-dawn meal in Ramadan
SESSIONS_PER_CONVERSION = 11  # non-converted sessions per order: ~8% conversion


@dataclass
class OrderInfo:
    """What later generators (tickets) need to know about an online order."""

    order_id: int
    order_number: str
    customer_id: int
    ordered_at: datetime
    status: str
    courier: str | None
    has_return: bool


@dataclass
class SalesResult:
    tables: list[Table]
    online_orders: list[OrderInfo] = field(default_factory=list)
    store_day_lambda: dict[tuple[int, date], float] = field(default_factory=dict)
    store_month_net: dict[tuple[int, date], int] = field(default_factory=dict)


def _day_factors(d: date) -> tuple[float, float]:
    """Relative order volume for (stores, online) on business day d."""
    growth = 1.15 ** ((d - DATA_START).days / 365)
    dow = d.isoweekday()
    store = {5: 1.1, 6: 1.35, 7: 1.3}.get(dow, 0.9)
    online = {6: 1.05, 7: 1.15}.get(dow, 1.0)
    if d.day >= 25 or d.day == 1:  # payday
        store, online = store * 1.1, online * 1.2
    if rd := ramadan_day(d):
        boost = 1.1 + 0.6 * rd / 30
        store, online = store * boost, online * boost
    if lebaran_day(d):
        store, online = store * 0.35, online * 0.5
    elif any(lebaran_day(d - timedelta(days=k)) for k in range(2, 7)):  # mudik week
        store, online = store * 0.8, online * 0.85
    md = (d.month, d.day)
    online *= {
        (11, 11): 5.0,
        (12, 12): 4.0,
        (9, 9): 2.5,
        (10, 10): 2.5,
        (11, 10): 0.8,
        (12, 11): 0.8,
    }.get(md, 1.0)
    if d.month == 12 and d.day >= 20:
        store *= 1.3
    if d.month == 8 and 14 <= d.day <= 18:
        store, online = store * 1.2, online * 1.2
    return store * growth, online * growth


def _online_share(d: date) -> float:
    return 0.32 + 0.23 * (d - DATA_START).days / (DATA_END - DATA_START).days


def _online_channel_shares(d: date) -> dict[int, float]:
    t = (d - DATA_START).days / (DATA_END - DATA_START).days
    app, web = 0.35 + 0.12 * t, 0.33 - 0.06 * t
    return {WEBSITE: web, APP: app, MARKETPLACE: 1 - app - web}


def _leaf_weights(d: date) -> dict[int, float]:
    tops = {t[0]: t[3] for t in TOP_CATEGORIES}
    n_leaves = defaultdict(int)
    for _, parent, *_ in LEAF_CATEGORIES:
        n_leaves[parent] += 1
    weights = {}
    for leaf_id, parent, *_ in LEAF_CATEGORIES:
        w = tops[parent] / n_leaves[parent]
        if ramadan_day(d) or lebaran_day(d):
            w *= {33: 5.0, 61: 2.2, 62: 2.0}.get(leaf_id, 1.3 if parent == 3 else 1.0)
        if (d.month, d.day) in {(11, 11), (12, 12), (9, 9), (10, 10)} and parent == 1:
            w *= 1.8
        if d.month == 7 and leaf_id == 13:
            w *= 1.5
        if d.month == 12 and leaf_id == 72:
            w *= 1.6
        weights[leaf_id] = w
    return weights


class _CustomerPicker:
    """Picks returning customers who had already signed up on a given day."""

    def __init__(self, rng: random.Random, customers: list[Customer]):
        self.customers = customers  # sorted by signup
        self.signups = [c.signup for c in customers]
        weights = [rng.paretovariate(1.3) * (2.5 if c.segment == "vip" else 1.0) for c in customers]
        self.picker = WeightedPicker(customers, weights)

    def pick(self, rng: random.Random, d: date) -> Customer | None:
        n = bisect_right(self.signups, d)
        return self.picker.pick(rng, n) if n else None


def generate_sales(
    seed: int,
    scale: float,
    store_rows: list[tuple],
    products: list[Product],
    customers: list[Customer],
    employees: list[Employee],
    promo_rows: list[tuple],
) -> SalesResult:
    rng = rng_for(seed, "sales")
    target_orders = 60_000 * scale

    # Calibrate the base daily volume so the expected total is ~60k orders.
    all_days = list(days(DATA_START, DATA_END))
    factors = {d: _day_factors(d) for d in all_days}
    expected = sum(
        (1 - _online_share(d)) * f[0] + _online_share(d) * f[1] for d, f in factors.items()
    )
    base = target_orders / expected

    stores = {s[0]: s for s in store_rows}
    store_weight = {s[0]: FORMAT_WEIGHT[s[4]] for s in store_rows}
    global_customers = _CustomerPicker(rng, customers)
    regional_customers = {
        rid: _CustomerPicker(rng, [c for c in customers if c.region_id == rid])
        for rid in sorted({c.region_id for c in customers})
    }
    sellers = defaultdict(list)
    for e in employees:
        if e.role == "sales_associate":
            sellers[e.store_id].append(e)
    products_by_leaf = defaultdict(list)
    for p in products:
        products_by_leaf[p.leaf_id].append(p)
    promos_by_day = defaultdict(list)
    for promo in promo_rows:
        for d in days(promo[6], promo[7]):
            promos_by_day[d].append(promo)

    t_orders = Table(
        "orders",
        "order_id order_number customer_id store_id channel_id sales_employee_id ordered_at status total_amount region_code",
    )
    t_items = Table(
        "order_items",
        "order_item_id order_id line_number product_id quantity unit_price_idr discount_idr",
    )
    t_pay = Table(
        "payments",
        "payment_id order_id payment_method payment_status amount_idr paid_at",
    )
    t_ret = Table(
        "returns",
        "return_id order_item_id order_id returned_at quantity reason refund_amount_idr",
    )
    t_ship = Table(
        "shipments",
        "shipment_id order_id courier destination_region_id shipping_fee_idr shipped_at delivered_at shipment_status",
    )
    t_red = Table(
        "promotion_redemptions",
        "redemption_id promotion_id order_id discount_idr redeemed_at",
    )
    t_sess = Table(
        "web_sessions",
        "session_id channel_id customer_id started_at device_type traffic_source viewed_product added_to_cart reached_checkout converted order_id",
    )
    result = SalesResult([t_orders, t_items, t_pay, t_ret, t_ship, t_red, t_sess])
    data_end_utc = wib_to_utc(DATA_END + timedelta(days=1), 0)  # first moment after the data
    refund_cutoff = DATA_END - timedelta(days=30)

    for d in all_days:
        store_f, online_f = factors[d]
        share = _online_share(d)
        open_stores = [s for s in store_rows if s[6] <= d and (s[7] is None or d <= s[7])]
        open_by_region = defaultdict(list)
        for s in open_stores:
            open_by_region[s[3]].append(s[0])
        store_picker = WeightedPicker(
            [s[0] for s in open_stores], [store_weight[s[0]] for s in open_stores]
        )
        lam_store = base * (1 - share) * store_f
        total_w = sum(store_weight[s[0]] for s in open_stores)
        for s in open_stores:
            result.store_day_lambda[(s[0], d)] = lam_store * store_weight[s[0]] / total_w

        leaf_w = _leaf_weights(d)
        leaf_picker = WeightedPicker(list(leaf_w), list(leaf_w.values()))
        product_pickers = {}
        for leaf_id, plist in products_by_leaf.items():
            avail = [
                p
                for p in plist
                if p.launched <= d and (p.discontinued is None or d <= p.discontinued)
            ]
            if avail:
                product_pickers[leaf_id] = WeightedPicker(avail, [p.popularity for p in avail])

        # 1) decide the day's orders: (seconds_of_day, channel, store_id, customer)
        specs = []
        for _ in range(poisson(rng, lam_store)):
            store_id = store_picker.pick(rng)
            cust = None
            if rng.random() > WALK_IN_SHARE:
                cust = regional_customers[stores[store_id][3]].pick(rng, d)
            specs.append((_store_second(rng), STORE, store_id, cust))
        for channel, ch_share in _online_channel_shares(d).items():
            for _ in range(poisson(rng, base * share * online_f * ch_share)):
                cust = global_customers.pick(rng, d)
                if cust is None:
                    continue
                store_id = rng.choice(open_by_region[cust.region_id])
                specs.append((_online_second(rng, d), channel, store_id, cust))
        specs.sort(key=lambda s: s[0])

        # 2) materialise each order with its lines, payment, shipment, returns
        day_sessions = []
        for seq, (second, channel, store_id, cust) in enumerate(specs, start=1):
            order_id = len(t_orders.rows) + 1
            ordered_at = wib_to_utc(d, second)
            online = channel != STORE
            method = rng.choices(*PAYMENT_METHODS[channel])[0]

            p_cancel = (
                0.01
                if not online
                else 0.04 + 0.04 * (channel == MARKETPLACE) + 0.08 * (method == "cod")
            )
            status = "completed"
            if rng.random() < p_cancel:
                status = "cancelled"
            elif d <= refund_cutoff and rng.random() < (0.01 if not online else 0.02):
                status = "refunded"

            promo = None
            for p in promos_by_day.get(d, []):
                if (p[5] == "all" or online) and (promo is None or p[4] > promo[4]):
                    promo = p
            use_promo = promo is not None and rng.random() < (
                0.8 if promo[3] == "flash_sale" else 0.5
            )

            lines, promo_discount = [], 0
            for _ in range(rng.choices([1, 2, 3, 4, 5, 6], [35, 25, 18, 12, 6, 4])[0]):
                leaf = leaf_picker.pick(rng)
                if leaf not in product_pickers:
                    continue
                prod = product_pickers[leaf].pick(rng)
                if prod.top_id in (4, 6):
                    qty = rng.choices([1, 2, 3, 4], [50, 25, 15, 10])[0]
                else:
                    qty = rng.choices([1, 2], [88, 12])[0]
                price = (
                    prod.list_price
                    if channel != MARKETPLACE
                    else retail_price(prod.list_price * 0.97)
                )
                discount = 0
                if use_promo:
                    discount = round_to(qty * price * promo[4] / 100, 100)
                    promo_discount += discount
                elif cust is not None and cust.segment == "vip":
                    discount = round_to(qty * price * 0.05, 100)
                elif rng.random() < 0.04:  # clearance markdown
                    discount = round_to(qty * price * 0.10, 100)
                lines.append(
                    (
                        len(t_items.rows) + len(lines) + 1,
                        order_id,
                        len(lines) + 1,
                        prod.product_id,
                        qty,
                        price,
                        discount,
                    )
                )
            if not lines:
                continue
            total = sum(q * p - disc for *_, q, p, disc in lines)
            t_items.rows.extend(lines)

            region_code = None
            if d < REGION_CODE_DEPRECATED_ON:
                if cust is None:
                    region_code = CITY_CODE[stores[store_id][3]]
                elif rng.random() < 0.07:  # customer moved; the code was never updated
                    region_code = rng.choice(
                        sorted(set(CITY_CODE.values()) - {CITY_CODE[cust.region_id]})
                    )
                else:
                    region_code = CITY_CODE[cust.region_id]
            seller = None
            if not online:
                active = [e for e in sellers[store_id] if e.active_on(d)]
                seller = rng.choice(active).employee_id if active else None
            t_orders.rows.append(
                (
                    order_id,
                    f"ORD-{d:%Y%m%d}-{seq:04d}",
                    cust.customer_id if cust else None,
                    store_id,
                    channel,
                    seller,
                    ordered_at,
                    status,
                    total,
                    region_code,
                )
            )

            delivered_at, courier = None, None
            if online and status != "cancelled":
                courier = rng.choices(*COURIERS)[0]
                shipped_at = ordered_at + timedelta(seconds=rng.randint(4 * 3600, 40 * 3600))
                lo, hi = DELIVERY_DAYS[cust.region_id]
                delivered_at = shipped_at + timedelta(
                    days=rng.randint(lo, hi), seconds=rng.randint(0, 36_000)
                )
                ship_status = "delivered"
                if shipped_at >= data_end_utc:
                    shipped_at, delivered_at, ship_status = ordered_at, None, "in_transit"
                elif delivered_at >= data_end_utc:
                    delivered_at, ship_status = None, "in_transit"
                fee = round_to(
                    8_000 + 2_500 * DELIVERY_DAYS[cust.region_id][1] * rng.uniform(0.8, 1.3), 500
                )
                t_ship.rows.append(
                    (
                        len(t_ship.rows) + 1,
                        order_id,
                        courier,
                        cust.region_id,
                        fee,
                        shipped_at,
                        delivered_at,
                        ship_status,
                    )
                )

            if status == "cancelled":
                pay_status, paid_at = "voided", None
            elif method == "cod":
                pay_status = (
                    "refunded" if status == "refunded" else ("paid" if delivered_at else "pending")
                )
                paid_at = delivered_at
            else:
                pay_status = "refunded" if status == "refunded" else "paid"
                paid_at = (
                    ordered_at
                    if not online
                    else ordered_at + timedelta(seconds=rng.randint(30, 900))
                )
            t_pay.rows.append((len(t_pay.rows) + 1, order_id, method, pay_status, total, paid_at))

            refunds = 0
            if status != "cancelled":
                base_time = delivered_at or ordered_at
                for item_id, _, _, _, qty, price, disc in lines:
                    if status == "refunded":
                        ret_qty = qty
                    elif rng.random() < 0.035:
                        ret_qty = rng.randint(1, qty)
                    else:
                        continue
                    returned_at = base_time + timedelta(
                        days=rng.randint(1, 7), seconds=rng.randint(0, 30_000)
                    )
                    if returned_at >= data_end_utc:
                        if status == "refunded":
                            returned_at = data_end_utc - timedelta(hours=1)
                        else:
                            continue
                    amount = round((qty * price - disc) * ret_qty / qty)
                    refunds += amount
                    t_ret.rows.append(
                        (
                            len(t_ret.rows) + 1,
                            item_id,
                            order_id,
                            returned_at,
                            ret_qty,
                            rng.choices(*RETURN_REASONS)[0],
                            amount,
                        )
                    )
                if use_promo and promo_discount:
                    t_red.rows.append(
                        (len(t_red.rows) + 1, promo[0], order_id, promo_discount, ordered_at)
                    )
                month = d.replace(day=1)
                result.store_month_net[(store_id, month)] = (
                    result.store_month_net.get((store_id, month), 0) + total - refunds
                )

            if online:
                result.online_orders.append(
                    OrderInfo(
                        order_id,
                        t_orders.rows[-1][1],
                        cust.customer_id,
                        ordered_at,
                        status,
                        courier,
                        refunds > 0,
                    )
                )
            if channel in (WEBSITE, APP):
                day_sessions.append(
                    _session(
                        rng,
                        channel,
                        cust.customer_id,
                        ordered_at - timedelta(seconds=rng.randint(180, 2400)),
                        order_id,
                    )
                )
                for _ in range(poisson(rng, SESSIONS_PER_CONVERSION)):
                    browser = global_customers.pick(rng, d) if rng.random() < 0.45 else None
                    day_sessions.append(
                        _session(
                            rng,
                            channel,
                            browser.customer_id if browser else None,
                            wib_to_utc(d, _online_second(rng, d)),
                            None,
                        )
                    )

        day_sessions.sort(key=lambda s: (s[2], s[0]))
        for s in day_sessions:
            t_sess.rows.append((len(t_sess.rows) + 1, *s))

    return result


def _store_second(rng: random.Random) -> int:
    hour = rng.choices(STORE_HOURS, STORE_HOUR_WEIGHTS)[0]
    return hour * 3600 + rng.randint(0, 3599)


def _online_second(rng: random.Random, d: date) -> int:
    if (d.month, d.day) in {(11, 11), (12, 12)} and rng.random() < 0.3:
        hour = rng.choice([0, 0, 1])  # the midnight rush when the sale opens
    else:
        weights = ONLINE_HOUR_WEIGHTS
        if ramadan_day(d):
            weights = [w + SAHUR_BOOST.get(h, 0) for h, w in enumerate(weights)]
        hour = rng.choices(range(24), weights)[0]
    return hour * 3600 + rng.randint(0, 3599)


def _session(
    rng: random.Random,
    channel: int,
    customer_id: int | None,
    started_at: datetime,
    order_id: int | None,
) -> tuple:
    """channel_id, customer_id, started_at, device, source, funnel flags..., order_id."""
    if channel == APP:
        device = rng.choices(["mobile", "tablet"], [88, 12])[0]
        source = rng.choices(["direct", "push_notification", "social", "email"], [55, 20, 15, 10])[
            0
        ]
    else:
        device = rng.choices(["mobile", "desktop", "tablet"], [60, 35, 5])[0]
        source = rng.choices(
            ["organic_search", "paid_search", "social", "direct", "email", "affiliate"],
            [30, 15, 20, 20, 7, 8],
        )[0]
    if order_id is not None:
        flags = (True, True, True, True)
    else:
        viewed = rng.random() < 0.72
        cart = viewed and rng.random() < 0.30
        checkout = cart and rng.random() < 0.45
        flags = (viewed, cart, checkout, False)
    return (channel, customer_id, started_at, device, source, *flags, order_id)
