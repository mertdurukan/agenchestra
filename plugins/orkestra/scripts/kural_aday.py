"""orkestra kural_aday: tekrarlayan ret -> kural adayı, maliyet anomalisi, kart bütçe tavanı önerisi (G-076).

SALT OKUMA: hiçbir dosya yazmaz, hiçbir şeyi durdurmaz (yalnız bilgi). Maliyet yalnız ork_lib.maliyet_kayitlari
(tekilleştirilmiş) üzerinden okunur. Anomali: grup içi medyan + k*MAD (MAD ölçeklenmemiş; MAD=0 ise medyan*2).
Bütçe tavanı: grup p90 (nearest-rank) x 2.

CLI: kural_aday.py rapor [--esik N] [--json] [--sd DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import ret_nedeni as RN  # noqa: E402

# neden -> (kabul kriteri şablonu, deterministik ön kontrol tarifi ya da None)
ONERI = {
    "kapsam-eksik": ("Her kabul kriteri için ayrı kanıt satırı (dosya:satır ya da komut çıktısı) verilmeli; "
                     "kanıtsız kriter yapılmamış sayılır.",
                     "Kabul kriteri numaralarını işçi çıktısında eşleştiren eksik-token denetimi "
                     "(her kriter numarası çıktıda geçmeli)."),
    "bicim": ("Çıktı dosya yolu, adlandırma ve şema kartta açıkça yazılmalı; çıktı bu şemaya birebir uymalı "
              "(LF, BOM yok).",
              "Satır sonu (CRLF) ve BOM denetimi; beklenen dosya adı/şema doğrulaması."),
    "sayi-tutarsiz": ("Rapordaki her sayı kaynağıyla (komut çıktısı, dosya) tek tek eşleşmeli; toplamlar "
                      "betikle yeniden hesaplanıp yazılmalı.", None),
    "kanit-yok": ("Her iddia dosya:satır, komut çıktısı ya da sayı ile kanıtlanmalı; kanıtsız iddia kabul "
                  "edilmez.",
                  "Çıktıda dosya:satır kanıt kalıbını arayan eksik-token denetimi."),
    "talimat-ihlali": ("Yazma alanı ve test alanı dışına yazılmamalı; kart ve protokol talimatları adım adım "
                       "karşılanmalı.",
                       "Kapsam denetimi: yazma alanı dışı ve test dosyası değişikliği."),
    "kriter-belirsiz": ("Kabul kriteri ölçülebilir, tek anlamlı ve birbiriyle çelişmeyen biçimde yeniden "
                        "yazılmalı (sayı, eşik, komut belirtilerek).", None),
    "yetenek-yetersiz": ("Basamak yükseltme ölçütü karta yazılmalı; iş daha küçük, doğrulanabilir parçalara "
                         "bölünmeli.", None),
    RN.SINIFLANMAMIS: ("Ret nedeni kodu girilmeli (ret_nedeni sözlüğü); nedensiz ret tekrar analiz edilemez.",
                       None),
}


def sinif_normal(k: dict) -> str:
    s = k.get("sinif")
    if s == "kod-duzenleme":
        return "kod"
    if s in (None, "", "-"):
        return "belirsiz"
    return s


def _retler(k: dict) -> list[dict]:
    den = k.get("denetimler")
    return [d for d in (den if isinstance(den, list) else []) if isinstance(d, dict) and d.get("karar") == "ret"]


def _neden(d: dict) -> str:
    n = d.get("neden")
    return n if isinstance(n, str) and n in RN.NEDENLER else RN.SINIFLANMAMIS


def kural_adaylari(kartlar: list[dict], esik: int = 3) -> list[dict]:
    sayim: dict = {}
    ornek: dict = {}
    for k in kartlar:
        sn = sinif_normal(k)
        for d in _retler(k):
            a = (sn, _neden(d))
            sayim[a] = sayim.get(a, 0) + 1
            ids = ornek.setdefault(a, [])
            if k.get("id") not in ids and len(ids) < 5:
                ids.append(k.get("id"))
    out = []
    for (sn, neden), n in sayim.items():
        if n < esik:
            continue
        kriter, on_kontrol = ONERI[neden]
        out.append({"sinif": sn, "neden": neden, "sayi": n, "ornek_kartlar": ornek[(sn, neden)],
                    "oneri_kriter": kriter, "oneri_on_kontrol": on_kontrol})
    out.sort(key=lambda a: (-a["sayi"], a["sinif"], a["neden"]))
    return out


def _medyan(x: list) -> float:
    s = sorted(x)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _gruplar(kartlar: list[dict], kayitlar: list[dict], ham_sinif: bool = False) -> dict:
    ids = {k.get("id") for k in kartlar}
    usd: dict = {}
    for r in kayitlar:
        g = r.get("gorev")
        if g in ids:
            usd[g] = usd.get(g, 0.0) + float(r.get("maliyet_usd") or 0)
    gr: dict = {}
    for k in kartlar:
        anahtar = (k.get("sinif") if ham_sinif else sinif_normal(k), k.get("basamak") or "-")
        gr.setdefault(anahtar, []).append((k, usd.get(k.get("id"), 0.0)))
    return gr


def anomaliler(kartlar: list[dict], kayitlar: list[dict], k: float = 3.0, min_grup: int = 4) -> list[dict]:
    out = []
    for (sn, bas), uyeler in sorted(_gruplar(kartlar, kayitlar).items()):
        if len(uyeler) < min_grup:
            continue
        x = [u for _, u in uyeler]
        med = _medyan(x)
        mad = _medyan([abs(v - med) for v in x])
        esik = med + k * mad if mad > 0 else med * 2
        for kart, u in uyeler:
            if u > esik:
                out.append({"id": kart.get("id"), "sinif": sn, "basamak": bas, "usd": u, "medyan": med,
                            "esik": esik, "ret_sayisi": len(_retler(kart))})
    return out


def butce_tavani(kartlar: list[dict], kayitlar: list[dict], min_grup: int = 4) -> list[dict]:
    # Kilitli test sözleşmesi: bütçe grubu ham sınıf x basamak (kod-duzenleme ayrı grup), çıktıda sınıf normal.
    out = []
    for (sn, bas), uyeler in sorted(_gruplar(kartlar, kayitlar, True).items(), key=lambda t: (str(t[0][0]), t[0][1])):
        sn = sinif_normal({"sinif": sn})
        n = len(uyeler)
        if n < min_grup:
            continue
        s = sorted(u for _, u in uyeler)
        p90 = s[max(0, -(-9 * n // 10) - 1)]  # nearest-rank: ceil(0.9*n). eleman
        out.append({"sinif": sn, "basamak": bas, "n": n, "tavan_usd": 2 * p90})
    return out


def rapor(sd: str, esik: int = 3) -> dict:
    kartlar = L.kartlar(sd)
    kay = L.maliyet_kayitlari(sd)
    return {"kural_adaylari": kural_adaylari(kartlar, esik), "anomaliler": anomaliler(kartlar, kay),
            "butce_tavani": butce_tavani(kartlar, kay)}


def duz(r: dict, sinir: int = 40) -> str:
    bolumler = [
        ("Kural adayları", r["kural_adaylari"],
         lambda a: f"  {a['sinif']}/{a['neden']} x{a['sayi']} ({', '.join(a['ornek_kartlar'])}): "
                   f"{a['oneri_kriter'][:60]}"),
        ("Anomaliler", r["anomaliler"],
         lambda a: f"  {a['id']} {a['sinif']}/{a['basamak']} {a['usd']:.4f} USD "
                   f"(medyan {a['medyan']:.4f}, eşik {a['esik']:.4f}, ret {a['ret_sayisi']})"),
        ("Bütçe tavanı (yalnız bilgi)", r["butce_tavani"],
         lambda a: f"  {a['sinif']}/{a['basamak']} n={a['n']} tavan {a['tavan_usd']:.4f} USD"),
    ]
    pay = max(1, (sinir - 3 - 3) // 3)  # başlık ve "... n daha" payı bırakılır
    satir = []
    for baslik, liste, bic in bolumler:
        satir.append(f"{baslik}: {len(liste)}")
        satir += [bic(a) for a in liste[:pay]]
        if len(liste) > pay:
            satir.append(f"  ... {len(liste) - pay} daha (--json ile tamamı)")
        if not liste:
            satir.append("  (yok)")
    return "\n".join(satir[:sinir])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kural_aday")
    alt = ap.add_subparsers(dest="komut", required=True)
    p = alt.add_parser("rapor")
    p.add_argument("--esik", type=int, default=3)
    p.add_argument("--json", action="store_true")
    p.add_argument("--sd", default=None)
    a = ap.parse_args(argv)
    sd = a.sd or os.path.join(L.proje_dizini(), ".claude", "orkestra")
    r = rapor(sd, a.esik)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else duz(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
