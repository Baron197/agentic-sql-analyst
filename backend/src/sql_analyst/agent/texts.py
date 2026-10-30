"""User-facing sentences written by code (refusals, fallbacks, caveats), in English and Indonesian."""

from typing import Literal

Lang = Literal["en", "id"]

_TEXTS: dict[str, dict[Lang, str]] = {
    "refuse_unsafe": {
        "en": "I can't help with that. This assistant only reads business data: it never "
        "changes data or shows personal information.",
        "id": "Maaf, saya tidak bisa membantu permintaan itu. Asisten ini hanya membaca data "
        "bisnis: tidak pernah mengubah data atau menampilkan data pribadi.",
    },
    "refuse_unanswerable": {
        "en": "I can't answer that from the available data.",
        "id": "Maaf, pertanyaan itu tidak bisa dijawab dengan data yang tersedia.",
    },
    "refuse_invalid": {
        "en": "Please ask a shorter question about the company's data.",
        "id": "Silakan ajukan pertanyaan yang lebih singkat tentang data perusahaan.",
    },
    "table_only": {
        "en": "Here is the result of the query ({{row_count}} rows).",
        "id": "Berikut hasil kuerinya ({{row_count}} baris).",
    },
    "error": {
        "en": "I couldn't build a working query for this question. Try rephrasing it.",
        "id": "Saya tidak berhasil menyusun kueri yang valid untuk pertanyaan ini. Coba ubah "
        "kalimatnya.",
    },
    "stopped": {
        "en": "I stopped before finishing: {reason}.",
        "id": "Saya berhenti sebelum selesai: {reason}.",
    },
    "caveat_truncated": {
        "en": "The result was cut off at the row limit; totals over all rows may be incomplete.",
        "id": "Hasil dipotong pada batas jumlah baris; total dari semua baris mungkin tidak lengkap.",
    },
    "caveat_empty": {
        "en": "No rows matched the question.",
        "id": "Tidak ada baris yang cocok dengan pertanyaan.",
    },
    "caveat_fallback": {
        "en": "The written answer could not be verified, so only the table is shown.",
        "id": "Jawaban tertulis tidak dapat diverifikasi, jadi hanya tabel yang ditampilkan.",
    },
    "caveat_retry_failed": {
        "en": "A retry to improve the query failed; this is the first result.",
        "id": "Percobaan memperbaiki kueri gagal; ini adalah hasil pertama.",
    },
    "caveat_stopped": {
        "en": "The run stopped early ({reason}); only the table is shown.",
        "id": "Proses berhenti lebih awal ({reason}); hanya tabel yang ditampilkan.",
    },
}


def text(key: str, lang: Lang, **kwargs: str) -> str:
    return _TEXTS[key][lang].format(**kwargs) if kwargs else _TEXTS[key][lang]
