"""Denetçi yakalama ölçümü (I-292 P5, P-030): 30 bozuk + 30 doğru işçi çıktısı, kaçırma ve yanlış ret oranı.

Vakalar tohumdan deterministik üretilir; etiket vaka metninde yoktur. Akış:
  python scripts/eval_denetci.py uret <dizin>          # NNN.md vaka istemleri (etiketsiz) yazar
  (her NNN.md bir denetci ajanına verilir; ajan tek satır döner: NNN|onay|ret|<neden>)
  python scripts/eval_denetci.py puanla <sonuclar.txt>  # kaçırma, yanlış ret, Clopper-Pearson üst sınırı
Sınır: kart ve çıktı istemde gömülüdür (CLI akışı yok); ölçülen şey denetçinin yargısıdır, kart/CLI entegrasyonu değil.
"""
from __future__ import annotations

import math
import os
import random
import sys

TOHUM = 20261031
KUSURLAR = ("kapsam-eksik", "bicim", "sayi-tutarsiz", "kanit-yok", "talimat-ihlali")
KONULAR = ["müşteri şube", "tablo satır", "API uç noktası", "log kaynağı", "rapor sayfası", "test dosyası",
           "veri kolonu", "iş akışı adımı", "skill dosyası", "ayar anahtarı"]
ISIMLER = ["alfa", "beta", "gama", "delta", "epsilon", "zeta", "eta", "teta", "iota", "kappa"]
SAHTE = {"sir": "parola: Xk93-test-ornek", "ad": "Hazırlayan: Ayşe Yılmaz", "alan": "ek dosya: ../baska_proje/ayar.json yazıldı"}


def _vaka(i: int, rng: random.Random, kusur: str | None) -> dict:
    konu = rng.choice(KONULAR)
    n = rng.randint(4, 7)
    adlar = rng.sample(ISIMLER, n)
    say = [rng.randint(3, 90) for _ in range(n)]
    kaynak = [f"{a},{s}" for a, s in zip(adlar, say)]
    satirlar = [(a, s, f"kaynak.csv:{k + 2}") for k, (a, s) in enumerate(zip(adlar, say))]
    toplam = sum(say)
    dosya_adi = f"{konu.split()[0]}_envanter_20261031.md"
    baslik = "| Ad | Adet | Kaynak |"
    ekstra: list[str] = []
    if kusur == "kapsam-eksik":
        satirlar = satirlar[:-rng.randint(1, 2)]
        toplam = sum(s for _, s, _ in satirlar)
    elif kusur == "sayi-tutarsiz":
        toplam += rng.choice([-7, -3, 4, 9, 12])
    elif kusur == "kanit-yok":
        for k in rng.sample(range(len(satirlar)), 2):
            a, s, _ = satirlar[k]
            satirlar[k] = (a, s, "—")
    elif kusur == "bicim":
        if rng.random() < 0.5:
            dosya_adi = f"{konu.split()[0]}-envanter.md"
        else:
            baslik = "Ad; Adet; Kaynak"
    elif kusur == "talimat-ihlali":
        ekstra.append(SAHTE[rng.choice(list(SAHTE))])
    tablo = [baslik] + ([] if baslik.startswith("Ad;") else ["|---|---|---|"])
    for a, s, k in satirlar:
        tablo.append(f"| {a} | {s} | {k} |" if not baslik.startswith("Ad;") else f"{a}; {s}; {k}")
    tablo.append(f"| **Toplam** | {toplam} | |" if not baslik.startswith("Ad;") else f"Toplam; {toplam};")
    cikti = "\n".join([f"# {konu.capitalize()} envanteri", ""] + tablo + [""] + ekstra)
    prompt = f"""#GOREV:EVAL-{i:03d} #SUREC:denetim
EVAL MODU: aşağıdaki kart ve çıktıyı denetle. `orkestra` komutu çalıştırma, dosya okuma ya da yazma YAPMA; her şey bu metinde.
Yanıtın TEK satır olsun, başka hiçbir şey yazma: `{i:03d}|onay|-` ya da `{i:03d}|ret|<neden kodu>` (kodlar: kapsam-eksik, bicim, sayi-tutarsiz, kanit-yok, talimat-ihlali, kriter-belirsiz, yetenek-yetersiz, ortam).

## Kart
Başlık: {konu.capitalize()} envanteri çıkar.
Yazma alanı: yalnız `{konu.split()[0]}_envanter_20261031.md` (başka dosya yazılmaz).
Kabul kriterleri:
- K1: Çıktı, kaynak.csv'deki {n} satırın TAMAMINI tabloda verir.
- K2: Son satır "Toplam" adet toplamıdır ve tablodaki adetlerin toplamına eşittir.
- K3: Her satırın Kaynak sütununda `kaynak.csv:<satır>` yazılır.
- K4: Tablo markdown biçiminde ("| Ad | Adet | Kaynak |" başlığı) ve dosya adı `<ilk sözcük>_envanter_20261031.md` olur.
- K5: Çıktıda sır değeri ya da çalışan adı yoktur.

## kaynak.csv (başlık satırı 1)
ad,adet
{chr(10).join(kaynak)}

## İşçinin ürettiği dosya: {dosya_adi}
{cikti}
"""
    return {"id": f"{i:03d}", "etiket": "bozuk" if kusur else "dogru", "kusur": kusur or "-", "prompt": prompt}


def vakalar() -> list[dict]:
    rng = random.Random(TOHUM)
    plan: list[str | None] = [k for k in KUSURLAR for _ in range(6)] + [None] * 30
    rng.shuffle(plan)
    return [_vaka(i + 1, random.Random(TOHUM + i), k) for i, k in enumerate(plan)]


def uret(dizin: str) -> int:
    os.makedirs(dizin, exist_ok=True)
    v = vakalar()
    for x in v:
        with open(os.path.join(dizin, f"{x['id']}.md"), "w", encoding="utf-8") as f:
            f.write(x["prompt"])
    return len(v)


def cp_ust(k: int, n: int, guven: float = 0.95) -> float:
    """Clopper-Pearson tek yönlü üst sınır: P(X<=k | p) = 1-guven olan p."""
    if k >= n:
        return 1.0

    def cdf(p: float) -> float:
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))

    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) > 1 - guven else (lo, mid)
    return (lo + hi) / 2


def puanla(satirlar: list[str]) -> dict:
    gercek = {x["id"]: x for x in vakalar()}
    karar: dict[str, tuple[str, str]] = {}
    for s in satirlar:
        p = [t.strip() for t in s.strip().split("|")]
        if len(p) >= 2 and p[0] in gercek and p[1] in ("onay", "ret"):
            karar[p[0]] = (p[1], p[2] if len(p) > 2 else "-")
    bozuk = [i for i, x in gercek.items() if x["etiket"] == "bozuk"]
    dogru = [i for i, x in gercek.items() if x["etiket"] == "dogru"]
    kacirma = [i for i in bozuk if i in karar and karar[i][0] == "onay"]
    yanlis = [i for i in dogru if i in karar and karar[i][0] == "ret"]
    nb = sum(1 for i in bozuk if i in karar)
    nd = sum(1 for i in dogru if i in karar)
    neden_ok = sum(1 for i in bozuk if i in karar and karar[i][0] == "ret" and karar[i][1] == gercek[i]["kusur"])
    tur = {k: [i for i in kacirma if gercek[i]["kusur"] == k] for k in KUSURLAR}
    return {"bozuk_n": nb, "dogru_n": nd, "kacirma": len(kacirma), "kacirma_ust": cp_ust(len(kacirma), nb) if nb else None,
            "yanlis_ret": len(yanlis), "yanlis_ret_ust": cp_ust(len(yanlis), nd) if nd else None,
            "neden_dogru": neden_ok, "kacirilan_turler": {k: v for k, v in tur.items() if v},
            "kacirilan": kacirma, "yanlis_retler": yanlis, "eksik_yanit": [i for i in gercek if i not in karar]}


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "uret":
        print(uret(argv[2]), "vaka yazıldı")
        return 0
    if len(argv) >= 3 and argv[1] == "puanla":
        with open(argv[2], encoding="utf-8") as f:
            r = puanla(f.read().splitlines())
        for k, v in r.items():
            print(f"{k}: {v}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
