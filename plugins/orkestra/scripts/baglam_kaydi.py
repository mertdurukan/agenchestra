"""Hook'un enjekte ettiği bağlamın kaydı (I-139 P2, bce F43): "ajan hangi bağlamı aldı" sorusunun cevabı.

`gunluk.jsonl`'a `tur=baglam` satırı yazar: olay, oturum, sha256 ilk 12 hane ve karakter sayısı. Bağlam metni yazılmaz
(sır ya da kişisel içerik günlüğe girmesin). Hata sessiz geçilir; hook çıktısı hiçbir durumda değişmez.
`ORKESTRA_BAGLAM_KAYDI=0` kapatır.
"""
from __future__ import annotations

import hashlib
import os

import ork_lib as L


def ozet(ek: str) -> dict:
    return {"hash": hashlib.sha256(ek.encode("utf-8")).hexdigest()[:12], "uzunluk": len(ek)}


def kaydet(sd: str | None, olay: str, oturum: str | None, ek: str | None) -> None:
    if not sd or not ek or os.environ.get("ORKESTRA_BAGLAM_KAYDI") == "0":
        return
    try:
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"),
                     {"zaman": L.simdi(), "oturum": oturum, "tur": "baglam", "olay": olay, **ozet(ek)})
    except Exception:
        pass
