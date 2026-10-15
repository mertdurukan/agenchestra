"""Ret nedeni sözlüğü: denetim kaydındaki 'neden' kodları ve kök eşlemesi. Başka modüle bağımlı değildir."""
from __future__ import annotations

SINIFLANMAMIS = "siniflanmamis"

NEDENLER = {
    "kapsam-eksik": "Kabul kriterlerinden biri ya da bir kısmı yapılmamış.",
    "bicim": "Çıktının biçimi (dosya yapısı, şema, adlandırma) istenene uymuyor.",
    "sayi-tutarsiz": "Sayılar kendi içinde ya da kaynakla tutarsız.",
    "kanit-yok": "İddia için dosya:satır, komut çıktısı gibi kanıt verilmemiş.",
    "talimat-ihlali": "Kart ya da protokol talimatı (yazma alanı, test dosyası vb.) çiğnenmiş.",
    "kriter-belirsiz": "Kabul kriteri belirsiz ya da çelişkili; kart yeniden yazılmalı.",
    "yetenek-yetersiz": "İşçi basamağının yeteneği işe yetmedi; basamak yükseltilmeli.",
    "ortam": "Başarısızlık kodun değil ortamın: yük altında zamanlama, başka kartın değişikliği, eksik araç/izin; kodu ya da modeli değiştirmek çözmez.",
}

KOK = {
    "kriter-belirsiz": "kart",
    "yetenek-yetersiz": "basamak",
    "ortam": "ortam",
    "kapsam-eksik": "dikkat",
    "bicim": "dikkat",
    "sayi-tutarsiz": "dikkat",
    "kanit-yok": "dikkat",
    "talimat-ihlali": "dikkat",
}


def kok(neden) -> str:
    """Neden kodunun kökünü döner; None ya da bilinmeyen kod için 'siniflanmamis'."""
    return KOK.get(neden, SINIFLANMAMIS) if isinstance(neden, str) else SINIFLANMAMIS
