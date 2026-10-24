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


# ---------------------------------------------------------------- hook ret sınıfı (I-224, R1–R9)
# Kök neden sınıfları: 129 kök neden analizi §2. Sınıf kayıt anında kapı kimliğinden türetilir; tabloda olmayan kapı
# 'siniflanmamis' döner (uydurma sınıf yazılmaz). Yeni kapı eklenince satırı buraya eklenir.
RET_SINIFLARI = {
    "R1": "Deterministik iş modele bırakılmış (bağlantı satırı, numara zinciri, saat, biçim).",
    "R2": "Şablon ile kapı uyuşmuyor; iskelet kendi kapısından geçemiyor.",
    "R3": "Kural yalnız ret anında ve parça parça görünüyor.",
    "R4": "Kural ya da spesifikasyon kusuru (bozuk, eski, çelişkili).",
    "R5": "Anlamsal kalite (kapsam, kanıt, ölçülemez kriter).",
    "R6": "Ajan durum makinesinde nerede olduğunu bilmeden yazıyor (sıra, onay, bağsız oturum).",
    "R7": "Ölçüm körlüğü: kök neden alanı sabit, ret bağlamı yok.",
    "R8": "Kapı sürtünmesi: yanlış pozitif ve dolanma.",
    "R9": "Serbest davranış, yapıya indirgenemeyen.",
}

KAPI_SINIF = {
    "K-003": "R1",        # belge bağlantı satırları
    "K-005": "R1",        # biçim
    "P-017": "R1",        # gap zinciri (G numaraları)
    "P-018": "R1",        # kalite alanları ve P/G zinciri
    "P-030": "R2",        # BIC bloğu iskeleti
    "P-035": "R4",        # bozuk kural metni
    "P-005": "R6",        # belge sırası
    "P-016": "R6",        # onay kapısı
    "bagsiz": "R6",       # işe bağlı olmayan oturum
    "P-010": "R8",        # kabuk kapısı yanlış pozitifi
    "denetci": "R5",      # denetçi reddi
    "P-023": "R9",        # kimlik
    "cikti_butcesi": "R9",
    "P-012": "R9",        # konu dışı
    "P-029": "R9",        # seçim ekranı
    "kapanis": "R9",
}


def ret_sinifi(kapi) -> str:
    """Kapı kimliğinin R1–R9 sınıfı; None ya da tabloda olmayan kapı için 'siniflanmamis'."""
    return KAPI_SINIF.get(kapi.strip(), SINIFLANMAMIS) if isinstance(kapi, str) else SINIFLANMAMIS
