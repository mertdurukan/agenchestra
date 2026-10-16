"""orkestra komutları: plan (plan.md iddia doğrulaması; model çağırmaz).

`orkestra plan dogrula <iş-kimliği|plan.md> [--yaz] [--json] [--kok DİZİN]... [--komut-kosma] [--ac]`
Çıkış kodu: 0 UYGULANABİLİR, 1 KOŞULLU, 2 UYGULANAMAZ, 3 TAMAMLANMAMIŞ (yapısal eksik).
`--yaz` olmadan dosya değişmez.
"""
from __future__ import annotations

import json
import os
import re
import sys

from komutlar._ortak import hata, sd_gerekli


def _plan_yolu(sd, hedef):
    if re.fullmatch(r"I-\d+", hedef):
        import is_kaydi
        kayit = is_kaydi.is_al(sd, hedef)
        if not kayit:
            hata(f"iş yok: {hedef}")
        return os.path.join(kayit["klasor"], "plan.md"), kayit
    return os.path.abspath(hedef), None


def cmd_plan_dogrula(a):
    import plan_dogrulama as PD
    sd = sd_gerekli()
    yol, kayit = _plan_yolu(sd, a.hedef)
    if not os.path.isfile(yol):
        hata(f"plan bulunamadı: {yol}")
    if a.ac:
        if not kayit:
            hata("--ac iş kimliği ister (I-nnn)")
        import is_kaydi
        is_kaydi._degistir(sd, kayit["id"], lambda k: (k.__setitem__("dogrulama", PD.DOGRULAMA_ADI),
                                                       k.setdefault("gecmis", []).append({"zaman": __import__("ork_lib").simdi(),
                                                                                         "olay": "dogrulama:acildi"})))
        print(f"{kayit['id']} plan doğrulaması açıldı (todo kapısı: mod={PD.ayar(os.path.dirname(os.path.dirname(sd))).get('mod')}).")
    try:
        sonuc = PD.yaz(yol, a.kok, not a.komut_kosma) if a.yaz else PD.degerlendir(yol, a.kok, not a.komut_kosma)
    except ValueError as e:
        hata(str(e))
    if a.json:
        cikti = {k: v for k, v in sonuc.items() if k != "iddialar"}
        cikti["iddialar"] = [{"no": c["no"], "isaret": c["isaret"], "hesap": c["hesap"], "neden": c["neden"],
                              "metin": c["metin"], "kanit": c["sonuclar"], "cikis": c["cikis"]} for c in sonuc["iddialar"]]
        print(json.dumps(cikti, ensure_ascii=False, indent=2))
    else:
        t = sum(c["hesap"] == PD.TAMAM for c in sonuc["iddialar"])
        y = sum(c["hesap"] == PD.YOK for c in sonuc["iddialar"])
        print(f"plan: {yol}")
        print(f"karar: {sonuc['karar']}")
        print(f"iddialar: {len(sonuc['iddialar'])} (✅ {t}, ❌ {y}); plan özeti {sonuc['ozet']}" + (" (yazıldı)" if a.yaz else ""))
        for c in sonuc["iddialar"]:
            print(f"  {c['hesap']} C{c['no']} {c['metin'][:70]} — {c['neden'][:110]}")
        for n, s in sonuc["engelli"].items():
            print(f"  engelli: P{n} ← " + ", ".join(f"C{x}" for x in s))
        for e in sonuc["eksik"]:
            print(f"  eksik: {e}")
        if sonuc.get("bayat"):
            b = sonuc["bayat"]
            print(f"  uyarı: {len(b)} iddianın işareti plan.md'de güncel değil ({', '.join(b[:8])}{'…' if len(b) > 8 else ''}): `--yaz` ile yaz")
    sys.exit(PD.CIKIS_KODU[sonuc["karar"]])


def kaydet(alt):
    p = alt.add_parser("plan", help="plan.md iddia doğrulaması: kanıtı yeniden doğrular, ✅/❌ koyar, uygulanabilirlik kararı verir").add_subparsers(dest="alt", required=True)
    d = p.add_parser("dogrula", help="plan.md iddialarını kanıtla doğrular; çıkış 0 uygulanabilir, 1 koşullu, 2 uygulanamaz, 3 tamamlanmamış")
    d.add_argument("hedef", help="iş kimliği (I-nnn) ya da plan.md yolu")
    d.add_argument("--yaz", action="store_true", help="işaretleri ve karar bloğunu plan.md'ye yazar")
    d.add_argument("--json", action="store_true")
    d.add_argument("--kok", action="append", default=[], metavar="DİZİN", help="dosya kanıtı için ek kök (tekrarlanabilir)")
    d.add_argument("--komut-kosma", action="store_true", help="komut kanıtlarını koşturma (❌ sayılır)")
    d.add_argument("--ac", action="store_true", help="işe dogrulama bayrağı koyar (todo kapısı açılır)")
    d.set_defaults(f=cmd_plan_dogrula)
