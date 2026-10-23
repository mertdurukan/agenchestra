"""orkestra komutları: `is dalga` — plan.md → dalgalar, `## Dalgalar` bölümü ve kart JSON'u (ADR-0080, P4).

Plan tek kaynaktır: dalga ve kritik yol `paralellik.analiz` ile hesaplanır, kartlar P bloklarından üretilir. Üretilen
`{"gorevler": [...]}` dosyası hem `orkestra kart toplu --json-dosya` girdisidir hem de `Workflow orkestra:calistir`
`args` biçimindedir (kartlar yüklendikten sonra `ref` yerine kart kimlikleri gelir).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import paralellik as PR  # noqa: E402
from komutlar._ortak import hata, sd_gerekli  # noqa: E402

BASLIK = "## Dalgalar"
ONCEKI_BOLUM = "## Gap kapsama"
VARSAYILAN_BASAMAK = "T2"
SORU_MAX = 200
_TEST_DOSYASI = re.compile(r"(^|/)tests?/.*test_[^/*?\[]*\.py$|(^|/)test_[^/*?\[]*\.py$", re.I)
_P_BASLIK = re.compile(r"^(?:#{2,4}\s+|[-*]\s+(?:\*\*)?)P(\d+)\b\**\s*[—–:.-]?\s*(.*)$")


def plan_yolu_coz(sd: str, hedef: str) -> tuple[str, dict | None]:
    """İş kimliği (I-nnn), iş klasörü ya da plan.md yolu → (plan.md yolu, iş kaydı | None). Bilinmeyen iş hata verir."""
    from komutlar.plan import _plan_yolu
    yol, kayit = _plan_yolu(sd, hedef)
    if os.path.isdir(yol):
        klasor = yol
        yol = os.path.join(klasor, "plan.md")
        is_json = os.path.join(klasor, "is.json")
        if os.path.isfile(is_json):
            try:
                with open(is_json, encoding="utf-8") as f:
                    kayit = json.load(f)
            except (OSError, ValueError):
                kayit = None
    if not os.path.isfile(yol):
        hata(f"plan bulunamadı: {yol}")
    return yol, kayit


def _p_basliklari(plan_metni: str) -> dict[int, str]:
    """{n: başlık} — P bloğunun ilk satırından madde adı (P numarası ve süsler atılır)."""
    sonuc = {}
    for n, blok in PR._p_bloklari(plan_metni).items():
        ilk = blok.splitlines()[0] if blok else ""
        m = _P_BASLIK.match(ilk.strip())
        ad = (m.group(2) if m else "").strip().strip("*").strip()
        sonuc[n] = ad
    return sonuc


def kabul_degerleri(plan_metni: str) -> dict[int, str]:
    return {n: PR._alan_degeri(blok, "Kabul") for n, blok in PR._p_bloklari(plan_metni).items()}


def _yazma_sirali(yazma_ham: str) -> list[str]:
    """Yazma alanı girdileri plandaki sırayla (paralellik.yazma_ayristir ile aynı normalleştirme)."""
    return sorted(PR.yazma_ayristir(yazma_ham), key=lambda p: yazma_ham.replace("\\", "/").find(p))


def kartlar_uret(plan_metni: str, an: dict, is_id: str | None = None, plan_yolu: str | None = None,
                 basamak: str = VARSAYILAN_BASAMAK) -> list[dict]:
    """P maddelerinden `cmd_kart_toplu` şemasında kart listesi (dalga sırasıyla)."""
    md = an["maddeler"]
    basliklar = _p_basliklari(plan_metni)
    kabuller = kabul_degerleri(plan_metni)
    seviye = {n: k for k, kat in enumerate(an["dalgalar"], 1) for n in kat}
    sira = [n for kat in an["dalgalar"] for n in kat] or sorted(md)
    kartlar = []
    for n in sira:
        m = md[n]
        ad = basliklar.get(n) or f"Madde {n}"
        yazma = _yazma_sirali(m["yazma_ham"])
        testler = [y for y in yazma if _TEST_DOSYASI.search(y)]
        soru = f"P{n} kabul ölçütü karşılandı mı: {ad}?"
        if len(soru) > SORU_MAX:
            soru = soru[:SORU_MAX - 2].rstrip() + "…?"
        k = {"ref": f"P{n}", "baslik": f"P{n} {ad}", "soru": soru, "basamak": basamak,
             "sinif": "kod" if testler else "belge",
             "kabul_kriterleri": [kabuller.get(n, "")] if kabuller.get(n) else [],
             "yazma_alani": yazma,
             "bagimliliklar": [f"P{d}" for d, _, _ in m["once"] if d in md and d != n],
             "girdi": (f"{plan_yolu} § P{n}" if plan_yolu else f"plan.md § P{n}"),
             "dalga": seviye.get(n)}
        if testler:
            k["test_alani"] = testler
            k["test_komutu"] = "python -m pytest " + " ".join(testler)
        if is_id:
            k["is"] = is_id
        kartlar.append(k)
    return kartlar


def eksikler(plan_metni: str, an: dict) -> list[str]:
    """paralellik.analiz eksikleri + P maddesi yoksa ya da `Kabul` boşsa (kart kabul kriterisiz açılamaz)."""
    liste = list(an["eksikler"])
    if not an["maddeler"]:
        liste.append("plan.md'de P maddesi yok (### P<n> başlığı ya da - P<n> satırı)")
    kabuller = kabul_degerleri(plan_metni)
    liste += [f"P{n}: **Kabul:** alanı yok ya da boş (kartın kabul kriteri olur)"
              for n in sorted(an["maddeler"]) if not kabuller.get(n)]
    return liste


def _sayi(x) -> str:
    return f"{x:g}".replace(".", ",") if isinstance(x, float) else str(x)


def dalgalar_bolumu(an: dict) -> str:
    """`## Dalgalar` bölüm metni (başlık dahil, sonda boş satır)."""
    s = [BASLIK, "", "<!-- `orkestra is dalga --yaz` üretir; elle düzenleme, plan maddelerini değiştirip yeniden üret -->", ""]
    for k, kat in enumerate(an["dalgalar"], 1):
        s.append(f"- **Dalga {k}:** " + ", ".join(f"P{n}" for n in kat))
    s += [f"- **Kritik yol:** {an['kritik_yol']}",
          f"- **Genişlik:** {an['genislik']}",
          f"- **Ağırlıklı kritik yol:** {an['agirlikli_kritik_yol']}",
          f"- **Planlanan eşzamanlılık (ağırlıksız, P sayısı ÷ kritik yol):** {_sayi(an['planlanan_agirliksiz'])}",
          f"- **Planlanan eşzamanlılık (ağırlıklı, Σ ağırlık ÷ ağırlıklı kritik yol):** {_sayi(an['planlanan_agirlikli'])}",
          ""]
    return "\n".join(s) + "\n"


def bolum_yaz(plan_metni: str, bolum: str) -> str:
    """`## Dalgalar` bölümünü (başlıktan sonraki `## ` başlığına kadar) değiştirir; yoksa `## Gap kapsama`dan önce,
    o da yoksa sona ekler. Bölüm dışındaki metne dokunmaz."""
    satirlar = plan_metni.splitlines(keepends=True)
    bas = next((i for i, s in enumerate(satirlar) if s.rstrip() == BASLIK), None)
    if bas is not None:
        son = next((i for i in range(bas + 1, len(satirlar)) if re.match(r"^##\s", satirlar[i])), len(satirlar))
        return "".join(satirlar[:bas]) + bolum + "".join(satirlar[son:])
    gap = next((i for i, s in enumerate(satirlar) if s.rstrip() == ONCEKI_BOLUM), None)
    if gap is not None:
        return "".join(satirlar[:gap]) + bolum + "".join(satirlar[gap:])
    govde = plan_metni if plan_metni.endswith("\n") else plan_metni + "\n"
    return govde + "\n" + bolum


def ozet_metni(an: dict) -> str:
    s = []
    for k, kat in enumerate(an["dalgalar"], 1):
        s.append(f"Dalga {k}: " + ", ".join(f"P{n}" for n in kat))
    s += [f"Kritik yol: {an['kritik_yol']}", f"Genişlik: {an['genislik']}",
          f"Planlanan eşzamanlılık (ağırlıksız): {_sayi(an['planlanan_agirliksiz'])}",
          f"Planlanan eşzamanlılık (ağırlıklı): {_sayi(an['planlanan_agirlikli'])}"]
    return "\n".join(s)


def cmd_is_dalga(a):
    sd = sd_gerekli()
    yol, kayit = plan_yolu_coz(sd, a.hedef)
    with open(yol, encoding="utf-8") as f:
        metin = f.read()
    an = PR.analiz(metin, ileri_yasak=False)
    eksik = eksikler(metin, an)
    print(ozet_metni(an))
    if eksik:
        print(f"orkestra: plan eksik ({len(eksik)}); " + ("plan.md yazılmadı, " if a.yaz else "") + "kart JSON üretilmedi:",
              file=sys.stderr)
        for e in eksik:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    if a.yaz:
        yeni = bolum_yaz(metin, dalgalar_bolumu(an))
        if yeni != metin:
            with open(yol, "w", encoding="utf-8", newline="") as f:
                f.write(yeni)
        print(f"{BASLIK} bölümü yazıldı: {yol}")
    is_id = (kayit or {}).get("id")
    paket = {"gorevler": kartlar_uret(metin, an, is_id, yol, a.basamak)}
    metin_json = json.dumps(paket, ensure_ascii=False, indent=2)
    if a.json_cikti:
        os.makedirs(os.path.dirname(os.path.abspath(a.json_cikti)) or ".", exist_ok=True)
        with open(a.json_cikti, "w", encoding="utf-8") as f:
            f.write(metin_json + "\n")
        print(f"Kart JSON: {a.json_cikti}")
        print(f"Yükle: orkestra kart toplu --json-dosya {a.json_cikti}")
        print("Dağıt: Workflow name=orkestra:calistir, args={\"gorevler\": [yüklenen kartların `kart goster` JSON'u]}")
    else:
        print("Kart JSON (`kart toplu --json-dosya` ve Workflow orkestra:calistir args biçimi):")
        print(metin_json)


def kaydet(alt):
    """`is` alt komutlarına `dalga`yı ekler (isler.kaydet'ten SONRA çağrılmalı; MODULLER sırası)."""
    is_parser = alt.choices.get("is")
    if is_parser is None:
        raise RuntimeError("dalga: `is` komutu kayıtlı değil (isler modülü önce kaydedilmeli)")
    is_alt = next(x for x in is_parser._actions if isinstance(x, argparse._SubParsersAction))
    d = is_alt.add_parser("dalga", help="plan.md → dalgalar, kritik yol, `## Dalgalar` bölümü ve kart JSON'u (kart toplu / calistir args)")
    d.add_argument("--yardım", action="help", help="bu yardımı gösterir")
    d.add_argument("hedef", help="iş kimliği (I-nnn), iş klasörü ya da plan.md yolu")
    d.add_argument("--yaz", action="store_true", help="plan.md'deki `## Dalgalar` bölümünü betik çıktısıyla günceller/ekler")
    d.add_argument("--json-cikti", dest="json_cikti", metavar="DOSYA", help="kart JSON'unu dosyaya yazar ({\"gorevler\": [...]})")
    d.add_argument("--basamak", default=VARSAYILAN_BASAMAK, choices=("T0", "T1", "T2", "T3", "T4"),
                   help="kartların başlangıç basamağı (varsayılan T2)")
    d.set_defaults(f=cmd_is_dalga)
