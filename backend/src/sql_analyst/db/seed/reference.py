"""Small fixed reference data: regions, channels, stores, categories, brands, promotions.

Store names use real Indonesian neighbourhood names for flavour; the company and
its stores are fictional.
"""

from datetime import date, timedelta

from sql_analyst.db.calendar import DATA_END, DATA_START, RAMADAN

# region_id, city, province, region_group, island, city_code
REGIONS = [
    (1, "Jakarta", "DKI Jakarta", "Jabodetabek", "Jawa", "JKT"),
    (2, "Bogor", "Jawa Barat", "Jabodetabek", "Jawa", "BGR"),
    (3, "Depok", "Jawa Barat", "Jabodetabek", "Jawa", "DPK"),
    (4, "Tangerang", "Banten", "Jabodetabek", "Jawa", "TNG"),
    (5, "Bekasi", "Jawa Barat", "Jabodetabek", "Jawa", "BKS"),
    (6, "Bandung", "Jawa Barat", "Jawa Barat", "Jawa", "BDG"),
    (7, "Semarang", "Jawa Tengah", "Jawa Tengah & DIY", "Jawa", "SMG"),
    (8, "Yogyakarta", "DI Yogyakarta", "Jawa Tengah & DIY", "Jawa", "YGY"),
    (9, "Surabaya", "Jawa Timur", "Jawa Timur", "Jawa", "SBY"),
    (10, "Denpasar", "Bali", "Bali", "Bali", "DPS"),
    (11, "Medan", "Sumatera Utara", "Sumatera", "Sumatera", "MDN"),
    (12, "Makassar", "Sulawesi Selatan", "Sulawesi", "Sulawesi", "MKS"),
]
CITY_CODE = {r[0]: r[5] for r in REGIONS}
CITY_NAME = {r[0]: r[1] for r in REGIONS}
# Share of customers living in each region (Jabodetabek-heavy, like most retailers).
CUSTOMER_REGION_WEIGHTS = {
    1: 22,
    2: 5,
    3: 5,
    4: 9,
    5: 7,
    6: 10,
    7: 7,
    8: 5,
    9: 13,
    10: 5,
    11: 6,
    12: 6,
}
# Delivery days for online orders, by destination region (min, max).
DELIVERY_DAYS = {
    1: (1, 2),
    2: (1, 3),
    3: (1, 3),
    4: (1, 3),
    5: (1, 3),
    6: (2, 4),
    7: (2, 4),
    8: (2, 4),
    9: (2, 4),
    10: (2, 5),
    11: (3, 6),
    12: (3, 7),
}

# channel_id, channel_code, channel_name, is_online
CHANNELS = [
    (1, "store", "Physical store", False),
    (2, "website", "Website", True),
    (3, "app", "Mobile app", True),
    (4, "marketplace", "Marketplace", True),
]
STORE, WEBSITE, APP, MARKETPLACE = 1, 2, 3, 4

# (region_id, neighbourhood, format, floor m2, opened, closed)
_STORE_SPECS = [
    (1, "Senayan", "flagship", 2400, date(2016, 5, 14), None),
    (1, "Kelapa Gading", "mall", 1300, date(2017, 3, 2), None),
    (1, "Kemang", "street", 650, date(2018, 8, 20), None),
    (1, "Puri Indah", "mall", 1200, date(2018, 11, 3), None),
    (1, "Pondok Indah", "mall", 1400, date(2019, 2, 9), None),
    (1, "Cikini", "street", 500, date(2019, 9, 12), None),
    (1, "Sunter", "mall", 1000, date(2020, 1, 18), None),
    (1, "Tebet", "street", 550, date(2021, 7, 1), None),
    (1, "Cempaka Putih", "mall", 900, date(2022, 4, 22), None),
    (2, "Pajajaran", "mall", 900, date(2019, 6, 15), None),
    (2, "Cibinong", "mall", 850, date(2022, 10, 1), None),
    (3, "Margonda", "mall", 1000, date(2018, 12, 8), None),
    (3, "Cinere", "street", 600, date(2021, 3, 27), None),
    (4, "BSD", "mall", 1500, date(2017, 10, 10), None),
    (4, "Alam Sutera", "mall", 1100, date(2019, 4, 6), None),
    (4, "Karawaci", "mall", 1000, date(2020, 8, 15), None),
    (4, "Gading Serpong", "mall", 1100, date(2025, 2, 14), None),
    (5, "Summarecon", "mall", 1200, date(2018, 6, 30), None),
    (5, "Harapan Indah", "street", 600, date(2021, 11, 13), None),
    (5, "Cikarang", "mall", 900, date(2023, 5, 20), None),
    (6, "Dago", "street", 700, date(2017, 7, 7), None),
    (6, "Pasirkaliki", "mall", 1300, date(2018, 3, 17), None),
    (6, "Buah Batu", "street", 550, date(2020, 2, 29), None),
    (6, "Antapani", "mall", 950, date(2024, 9, 7), None),
    (7, "Simpang Lima", "mall", 1200, date(2018, 9, 1), None),
    (7, "Tembalang", "street", 500, date(2021, 1, 23), None),
    (7, "Banyumanik", "mall", 800, date(2022, 8, 6), None),
    (8, "Malioboro", "street", 750, date(2019, 5, 25), None),
    (8, "Seturan", "mall", 900, date(2021, 10, 9), None),
    (9, "Tunjungan", "flagship", 2000, date(2016, 11, 19), None),
    (9, "Darmo", "street", 600, date(2018, 4, 14), None),
    (9, "Pakuwon", "mall", 1500, date(2019, 7, 27), None),
    (9, "Rungkut", "street", 500, date(2021, 5, 15), None),
    (9, "Kenjeran", "mall", 850, date(2023, 2, 11), None),
    (10, "Renon", "mall", 1000, date(2019, 3, 30), None),
    (10, "Sanur", "street", 600, date(2022, 6, 18), None),
    (11, "Kesawan", "street", 650, date(2019, 10, 19), date(2025, 6, 30)),
    (11, "Setiabudi", "mall", 1100, date(2020, 12, 5), None),
    (12, "Panakkukang", "mall", 1100, date(2020, 3, 7), None),
    (12, "Losari", "street", 550, date(2022, 9, 24), None),
]
FORMAT_WEIGHT = {"flagship": 2.2, "mall": 1.2, "street": 0.8}


def stores() -> list[tuple]:
    """store_id, store_code, store_name, region_id, store_format, floor_area_m2, opened, closed."""
    rows, per_city = [], {}
    for i, (region_id, hood, fmt, area, opened, closed) in enumerate(_STORE_SPECS, start=1):
        per_city[region_id] = per_city.get(region_id, 0) + 1
        code = f"ST-{CITY_CODE[region_id]}-{per_city[region_id]:02d}"
        name = f"Arunika {CITY_NAME[region_id]} {hood}"
        rows.append((i, code, name, region_id, fmt, area, opened, closed))
    return rows


# Top-level categories: (id, English, Indonesian, order weight, (min, max) price IDR)
TOP_CATEGORIES = [
    (1, "Electronics", "Elektronik", 18, (150_000, 12_000_000)),
    (2, "Home Appliances", "Peralatan Rumah Tangga", 10, (200_000, 5_000_000)),
    (3, "Fashion", "Fashion", 20, (80_000, 900_000)),
    (4, "Beauty & Personal Care", "Kecantikan & Perawatan Diri", 16, (30_000, 600_000)),
    (5, "Home & Living", "Rumah & Dekorasi", 8, (100_000, 6_000_000)),
    (6, "Groceries", "Bahan Makanan", 14, (10_000, 150_000)),
    (7, "Baby & Kids", "Ibu & Anak", 8, (25_000, 1_200_000)),
    (8, "Sports & Outdoors", "Olahraga & Outdoor", 6, (50_000, 3_000_000)),
]
# Leaf categories: (id, parent id, English, Indonesian, product nouns)
LEAF_CATEGORIES = [
    (11, 1, "Smartphones", "Ponsel", ["Smartphone", "Phone Lite", "Phone Pro"]),
    (12, 1, "Audio", "Audio", ["Wireless Earbuds", "Bluetooth Speaker", "Headphones"]),
    (
        13,
        1,
        "Computers & Accessories",
        "Komputer & Aksesori",
        ["Laptop", "Wireless Mouse", "Mechanical Keyboard", "Power Bank", "USB-C Hub"],
    ),
    (
        21,
        2,
        "Kitchen Appliances",
        "Peralatan Dapur",
        ["Rice Cooker", "Blender", "Air Fryer", "Electric Kettle"],
    ),
    (
        22,
        2,
        "Cleaning Appliances",
        "Peralatan Kebersihan",
        ["Vacuum Cleaner", "Steam Iron", "Cordless Vacuum"],
    ),
    (31, 3, "Men's Clothing", "Pakaian Pria", ["Batik Shirt", "Polo Shirt", "Chino Pants"]),
    (32, 3, "Women's Clothing", "Pakaian Wanita", ["Blouse", "Midi Dress", "Culottes"]),
    (33, 3, "Muslim Wear", "Busana Muslim", ["Koko Shirt", "Gamis", "Hijab", "Mukena", "Sarung"]),
    (41, 4, "Skincare", "Perawatan Kulit", ["Facial Wash", "Moisturizer", "Sunscreen", "Serum"]),
    (42, 4, "Makeup", "Tata Rias", ["Lip Cream", "Cushion Foundation", "Mascara"]),
    (51, 5, "Furniture", "Furnitur", ["Study Desk", "Bookshelf", "Office Chair"]),
    (52, 5, "Bedding", "Perlengkapan Tidur", ["Bed Sheet Set", "Pillow", "Blanket"]),
    (61, 6, "Snacks", "Makanan Ringan", ["Kerupuk", "Kue Kering", "Keripik", "Nastar"]),
    (62, 6, "Beverages", "Minuman", ["Ground Coffee", "Syrup", "Tea Bags", "Kurma Juice"]),
    (71, 7, "Baby Care", "Perawatan Bayi", ["Baby Diapers", "Baby Lotion", "Baby Wipes"]),
    (72, 7, "Toys", "Mainan", ["Building Blocks", "Puzzle", "RC Car"]),
    (
        81,
        8,
        "Sports Equipment",
        "Peralatan Olahraga",
        ["Yoga Mat", "Badminton Racket", "Running Shoes", "Dumbbell Set"],
    ),
]
BRANDS = {
    1: ["Nusantech", "Volta", "Sora", "Kirana"],
    2: ["Dapura", "Kilau", "Hemat+"],
    3: ["Batara", "Laksmi", "Rupa"],
    4: ["Sekar", "Ayu Lab", "Melati"],
    5: ["Rumahku", "Jati Living"],
    6: ["Rasa Nusa", "Kopi Senja", "Sari Buah"],
    7: ["Bunda Care", "Si Kecil"],
    8: ["Garuda Sport", "Lari"],
}
SUPPLIERS_PER_TOP = 3

PAYMENT_METHODS = {
    STORE: (["cash", "card", "qris", "ewallet"], [25, 30, 30, 15]),
    WEBSITE: (["ewallet", "qris", "card", "bank_transfer", "cod"], [30, 15, 15, 25, 15]),
    APP: (["ewallet", "qris", "card", "bank_transfer", "cod"], [38, 17, 12, 20, 13]),
    MARKETPLACE: (["ewallet", "card", "bank_transfer", "cod"], [40, 15, 25, 20]),
}
COURIERS = (["JNE", "J&T Express", "SiCepat", "AnterAja", "GoSend"], [30, 28, 20, 12, 10])
RETURN_REASONS = (
    ["damaged", "wrong_item", "not_as_described", "size_issue", "changed_mind"],
    [25, 15, 25, 20, 15],
)


def promotions() -> list[tuple]:
    """promotion_id, promo_code, promo_name, promo_type, discount_pct, channel_scope, start, end."""
    specs = []
    for year in (2024, 2025, 2026):
        start, eid = RAMADAN[year]
        yy = str(year)[2:]
        specs.append(
            (
                f"RAMADAN{yy}",
                f"Ramadan Sale {year}",
                "seasonal",
                15,
                "all",
                start,
                eid - timedelta(days=1),
            )
        )
        specs.append(
            (
                f"MERDEKA{yy}",
                f"Promo Kemerdekaan 17.08 {year}",
                "seasonal",
                17,
                "all",
                date(year, 8, 14),
                date(year, 8, 18),
            )
        )
        specs.append(
            (
                f"SEKOLAH{yy}",
                f"Back to School {year}",
                "seasonal",
                10,
                "all",
                date(year, 7, 1),
                date(year, 7, 14),
            )
        )
        specs.append(
            (
                f"FLASH99-{yy}",
                f"Flash Sale 9.9 {year}",
                "flash_sale",
                15,
                "online",
                date(year, 9, 9),
                date(year, 9, 9),
            )
        )
        if year < 2026:
            for code, name, pct, month in (
                ("FLASH1010", "Flash Sale 10.10", 15, 10),
                ("HARBOLNAS1111", "Harbolnas 11.11", 25, 11),
                ("HARBOLNAS1212", "Harbolnas 12.12", 20, 12),
            ):
                specs.append(
                    (
                        f"{code}-{yy}",
                        f"{name} {year}",
                        "flash_sale",
                        pct,
                        "online",
                        date(year, month, month),
                        date(year, month, month),
                    )
                )
            specs.append(
                (
                    f"YEAREND{yy}",
                    f"Year End Sale {year}",
                    "seasonal",
                    10,
                    "all",
                    date(year, 12, 20),
                    date(year, 12, 31),
                )
            )
    d = DATA_START
    while d <= DATA_END:
        specs.append(
            (
                f"GAJIAN-{d:%Y%m}",
                f"Payday Sale {d:%b %Y}",
                "payday",
                8,
                "online",
                d.replace(day=25),
                d.replace(day=28),
            )
        )
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    specs.sort(key=lambda s: (s[5], s[0]))
    return [(i, *spec) for i, spec in enumerate(specs, start=1)]
