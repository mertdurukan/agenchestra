"""orkestra komutları: `konu` — sohbet konu defteri (ADR-0115): ac, liste, rapor."""
from __future__ import annotations

import json
import os
import sys

import konu_defteri as KD
import ork_lib as L
from komutlar._ortak import hata, oturum_id, sd_gerekli


def _sdler(tum: bool) -> list[str]:
    if not tum:
        return [sd_gerekli()]
    out = []
    for a in L.calisma_alanlari():
        sd = L.durum_dizini(a["yol"])
        if sd and os.path.exists(KD.yol(sd)):
            out.append(sd)
    return out


def cmd_konu_ac(a):
    sd = sd_gerekli()
    oturum = a.oturum or oturum_id()
    if oturum == "-":
        return hata("oturum kimliği bulunamadı (CLAUDE_CODE_SESSION_ID yok); --oturum ver.")
    if not (a.baslik or "").strip():
        return hata("konu başlığı boş olamaz.")
    sira = KD.ac(sd, oturum, a.baslik, kaynak="ajan", neden=a.neden)
    if a.neden:
        try:
            import niyet
            niyet.olay(oturum, L.proje_dizini(), "niyet", ne=a.baslik[:140], neden=a.neden[:160])
        except Exception:
            pass
    print(f"K{sira} açıldı: {KD._kisalt(a.baslik, KD.BASLIK_AZAMI)}")


def cmd_konu_liste(a):
    sd = sd_gerekli()
    oturum = a.oturum or oturum_id()
    olaylar = [k for k in KD.oku(sd) if k.get("oturum") == oturum]
    konular = KD.oturum_ozeti(olaylar)
    if a.json:
        print(json.dumps(konular, ensure_ascii=False, indent=2))
    elif not konular:
        print("Bu sohbette kayıtlı konu yok.")
    else:
        print(KD.liste_md(konular, f"Sohbet {oturum[:8]} konuları (toplam {len(konular)})"), end="")


def cmd_konu_rapor(a):
    sdler = _sdler(a.tum)
    if a.etiket:
        metin = KD.etiket_md(sdler, a.gun)
    else:
        r = KD.rapor(sdler, a.gun)
        metin = json.dumps(r, ensure_ascii=False, indent=2) if a.json else KD.rapor_md(r, a.gun)
    if a.yaz:
        with open(a.yaz, "w", encoding="utf-8") as f:
            f.write(metin)
        print(a.yaz)
    else:
        print(metin, end="")


def kaydet(alt):
    p = alt.add_parser("konu", help="sohbet konu defteri: ac, liste, rapor (ADR-0115)")
    p.add_argument("--yardım", action="help", help="bu yardımı gösterir")
    s = p.add_subparsers(dest="konu_komut", required=True)
    d = s.add_parser("ac", help="yeni konu başlatır (yalnızca konu gerçekten değiştiğinde)")
    d.add_argument("baslik", help="konu başlığı (en çok 12 kelime; sır yazma)")
    d.add_argument("--neden", help="konunun neye yaradığı (niyet kaydına da yansır)")
    d.add_argument("--oturum")
    d.set_defaults(f=cmd_konu_ac)
    d = s.add_parser("liste", help="sohbetin konuları: zaman, tur sayısı, süre")
    d.add_argument("--oturum")
    d.add_argument("--json", action="store_true")
    d.set_defaults(f=cmd_konu_liste)
    d = s.add_parser("rapor", help="sohbet başına konu sayısı, dağılım ve konu sınırı göstergeleri")
    d.add_argument("--gun", type=int, help="son N gün")
    d.add_argument("--tum", action="store_true", help="hesaptaki bütün çalışma alanları")
    d.add_argument("--etiket", action="store_true", help="elle etiketleme şablonu üretir")
    d.add_argument("--yaz", metavar="DOSYA", help="çıktıyı dosyaya yazar")
    d.add_argument("--json", action="store_true")
    d.set_defaults(f=cmd_konu_rapor)
