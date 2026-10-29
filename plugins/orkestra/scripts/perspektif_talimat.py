"""Perspektif talimatı tek kaynak (ADR-0094): agents/perspektif-ajani.md'den başsız koşu istemi türetilir.

md'nin ön maddesi ve "Akış" bölümü (araç ve komut akışı: oturum içi ajana özgü) atılır; "Rapor bölümleri"
(`## 9.` ve `## 10.` dahil), "Doğrulama", "Vaat satırı", "Yayın satırı" ve "Kurallar" bölümleri birebir alınır,
başına başsız başlık (süreç etiketi, kaynak yolları) eklenir. İki kopya olmadığı için elle eşitleme gerekmez.
"""
import os
import re

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_YOLU = os.path.join(KOK, "agents", "perspektif-ajani.md")

# Başsız istemde birebir alınan bölümler (md sırasıyla). "Akış" bilerek yok.
ALINAN = ("Rapor bölümleri", "Doğrulama (P-021)", "Vaat satırı", "Yayın satırı", "Kurallar")

_BASLIK = re.compile(r"^## (?P<ad>.+?)\s*$")
_NUMARALI = re.compile(r"^\d+\.\s")


def _oku(yol: str | None = None) -> str:
    with open(yol or MD_YOLU, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def _on_madde_at(metin: str) -> str:
    """YAML ön maddeyi (`---` ... `---`) atar."""
    if metin.startswith("---\n"):
        son = metin.find("\n---\n", 4)
        if son != -1:
            return metin[son + 5:]
    return metin


def bolumler(metin: str) -> list[tuple[str, str]]:
    """[(ad, gövde)] sırayla. `## 9.` gibi numaralı başlıklar önceki bölümün (Rapor bölümleri) devamıdır.
    Gövde başlık satırını da içerir; baştaki/sondaki boş satırlar kırpılır."""
    sonuc: list[tuple[str, list[str]]] = []
    for satir in _on_madde_at(metin).split("\n"):
        m = _BASLIK.match(satir)
        if m and not (sonuc and _NUMARALI.match(m.group("ad"))):
            sonuc.append((m.group("ad"), [satir]))
        elif sonuc:
            sonuc[-1][1].append(satir)
    return [(ad, "\n".join(g).strip("\n")) for ad, g in sonuc]


def baslik(hafiza: str, proje: str, sd: str) -> str:
    return (
        "#SUREC:perspektif\n"
        "Sen orkestra sisteminin PERSPEKTİF (hafıza bakımı) koşusunsun. Kullanıcı yok; YALNIZ OKU, hiçbir dosyayı değiştirme.\n"
        "Görev: aşağıdaki kaynakları oku ve tek bir Markdown rapor üret (yanıtın yalnız rapor olsun).\n"
        "\n"
        "Kaynaklar (önce 1'i oku; sayıları yeniden hesaplama, oradan al):\n"
        f"1. Mekanik girdi: {sd}\\perspektif\\girdi.json — hafıza dosya boyutları ve MEMORY.md satır/bayt, ölü yollar, "
        "maliyet anomalileri, KPI, zaman ve trend, günlük özeti (kapı, ihlal, hata, atıf, skill/ajan kullanımı), ortak defter özeti.\n"
        f"2. Otomatik hafıza: {hafiza}  (MEMORY.md + konu dosyaları) — yalnız içerik yargısı için (kopya, çelişki, eskimiş iş).\n"
        f"3. Proje kuralları: {proje}\\CLAUDE.md ve {proje}\\.claude\\rules\\ (varsa)."
    )


def uret(hafiza: str, proje: str, sd: str, md_yolu: str | None = None) -> str:
    """Başsız perspektif istemi: başlık + md'nin ALINAN bölümleri (birebir). Bölüm bulunamazsa ValueError."""
    tum = bolumler(_oku(md_yolu))
    secilen: list[str] = []
    eksik: list[str] = []
    for ad in ALINAN:  # başlık "Vaat satırı (bölüm 6'daki ...)" gibi ek taşıyabilir: önek eşleşir
        bulunan = next((g for a, g in tum if a == ad or a.startswith(ad + " (")), None)
        if bulunan is None:
            eksik.append(ad)
        else:
            secilen.append(bulunan)
    if eksik:
        raise ValueError(f"perspektif-ajani.md bölümü yok: {', '.join(eksik)}")
    parcalar = [baslik(hafiza, proje, sd)] + secilen
    return "\n\n".join(parcalar) + "\n"
