"""orkestra komutları: gosterge (orkestra.py bölünmesinden)."""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import hashlib
import os
import re
import subprocess
import sys
import time

import ork_lib as L  # noqa: E402
import ret_nedeni as RN  # noqa: E402
import soru_sinif as SS  # noqa: E402
from komutlar._ortak import sd_gerekli  # noqa: E402


def cmd_gunluk_ozet(a):
    sd = sd_gerekli()
    esik = L.gun_baslangici(a.gun).isoformat()
    kayitlar = [r for r in L.jsonl_oku(os.path.join(sd, "gunluk.jsonl")) if r.get("zaman", "") >= esik]
    tur = collections.Counter(r.get("tur") for r in kayitlar)
    skill = collections.Counter(r.get("skill") for r in kayitlar if r.get("tur") == "skill")
    ajan = collections.Counter(r.get("ajan") for r in kayitlar if r.get("tur") == "ajan")
    print(f"Son {a.gun} gün: {len(kayitlar)} olay — " + ", ".join(f"{k}: {v}" for k, v in tur.items()))
    print("Skill kullanımı: " + (", ".join(f"{k} ×{v}" for k, v in skill.most_common()) or "-"))
    print("Ajan kullanımı: " + (", ".join(f"{k} ×{v}" for k, v in ajan.most_common()) or "-"))
    print("\nİstekler (maskeli, en yeni 40):")
    for r in [r for r in kayitlar if r.get("tur") == "istek"][-40:]:
        print(f"- {r.get('zaman', '')[:16]} {r.get('metin', '')[:160]}")


def cmd_kpi(a):
    """Hazır 8 KPI, salt okuma (kpi.py)."""
    sd = sd_gerekli()
    if getattr(a, "islem", None) == "planlayici-degerlendir":
        import planlayici_degerlendir as PD
        r = PD.degerlendir(sd, zorla=a.zorla, kuru=a.kuru)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(f"planlayıcı değerlendirmesi: {r['durum']} (model {r['model_surumu']})")
            for x in r.get("planlayicilar") or []:
                print(f"  {x['planlayici']:<10} n={x['n']}" + ("" if x["yeterli"] else " [yetersiz veri]"))
            for x in r.get("farklar") or []:
                print(f"  fark {x['referans']}~{x['aday']}: " + "; ".join(x["nedenler"]))
            if r.get("oneri"):
                print(f"  onay önerisi açıldı: {r['oneri']['onay_id']}")
        return
    import kpi
    aralik = None
    if getattr(a, "baslangic", None):
        try:
            bas = datetime.datetime.fromisoformat(a.baslangic).astimezone()                 if "T" in a.baslangic else datetime.datetime.strptime(a.baslangic, "%Y-%m-%d").astimezone()
        except ValueError:
            print("--baslangic YYYY-AA-GG biçiminde olmalı", file=sys.stderr)
            sys.exit(2)
        aralik = (bas, bas + datetime.timedelta(days=36500))
    s = kpi.olcum(sd, a.gun, aralik)
    print(json.dumps(s, ensure_ascii=False, indent=2) if a.json else kpi.tablo(s))


def cmd_ui_ozet(a):
    """Arayüz anlık görüntüsü (ozet.json ile aynı içerik); --yaz ile dosyayı da günceller."""
    sd = L.durum_dizini()
    if not sd:
        print(json.dumps({"acik": False}))
        return
    import ozet
    o = ozet.yaz(sd, L.proje_dizini()) if a.yaz else ozet.olustur(sd, L.proje_dizini())
    print(json.dumps(o, ensure_ascii=False))


def cmd_panel(a):
    """HTML canlı paneli başlatır (tüm çalışma alanları; yalnız 127.0.0.1) ve adresini yazar.

    Bulunulan klasör bir Claude çalışma alanıysa panel onu seçili açar."""
    import panel
    alan_id = os.path.basename(L.proje_oturum_dizini(L.proje_dizini()))
    if not os.path.isdir(L.proje_oturum_dizini(L.proje_dizini())):
        alan_id = None
    sonuc = panel.baslat(a.port, alan_id, on_planda=a.on_planda)
    print(sonuc)
    if a.ac and sonuc.startswith("http"):
        import webbrowser
        webbrowser.open(sonuc.split()[0])


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    ui = alt.add_parser("ui-ozet")
    ui.add_argument("--oturum")
    ui.add_argument("--yaz", action="store_true")
    ui.set_defaults(f=cmd_ui_ozet)

    pa = alt.add_parser("panel")
    pa.add_argument("--port", type=int, default=None, help="varsayılan: cfg (panel_port)")
    pa.add_argument("--on-planda", action="store_true", help="sunucuyu bu süreçte çalıştır (Ctrl+C ile durur)")
    pa.add_argument("--ac", action="store_true", help="adresi varsayılan tarayıcıda aç")
    pa.set_defaults(f=cmd_panel)

    kp = alt.add_parser("kpi", help="8 KPI salt okuma ölçümü")
    kp.add_argument("--json", action="store_true", help="makine çıktısı")
    kp.add_argument("--gun", type=float, default=None, help="son N gün")
    kp.add_argument("--baslangic", help="YYYY-AA-GG: bu tarihten (yerel 00:00) sonraki kartlar ve kayıtlar (kapı sonrası pencere)")
    kp.add_argument("islem", nargs="?", choices=["planlayici-degerlendir"], help="planlayici-degerlendir: haftalık planlayıcı değerlendirmesi (eşik aşılırsa onay önerisi, model sürümü değişirse dönem sıfırlanır)")
    kp.add_argument("--zorla", action="store_true", help="planlayici-degerlendir: 7 günlük bekleme süresini yoksay")
    kp.add_argument("--kuru", action="store_true", help="planlayici-degerlendir: hiçbir şey yazma, onay açma")
    kp.set_defaults(f=cmd_kpi)

    gu = alt.add_parser("gunluk").add_subparsers(dest="alt", required=True)
    go = gu.add_parser("ozet")
    go.add_argument("--gun", type=int, default=7)
    go.set_defaults(f=cmd_gunluk_ozet)
