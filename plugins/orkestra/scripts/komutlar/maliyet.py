"""orkestra komutları: maliyet (orkestra.py bölünmesinden)."""
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
from komutlar._ortak import BETIK_DIZINI, hata, oturum_id, sd_gerekli  # noqa: E402


def _maliyet_kayitlari(sd, gun):
    kayitlar = L.maliyet_kayitlari(sd)
    if gun:
        esik = L.gun_baslangici(gun)

        def yeni(r):   # damgalar +03:00 ya da Z (ham transkript) olabilir: metin değil an karşılaştırılır
            try:
                z = datetime.datetime.fromisoformat(str(r.get("zaman") or "").replace("Z", "+00:00"))
                return (z if z.tzinfo else z.astimezone()) >= esik
            except ValueError:
                return False
        kayitlar = [r for r in kayitlar if yeni(r)]
    return kayitlar


def _pivot(kayitlar, anahtarlar):
    p = collections.OrderedDict()
    for r in kayitlar:
        k = tuple(str(r.get(x, "-")) for x in anahtarlar)
        d = p.setdefault(k, {"kosu": 0, "giris": 0, "cikis": 0, "onbellek_okuma": 0, "onbellek_yazma": 0, "maliyet_usd": 0.0})
        d["kosu"] += 1
        for f in ("giris", "cikis", "onbellek_okuma", "onbellek_yazma"):
            d[f] += r.get(f, 0) or 0
        d["maliyet_usd"] += r.get("maliyet_usd", 0) or 0
    return p


def _md_tablo(baslik, anahtarlar, p):
    satirlar = [f"### {baslik}", "", "| " + " | ".join(anahtarlar) + " | koşu | giriş | çıkış | önbellek okuma | önbellek yazma | ≈$ |",
                "|" + "---|" * (len(anahtarlar) + 6)]
    for k, d in sorted(p.items(), key=lambda x: -x[1]["maliyet_usd"]):
        satirlar.append("| " + " | ".join(k) + f" | {d['kosu']} | {d['giris']:,} | {d['cikis']:,} | {d['onbellek_okuma']:,} | {d['onbellek_yazma']:,} | {d['maliyet_usd']:.3f} |")
    return "\n".join(satirlar).replace(",", ".") + "\n"


def _baglam_md(kayitlar):
    import analitik as AN
    k = AN.baglam_kirilim(kayitlar)
    satirlar = ["### Bağlam (proje / süreç / görev)", "", "| bağlam | ≈$ | pay |", "|---|---|---|"]
    for pr in k["projeler"]:
        satirlar.append(f"| **{pr['proje']}** | {pr['usd']:.3f} | %{pr['pay'] * 100:.1f} |")
        for b in pr["baglamlar"]:
            if b["baglam"] != pr["proje"]:
                satirlar.append(f"| &nbsp;&nbsp;{b['baglam']} | {b['usd']:.3f} | %{b['pay'] * 100:.1f} |")
    satirlar.append(f"| **Toplam** | {k['toplam_usd']:.3f} | %100.0 |")
    return "\n".join(satirlar) + "\n"


def cmd_maliyet_rapor(a):
    sd = sd_gerekli()
    import analitik as AN
    kayitlar = AN.baglam_filtre(AN.baglam_coz(sd, _maliyet_kayitlari(sd, a.gun)), getattr(a, "baglam", None))
    if a.csv:
        buf = io.StringIO()
        alanlar = ["zaman", "oturum", "gorev", "surec", "ajan", "agent_id", "model", "giris", "cikis", "onbellek_okuma",
                   "onbellek_yazma", "maliyet_usd", "sure_ms", "tur", "arac_cagrisi", "baglam"]
        w = csv.DictWriter(buf, fieldnames=alanlar, extrasaction="ignore")
        w.writeheader()
        for r in kayitlar:
            w.writerow(r)
        metin = buf.getvalue()
    else:
        toplam = sum(r.get("maliyet_usd", 0) or 0 for r in kayitlar)
        metin = f"# Token ve maliyet raporu ({'son ' + str(a.gun) + ' gün' if a.gun else 'tümü'}) — {L.simdi()[:16]}\n\n"
        metin += f"Toplam {len(kayitlar)} koşu, ≈${toplam:.2f} (API liste fiyatıyla tahmin).\n\n"
        metin += _md_tablo("Görev × süreç", ["gorev", "surec"], _pivot(kayitlar, ["gorev", "surec"]))
        metin += "\n" + _md_tablo("Ajan × model", ["ajan", "model"], _pivot(kayitlar, ["ajan", "model"]))
        metin += "\n" + _md_tablo("Süreç", ["surec"], _pivot(kayitlar, ["surec"]))
        metin += "\n" + _md_tablo("Gün", ["gun"], _pivot([dict(r, gun=(lambda z: z.date().isoformat() if z else "-")(__import__("analitik")._zaman(r.get("zaman")))) for r in kayitlar], ["gun"]))
        metin += "\n" + _baglam_md(kayitlar)
        metin += "\n" + AN.planlayici_md(AN._planlayici(L.kartlar(sd), L.maliyet_kayitlari(sd)))
        sohbet = {s["oturum"]: s for s in L.sohbetler(sd, L.proje_dizini(), limit=500)}
        satirlar = ["", "### Sohbet (çalışma alanındaki oturumlar)", "",
                    "| sohbet | son etkinlik | defter ≈$ | motor $ (sohbet kapanınca yazılır) |", "|---|---|---|---|"]
        for s in sorted(sohbet.values(), key=lambda x: -(x["motor_usd"] or x["defter_usd"] or 0)):
            if not (s["motor_usd"] or s["defter_usd"]):
                continue
            motor = f"{s['motor_usd']:.2f}" if s["motor_usd"] is not None else "—"
            satirlar.append(f"| {s['baslik']} | {s['son'][:16].replace('T', ' ')} | {s['defter_usd']:.2f} | {motor} |")
        metin += "\n".join(satirlar) + "\n"
    if a.cikti:
        L.atomik_yaz(a.cikti, metin)
        print(a.cikti)
    else:
        print(metin)


def cmd_maliyet_gecmis(a):
    """Projenin geçmiş Claude oturumlarındaki token kullanımını maliyet defterine bir kez aktarır (ajan × süreç × model)."""
    sd = sd_gerekli()
    import glob as _glob
    sys.path.insert(0, BETIK_DIZINI)
    import perspektif
    pdir = os.path.dirname(perspektif.hafiza_dizini(L.proje_dizini()))
    yol = os.path.join(sd, "maliyet.jsonl")
    mevcut = {(r.get("oturum"), r.get("agent_id"), r.get("model")) for r in L.jsonl_oku(yol)}
    yeni = 0
    for ana in sorted(_glob.glob(os.path.join(pdir, "*.jsonl"))):
        oid = os.path.basename(ana)[:-6]
        if oid == oturum_id() and not a.bu_oturum_dahil:
            continue
        ozet = L.transkript_oku(ana, 0, yan_zincir=False)
        for model, m in ozet["modeller"].items():
            if (oid, None, model) in mevcut:
                continue
            L.jsonl_ekle(yol, dict({"zaman": ozet["son_zaman"] or L.simdi(), "oturum": oid, "gorev": "-", "surec": "gecmis-ana",
                                    "ajan": "ana-ajan", "agent_id": None, "tur": ozet["tur"], "arac_cagrisi": ozet["arac_cagrisi"],
                                    "sure_ms": L.sure_ms(ozet["ilk_zaman"], ozet["son_zaman"]), "kaynak": "gecmis"}, model=model, **m))
            yeni += 1
        for alt in sorted(_glob.glob(os.path.join(pdir, oid, "subagents", "agent-*.jsonl"))):
            aid = os.path.basename(alt)[len("agent-"):-6]
            meta = L.alt_ajan_meta(alt)
            o2 = L.transkript_oku(alt)
            gorev, surec = L.etiketler(o2["ilk_kullanici"])
            for model, m in o2["modeller"].items():
                if (oid, aid, model) in mevcut:
                    continue
                L.jsonl_ekle(yol, dict({"zaman": o2["son_zaman"] or L.simdi(), "oturum": oid, "gorev": gorev,
                                        "surec": surec if surec != "bilinmiyor" else "gecmis-alt", "ajan": meta.get("agentType") or "?",
                                        "agent_id": aid, "tur": o2["tur"], "arac_cagrisi": o2["arac_cagrisi"],
                                        "sure_ms": L.sure_ms(o2["ilk_zaman"], o2["son_zaman"]), "aciklama": meta.get("description"),
                                        "kaynak": "gecmis"}, model=model, **m))
                yeni += 1
    print(f"{yeni} satır aktarıldı → {yol}")


def cmd_maliyet_yeniden_etiketle(a):
    """gorev='-' ve agent_id'li maliyet kayıtlarını transkriptten çözülen karta bağlar (varsayılan kuru çalıştırma)."""
    sd = sd_gerekli()
    sys.path.insert(0, BETIK_DIZINI)
    import hook
    pdir = a.transkript_dizini
    if not pdir:
        import perspektif
        pdir = os.path.dirname(perspektif.hafiza_dizini(L.proje_dizini()))
    yol = os.path.join(sd, "maliyet.jsonl")
    cozum = {}  # (oturum, agent_id) -> (gorev, surec) | None

    def coz(oid, aid):
        k = (oid, aid)
        if k not in cozum:
            tp = hook.transkript_bul(os.path.join(pdir, f"{oid}.jsonl"), oid, aid)
            g, s, _ = hook.transkript_etiketleri(tp)
            cozum[k] = (g, s) if g != "-" else None
        return cozum[k]

    def uygula_satir(r):
        if r.get("gorev") == "-" and r.get("agent_id") and r.get("oturum"):
            c = coz(r["oturum"], r["agent_id"])
            if c:
                return dict(r, gorev=c[0])
        return r

    sayac = {}
    for r in L.jsonl_oku(yol):
        y = uygula_satir(r)
        if y is not r:
            sayac[y["gorev"]] = sayac.get(y["gorev"], 0) + 1
    toplam = sum(sayac.values())
    ozet_s = ", ".join(f"{g}: {n}" for g, n in sorted(sayac.items())) or "yok"
    if not a.uygula:
        print(f"[kuru çalıştırma] {toplam} kayıt bağlanacak ({ozet_s}). Uygulamak için --uygula.")
        return
    degisen = 0
    with L.kilit(yol):  # kilit altında yeniden oku (paralel oturumlar ekleme yapmış olabilir)
        satirlar, yeni_satirlar = [], []
        if os.path.exists(yol):
            with open(yol, encoding="utf-8", errors="replace") as f:
                satirlar = f.read().splitlines()
        for ham in satirlar:
            try:
                r = json.loads(ham)
            except json.JSONDecodeError:
                yeni_satirlar.append(ham)
                continue
            y = uygula_satir(r)
            if y is not r:
                degisen += 1
                yeni_satirlar.append(json.dumps(y, ensure_ascii=False))
            else:
                yeni_satirlar.append(ham)
        if degisen:
            L.atomik_yaz(yol, "\n".join(yeni_satirlar) + "\n")
    onb = 0
    for (oid, aid), c in cozum.items():
        if not c:
            continue
        ay = os.path.join(sd, "oturumlar", f"ajan_{aid}.json")
        try:
            with open(ay, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if d.get("gorev") == "-":
            d["gorev"], d["surec"] = c[0], c[1]
            L.atomik_yaz(ay, json.dumps(d))
            onb += 1
    print(f"{degisen} kayıt yeniden etiketlendi ({ozet_s}); {onb} önbellek düzeltildi → {yol}")


def cmd_maliyet_tur(a):
    """Sayaç modülünden gelen KESİN tur kullanımını deftere yazar (orkestra kapalıysa sessizce çıkar)."""
    sd = L.durum_dizini()
    if not sd:
        return
    gorev, surec, ajan = "-", "orkestrasyon", "ana-ajan"
    if a.agent_id:
        ajan, surec = "?", "bilinmiyor"
        onb = os.path.join(sd, "oturumlar", f"ajan_{a.agent_id}.json")
        try:
            with open(onb, encoding="utf-8") as f:
                d = json.load(f)
            gorev, surec, ajan = d.get("gorev", "-"), d.get("surec", "bilinmiyor"), d.get("ajan", "?")
        except Exception:
            tr = os.path.join(L.proje_oturum_dizini(L.proje_dizini()), a.oturum, "subagents", f"agent-{a.agent_id}.jsonl")
            o = L.transkript_oku(tr)
            gorev, surec = L.etiketler(o["ilk_kullanici"])
            ajan = L.alt_ajan_meta(tr).get("agentType") or "?"
            if surec == "bilinmiyor":
                surec = "denetim" if "denetci" in ajan else ("is" if "isci" in ajan else ("perspektif" if ("perspektif" in ajan or "ruya" in ajan) else
                        "arastirma" if ajan in ("Explore", "orkestra:arastirmaci") else "bilinmiyor"))
            L.atomik_yaz(onb, json.dumps({"gorev": gorev, "surec": surec, "ajan": ajan}))
    elif os.environ.get("ORKESTRA_PERSPEKTIF"):
        surec, ajan = "perspektif", "perspektif-bakimcisi"
    u = {"input_tokens": a.giris, "output_tokens": a.cikis, "cache_read_input_tokens": a.onb_okuma,
         "cache_creation": {"ephemeral_1h_input_tokens": a.onb_yazma}}  # hook satırlarıyla aynı 1 sa tarifesi
    L.jsonl_ekle(os.path.join(sd, "maliyet.jsonl"), {
        "zaman": L.simdi(), "oturum": a.oturum, "gorev": gorev, "surec": surec, "ajan": ajan, "agent_id": a.agent_id,
        "model": a.model, "giris": a.giris, "cikis": a.cikis, "onbellek_okuma": a.onb_okuma, "onbellek_yazma": a.onb_yazma,
        "maliyet_usd": L.kullanim_maliyeti(a.model, u), "sure_ms": a.sure_ms, "kaynak": "tur", "tarife": "1sa",
        **_tur_isi(sd, gorev, a.oturum), **L.istek_kimlik_alanlari(sd, a.oturum, agent_id=a.agent_id)})


def _tur_isi(sd, gorev, oturum):
    """Tek çözüm ork_lib.is_coz: {'is': ..., ['atif_nedeni': ...]} (hata ve bağsızda is None)."""
    return L.is_alanlari(sd, oturum, gorev)


def cmd_maliyet_anomali(a):
    import maliyet_anomali as MA
    liste = MA.calistir(sd_gerekli(), a.gun or None)
    print(json.dumps(liste, ensure_ascii=False, indent=1) if a.json else MA.metin(liste))


def cmd_maliyet_etki(a):
    import maliyet_etki as ME
    try:
        kesim = datetime.datetime.fromisoformat(a.kesim)
    except ValueError:
        hata(f"--kesim ISO zaman olmalı: {a.kesim!r}")
    if kesim.tzinfo is None:
        kesim = kesim.astimezone()
    r = ME.karsilastir(sd_gerekli(), kesim, a.gun)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else ME.metin(r))


def cmd_maliyet_ozet(a):
    sd = sd_gerekli()
    kayitlar = L.maliyet_kayitlari(sd)
    import analitik as AN
    oid = oturum_id()
    o = {"bugun_usd": round(AN.bugun_usd(kayitlar), 4),  # yerel gün; damga +03:00 ya da Z olsa da aynı
         "oturum_usd": round(sum(r.get("maliyet_usd", 0) for r in kayitlar if r.get("oturum") == oid), 4),
         "toplam_usd": round(sum(r.get("maliyet_usd", 0) for r in kayitlar), 4), "kosu": len(kayitlar)}
    print(json.dumps(o) if a.json else f"bugün ≈${o['bugun_usd']:.2f} · bu oturum ≈${o['oturum_usd']:.2f} · toplam ≈${o['toplam_usd']:.2f} ({o['kosu']} koşu)")


def cmd_maliyet_duzelt(a):
    """Geriye dönük iş atfı: varsayılan kuru koşu; --uygula maliyet_duzeltme.jsonl'e yalnız ekler (ham defter değişmez)."""
    import maliyet_duzelt as MD
    sd = sd_gerekli()
    p = MD.planla(sd)
    n = MD.uygula(sd, p) if a.uygula else None
    print(MD.metin(p, n))


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    mal = alt.add_parser("maliyet").add_subparsers(dest="alt", required=True)
    r = mal.add_parser("rapor")
    r.add_argument("--gun", type=int, default=0)
    r.add_argument("--md", action="store_true")
    r.add_argument("--csv", action="store_true")
    r.add_argument("--cikti")
    r.add_argument("--baglam", help="yalnız bu önekle başlayan baglamlar (ör. RNV ya da RNV/05_sohbet_ajani)")
    r.set_defaults(f=cmd_maliyet_rapor)
    tu = mal.add_parser("tur")
    tu.add_argument("--oturum", required=True)
    tu.add_argument("--agent-id")
    tu.add_argument("--model", required=True)
    for ad in ("--giris", "--cikis", "--onb-okuma", "--onb-yazma", "--sure-ms"):
        tu.add_argument(ad, type=int, default=0)
    tu.set_defaults(f=cmd_maliyet_tur)
    an = mal.add_parser("anomali", help="deterministik maliyet anomali denetimi (kart × koşu × zaman kuralları)")
    an.add_argument("--gun", type=int, default=1, help="son N gün (0 = tümü)")
    an.add_argument("--json", action="store_true")
    an.set_defaults(f=cmd_maliyet_anomali)
    et = mal.add_parser("etki", help="değişiklik öncesi/sonrası maliyet ve kalite karşılaştırması (kalite bekçisi)")
    et.add_argument("--kesim", required=True, help="değişikliğin devreye girdiği an (ISO)")
    et.add_argument("--gun", type=float, default=7, help="her iki pencerenin gün sayısı")
    et.add_argument("--json", action="store_true")
    et.set_defaults(f=cmd_maliyet_etki)
    ge = mal.add_parser("gecmis")
    ge.add_argument("--bu-oturum-dahil", action="store_true")
    ge.set_defaults(f=cmd_maliyet_gecmis)
    ye = mal.add_parser("yeniden-etiketle")
    ye.add_argument("--uygula", action="store_true")
    ye.add_argument("--transkript-dizini", help=argparse.SUPPRESS)
    ye.set_defaults(f=cmd_maliyet_yeniden_etiketle)
    du = mal.add_parser("duzelt", help="işe bağsız geçmiş satırları kart/oturumdan işe atfeder (varsayılan kuru koşu)")
    du.add_argument("--uygula", action="store_true", help="maliyet_duzeltme.jsonl'e ekle (yoksa yalnız sayım)")
    du.set_defaults(f=cmd_maliyet_duzelt)
    oz = mal.add_parser("ozet")
    oz.add_argument("--json", action="store_true")
    oz.set_defaults(f=cmd_maliyet_ozet)
