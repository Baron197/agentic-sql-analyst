"""Deterministic input checks (safety layer 1) and language detection.

These run before any model call. They catch the obvious cases cheaply: empty or overlong
questions, requests to change data, requests for personal data, and prompt-injection
phrasing. Anything subtler is left to the model's refusal decision in `generate_sql`, and
every query still goes through the validator, the read-only role, and row-level security.
"""

import re
from typing import Literal

from pydantic import BaseModel

MAX_QUESTION_CHARS = 500

RefusalKind = Literal["unsafe", "unanswerable", "invalid"]


class GuardHit(BaseModel):
    kind: RefusalKind
    rule: str
    reason: str


_RULES: list[tuple[str, RefusalKind, re.Pattern[str], str]] = [
    (
        "prompt_injection",
        "unsafe",
        re.compile(
            r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|earlier|all)\b.{0,20}"
            r"\b(instructions?|rules?|prompts?)\b"
            r"|\babaikan\b.{0,30}\b(instruksi|perintah|aturan)\b"
            r"|\b(system prompt|you are now|developer mode|jailbreak)\b",
            re.IGNORECASE,
        ),
        "The question tries to override the assistant's instructions.",
    ),
    (
        "write_sql",
        "unsafe",
        re.compile(
            r"\b(drop|truncate|alter)\s+(table|schema|database|view|role|user|index)\b"
            r"|\bdelete\s+from\b|\binsert\s+into\b|\bupdate\s+[\w.]+\s+set\b"
            r"|\bcreate\s+(table|schema|role|user|view|function|index)\b"
            r"|\b(grant|revoke)\s+\w+\s+(on|to|from)\b",
            re.IGNORECASE,
        ),
        "The question contains a command that would change the database.",
    ),
    (
        "write_intent",
        "unsafe",
        re.compile(
            r"^\W*(please\s+|pls\s+|can you\s+|could you\s+|tolong\s+|mohon\s+|bisakah\s+)?"
            r"(delete|remove|erase|wipe|truncate|purge|update(?!\s+(me|on)\b)|modify|overwrite|"
            r"insert|reset|hapus|hapuskan|ubah|ganti|perbarui|tambahkan|masukkan|batalkan|"
            r"kosongkan|bersihkan)\b",
            re.IGNORECASE,
        ),
        "The question asks to change data; this assistant can only read it.",
    ),
    (
        "personal_data",
        "unsafe",
        re.compile(
            r"\b(e-?mail|email|phone|mobile|telephone|whatsapp|wa)\s+(address(es)?|numbers?|no\.?)\b"
            r"|\b(full|first|last|customer|customers'?|employee|staff)\s+names?\b"
            r"|\bnames?\s+of\s+(the\s+|our\s+|all\s+)?(customers?|employees?|staff|buyers?)\b"
            r"|\b(home|street|mailing|postal|delivery|shipping)\s+address(es)?\b"
            r"|\b(salary|salaries|wages?|payroll|passwords?|date of birth|birth ?dates?|"
            r"national id|credit card|card numbers?)\b"
            r"|\b(nama\s+(lengkap|pelanggan|customer|karyawan|pegawai|staf)|alamat(\s+email)?|"
            r"nomor\s+(hp|telepon|telp|ponsel|handphone|wa|whatsapp)|no\.?\s*(hp|telp|wa)|"
            r"gaji|upah|kata sandi|tanggal lahir|kartu kredit|nik|ktp)\b",
            re.IGNORECASE,
        ),
        "The question asks for personal data, which this assistant never returns.",
    ),
]


def check_question(question: str) -> GuardHit | None:
    """The first rule the question breaks, or None if it may go on to the agent."""
    text = question.strip()
    if not text:
        return GuardHit(kind="invalid", rule="empty", reason="The question is empty.")
    if len(text) > MAX_QUESTION_CHARS:
        return GuardHit(
            kind="invalid",
            rule="too_long",
            reason=f"The question is longer than {MAX_QUESTION_CHARS} characters.",
        )
    for rule, kind, pattern, reason in _RULES:
        if pattern.search(text):
            return GuardHit(kind=kind, rule=rule, reason=reason)
    return None


# ------------------------------------------------------------------ language
_ID_WORDS = frozenset(
    """berapa apa apakah yang di dan untuk pada bulan tahun toko mana jumlah pesanan
    pelanggan bagaimana tampilkan selama sepanjang ini itu ada dengan dari ke kategori
    penjualan pendapatan omzet omset bersih rata siapa kapan berdasarkan setiap tiap
    semua lalu kemarin minggu hari produk barang cabang kuartal fiskal dibatalkan banyak
    tertinggi terendah terbanyak paling dalam oleh atau saja hanya sudah belum metode
    pembayaran pengiriman stok pengunjung kota wilayah daerah tolong buat berikan
    sebutkan bandingkan dibanding dibandingkan masing kenaikan penurunan pertumbuhan
    pelanggan baru utama""".split()  # noqa: SIM905 (a word list reads better as text)
)
_EN_WORDS = frozenset(
    """what how many much which the in of for was were is are did does show list top by
    each last month year our me give total average who when where per during between
    across compare growth new active orders customers stores sales revenue""".split()  # noqa: SIM905 (a word list reads better as text)
)
_WORD = re.compile(r"[a-zA-Z]+")


def detect_language(question: str) -> Literal["en", "id"]:
    """'id' when the question has more Indonesian than English marker words, else 'en'."""
    words = [w.lower() for w in _WORD.findall(question)]
    id_hits = sum(w in _ID_WORDS for w in words)
    en_hits = sum(w in _EN_WORDS for w in words)
    return "id" if id_hits > en_hits else "en"
