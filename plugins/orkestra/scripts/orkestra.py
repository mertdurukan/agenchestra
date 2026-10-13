"""orkestra — görev kartları, ortak defter, token defteri ve rüya için komut satırı aracı.

Kullanım (ajanlar Bash'ten çağırır; `orkestra` plugin bin/ ile PATH'tedir):
  orkestra baslat                                   bu projede durum klasörünü açar
  orkestra kart yeni --baslik T --basamak T2 [--sinif S] [--girdi M] [--kabul K]... [--yazma GLOB]... [--bagimli G-001]...
  orkestra kart toplu --json-dosya plan.json       (liste: [{baslik, basamak, kabul_kriterleri, yazma_alani, bagimliliklar, ...}])
  orkestra kart goster G-001 | liste [--hepsi] [--json]
  orkestra kart durum G-001 isleniyor|is-bitti|beklemede|iptal|planlandi [--ozet M] [--cikti YOL]... [--not M]
  orkestra kart denetim G-001 --karar onay|ret --gerekce M [--talimat M]      (yalnız denetçi ajan)
  orkestra kart yukselt G-001 --basamak T3 --neden M
  orkestra kart teslim G-001 [--ozet M]                                        (yalnız ana ajan, onaylı kart)
  orkestra kart agac G-001 [--taban HEAD]         kart başına git çalışma ağacı (<depo>-kart-<id>, dal kart/<id>)
  orkestra kart birlestir G-001                  kart dalını --no-ff birleştirir; çatışmada geri alır, kart beklemede
  orkestra defter ekle G-001 --surec is [--yaptim M] [--sonuc M] [--not M]
  orkestra defter baglam G-001 [--max 2000]     ihtiyacın olan kayıtlar: kart + bağımlılıklar + aynı kartın geçmişi
  orkestra defter oku [--gorev G] [--son N] | ozet
  orkestra maliyet rapor [--gun N] [--md|--csv] [--cikti YOL] | ozet [--json]
  orkestra ruya durum | basla | bitti
  orkestra gunluk ozet [--gun 7]
  orkestra niyet --ne "şu an ne yapılıyor" --neden "neye yarayacak" | --sonuc "ne çıktı" | --goster   (yalnız ana ajan)
`--ajan-id/--ajan-tipi` argümanlarını PreToolUse hook'u ekler; elle verilenler silinir.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASAMAKLAR = ("T0", "T1", "T2", "T3", "T4")


def hata(mesaj: str, kod: int = 2):
    print(f"orkestra: {mesaj}", file=sys.stderr)
    sys.exit(kod)


def sd_gerekli() -> str:
    sd = L.durum_dizini()
    if not sd:
        hata("bu projede orkestra açık değil (`orkestra baslat`).")
    return sd


def oturum_id() -> str:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID") or "-"


# ---------------------------------------------------------------- baslat

README = """# .claude/orkestra — çalışma zamanı durumu

Bu klasörü orkestra plugin'i yönetir; elle düzenleme yapma (hook'lar engeller).

| Dosya | Ne | Kim yazar |
|---|---|---|
| `gorevler/<id>.json` | Görev kartları: kabul kriteri, yazma alanı, bağımlılık, denetimler | `orkestra kart …` |
| `ortak_defter.md` / `.jsonl` | Herkes ne yaptığını yazar; yalnız sona ekleme | SubagentStop/Stop hook'ları + `orkestra defter ekle` |
| `maliyet.jsonl` | Her ajanın her süreç için token ve maliyet kaydı | SubagentStop/Stop hook'ları |
| `gunluk.jsonl` | İstekler (maskeli), skill/ajan kullanımı — skill avcısı okur | UserPromptSubmit/PostToolUse hook'ları |
| `ruya/` | Hafıza bakım raporları | rüya koşusu |
| `onerilen_skill/` | Skill avcısının taslakları (onayın gerekir) | skill-avcisi |
| `raporlar/` | `orkestra maliyet rapor` çıktıları | CLI |
"""


def cmd_baslat(a):
    sd = L.durum_dizini(olustur=True)
    rd = os.path.join(sd, "README.md")
    if not os.path.exists(rd):
        L.atomik_yaz(rd, README)
    print(sd)


# ---------------------------------------------------------------- kart

def _kart_al(sd, gid):
    k = L.kart_oku(sd, gid)
    if not k:
        hata(f"kart yok: {gid}")
    return k


def _kart_kur(sd, d: dict) -> dict:
    basamak = (d.get("basamak") or "T2").upper()
    if basamak not in BASAMAKLAR:
        hata(f"basamak T0..T4 olmalı: {basamak}")
    gid = d.get("id") or L.yeni_kart_id(sd)
    if L.kart_oku(sd, gid):
        hata(f"kart zaten var: {gid}")
    return {
        "id": gid,
        "baslik": d.get("baslik") or "(başlıksız)",
        "sinif": d.get("sinif") or "-",
        "basamak": basamak,
        "baslangic_basamak": basamak,
        "girdi": d.get("girdi") or "",
        "kabul_kriterleri": list(d.get("kabul_kriterleri") or []),
        "yazma_alani": list(d.get("yazma_alani") or []),
        "bagimliliklar": list(d.get("bagimliliklar") or []),
        "durum": "planlandi",
        "oturum": oturum_id(),
        "olusturma": L.simdi(),
        "isciler": [],
        "denetciler": [],
        "denetimler": [],
        "ciktilar": [],
        "gecmis": [{"zaman": L.simdi(), "olay": "olusturuldu", "basamak": basamak}],
    }


def cmd_kart_yeni(a):
    sd = sd_gerekli()
    k = _kart_kur(sd, {"baslik": a.baslik, "sinif": a.sinif, "basamak": a.basamak, "girdi": a.girdi,
                       "kabul_kriterleri": a.kabul, "yazma_alani": a.yazma, "bagimliliklar": a.bagimli})
    if not k["kabul_kriterleri"]:
        hata("en az bir --kabul kriteri gerekli (denetçi buna göre karar verir).")
    L.kart_yaz(sd, k)
    _cakisma_uyarisi(sd, [k])
    print(k["id"])


def _cakisma_uyarisi(sd, ks):
    """Oluşturma sırasında yalnız uyarı: asıl kapı `kart durum … isleniyor` geçişindedir."""
    proje = L.proje_dizini()
    for k in ks:
        for m in L.yazma_cakismalari(sd, proje, k):
            print(f"orkestra: uyarı {k['id']}: {m}", file=sys.stderr)


def cmd_kart_toplu(a):
    sd = sd_gerekli()
    with open(a.json_dosya, encoding="utf-8") as f:
        liste = json.load(f)
    if isinstance(liste, dict):
        liste = liste.get("gorevler") or []
    yerel = {}
    olusan = []
    for d in liste:
        if not d.get("kabul_kriterleri"):
            hata(f"kabul kriteri eksik: {d.get('baslik')}")
    for d in liste:
        takma = d.pop("ref", None)
        d["bagimliliklar"] = [yerel.get(b, b) for b in d.get("bagimliliklar") or []]
        k = _kart_kur(sd, d)
        L.kart_yaz(sd, k)
        if takma:
            yerel[takma] = k["id"]
        olusan.append(k)
    # döngü kontrolü
    harita = {k["id"]: k["bagimliliklar"] for k in L.kartlar(sd)}

    def dongu(n, yol):
        if n in yol:
            return True
        return any(dongu(m, yol | {n}) for m in harita.get(n, []))
    for k in olusan:
        if dongu(k["id"], set()):
            hata(f"bağımlılık döngüsü: {k['id']}")
    _cakisma_uyarisi(sd, olusan)
    print(json.dumps([{"id": k["id"], "baslik": k["baslik"], "basamak": k["basamak"], "bagimliliklar": k["bagimliliklar"]}
                      for k in olusan], ensure_ascii=False))


def cmd_kart_goster(a):
    sd = sd_gerekli()
    k = _kart_al(sd, a.gid)
    k["durum"] = L.kart_durumu_hesapla(k)
    ca = k.get("calisma_agaci") or {}
    if ca.get("yol"):
        k["calisma_agaci_satiri"] = L.CALISMA_AGACI_ONEKI + ca["yol"]
    print(json.dumps(k, ensure_ascii=False, indent=2))


def cmd_kart_liste(a):
    sd = sd_gerekli()
    oid = oturum_id()
    ks = [k for k in L.kartlar(sd) if a.hepsi or k.get("oturum") == oid or k.get("durum") in L.ACIK_DURUMLAR]
    for k in ks:
        k["durum"] = L.kart_durumu_hesapla(k)
    if a.json:
        print(json.dumps(ks, ensure_ascii=False))
        return
    for k in ks:
        print(f"{k['id']:7s} {k['durum']:11s} {k['basamak']} {k['baslik'][:70]}"
              + (f"  ← {','.join(k['bagimliliklar'])}" if k["bagimliliklar"] else ""))
    if not ks:
        print("(kart yok)")


def _kim(a):
    return (a.ajan_id or "bilinmiyor"), (a.ajan_tipi or "bilinmiyor")


def cmd_kart_durum(a):
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    path = L.kart_yolu(sd, a.gid)
    with L.kilit(path):
        k = _kart_al(sd, a.gid)
        if a.durum == "is-bitti":
            if ajan_tipi == "ana":
                hata("ana ajan işçi işi bitiremez: işi bir işçi ajana ver.")
            k["son_is_zamani"] = L.simdi()
            k["son_is_sira"] = L.sonraki_sira(k)
            if ajan_id not in k["isciler"]:
                k["isciler"].append(ajan_id)
            for c in a.cikti or []:
                if c not in k["ciktilar"]:
                    k["ciktilar"].append(c)
            if a.ozet:
                k["son_ozet"] = L.maskele(a.ozet)[:2000]
            k["durum"] = "denetimde"
        else:
            if a.durum in ("iptal", "beklemede", "planlandi") and ajan_tipi not in ("ana", "bilinmiyor"):
                hata("kartı iptal/beklemeye yalnız ana ajan alır.")
            if a.durum == "isleniyor":
                # Çakışma kapısı: aynı fiziksel ağaçta açık kartlarla yazma alanı kesişmesi ya da depo kökü/'**' reddedilir.
                cakismalar = L.yazma_cakismalari(sd, L.proje_dizini(), k)
                if cakismalar:
                    hata(f"{a.gid} isleniyor'a geçemez — " + " | ".join(cakismalar), 5)
            k["durum"] = a.durum
            if a.durum == "beklemede":
                k["beklemede_sira"] = L.sonraki_sira(k)  # sonraki denetimlerle sıralanabilsin
        k["gecmis"].append({"zaman": L.simdi(), "olay": a.durum, "ajan": ajan_tipi, "agent_id": ajan_id,
                            "not": L.maskele(a.not_ or "")[:500]})
        L.kart_yaz(sd, k)
    print(f"{a.gid} → {k['durum']}")


def cmd_kart_denetim(a):
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    if not ajan_tipi.endswith("denetci"):
        hata(f"denetim kararını yalnız denetçi ajan yazar (sen: {ajan_tipi}).", 3)
    path = L.kart_yolu(sd, a.gid)
    with L.kilit(path):
        k = _kart_al(sd, a.gid)
        if ajan_id in k["isciler"]:
            hata("bu kartta işçi olarak çalışan ajan kendi işini denetleyemez.", 3)
        if not k.get("son_is_zamani"):
            hata("denetlenecek işçi çıktısı yok (işçi `kart durum … is-bitti` demedi).", 3)
        kayit = {"zaman": L.simdi(), "sira": L.sonraki_sira(k), "karar": a.karar, "gerekce": L.maskele(a.gerekce)[:3000],
                 "talimat": L.maskele(a.talimat or "")[:3000], "agent_id": ajan_id, "ajan": ajan_tipi,
                 "basamak": k["basamak"]}
        k["denetimler"].append(kayit)
        if ajan_id not in k["denetciler"]:
            k["denetciler"].append(ajan_id)
        k["durum"] = L.kart_durumu_hesapla(k)
        k["gecmis"].append({"zaman": kayit["zaman"], "olay": f"denetim:{a.karar}", "ajan": ajan_tipi, "agent_id": ajan_id})
        L.kart_yaz(sd, k)
        L.atomik_yaz(os.path.join(sd, "gorevler", f"{a.gid}.denetim.json"),
                     json.dumps(k["denetimler"], ensure_ascii=False, indent=2) + "\n")
    print(f"{a.gid} denetim: {a.karar} → {k['durum']}")


def cmd_kart_yukselt(a):
    sd = sd_gerekli()
    b = a.basamak.upper()
    if b not in BASAMAKLAR:
        hata("basamak T0..T4 olmalı")
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if BASAMAKLAR.index(b) <= BASAMAKLAR.index(k["basamak"]):
            hata("yükseltme yalnız yukarı yapılır.")
        k["gecmis"].append({"zaman": L.simdi(), "olay": "yukseltme", "eski": k["basamak"], "yeni": b, "not": a.neden})
        k["basamak"] = b
        k["durum"] = "isleniyor"
        k.pop("son_is_zamani", None)
        k.pop("son_is_sira", None)
        L.kart_yaz(sd, k)
    print(f"{a.gid} → {b}")


def cmd_kart_teslim(a):
    sd = sd_gerekli()
    _, ajan_tipi = _kim(a)
    if ajan_tipi not in ("ana", "bilinmiyor"):
        hata("teslimi yalnız ana ajan yapar.", 3)
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        durum = L.kart_durumu_hesapla(k)
        if durum != "onaylandi":
            hata(f"teslim için denetçi onayı gerekli (durum: {durum}).", 3)
        if (k.get("calisma_agaci") or {}).get("yol"):
            ok, mesaj = _birlestir(k)
            L.kart_yaz(sd, k)
            if not ok:
                hata(f"teslim reddedildi: kart çalışma ağacı birleşmedi — {mesaj}", 4)
            print(mesaj)
        k["durum"] = "teslim"
        k["teslim_ozeti"] = L.maskele(a.ozet or "")[:2000]
        k["gecmis"].append({"zaman": L.simdi(), "olay": "teslim"})
        L.kart_yaz(sd, k)
    L.defter_ekle(sd, {"gorev": a.gid, "surec": "sentez", "ajan": "ana-ajan", "model": "-",
                       "yaptim": "Onaylı çıktıyı topladım ve teslim ettim.", "sonuc": "TESLİM", "not": a.ozet or ""})
    print(f"{a.gid} → teslim")


def _girdi_agacsiz(girdi: str) -> str:
    satirlar = (girdi or "").split("\n")
    if satirlar and satirlar[0].startswith(L.CALISMA_AGACI_ONEKI):
        satirlar = satirlar[1:]
    return "\n".join(satirlar)


def cmd_kart_agac(a):
    sd = sd_gerekli()
    _, ajan_tipi = _kim(a)
    if ajan_tipi not in ("ana", "bilinmiyor"):
        hata("kart çalışma ağacını yalnız ana ajan açar.", 3)
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if L.kart_durumu_hesapla(k) in ("teslim", "iptal"):
            hata(f"kapalı karta çalışma ağacı açılmaz ({k['durum']}).")
        try:
            ca, yeni = L.kart_agaci_ac(L.proje_dizini(), k, a.taban)
        except ValueError as e:
            hata(str(e))
        k["yazma_alani_ilk"] = list(k.get("yazma_alani") or [])
        k["yazma_alani"] = yeni
        k["calisma_agaci"] = ca
        k["girdi"] = L.CALISMA_AGACI_ONEKI + ca["yol"] + "\n" + _girdi_agacsiz(k.get("girdi"))
        k["gecmis"].append({"zaman": L.simdi(), "olay": "calisma-agaci", "yol": ca["yol"], "dal": ca["dal"], "taban": ca["taban"]})
        L.kart_yaz(sd, k)
    print(ca["yol"])


def _birlestir(k) -> tuple[bool, str]:
    """Kartın çalışma ağacını birleştirir ve kartı günceller (yazmaz). Çatışmada kart beklemede, dosyalar not edilir."""
    s = L.kart_agaci_birlestir(k)
    if s["sonuc"] == "tamam":
        ca = k.pop("calisma_agaci")
        ca.update(birlesme=L.simdi(), commit=s.get("commit"))
        k["calisma_agaci_birlesik"] = ca
        if "yazma_alani_ilk" in k:
            k["yazma_alani"] = k.pop("yazma_alani_ilk")
        k["girdi"] = _girdi_agacsiz(k.get("girdi"))
        k.pop("birlestirme_catismasi", None)
        k["gecmis"].append({"zaman": L.simdi(), "olay": "birlestirildi", "commit": s.get("commit"), "not": s["mesaj"][:500]})
        return True, s["mesaj"]
    if s["sonuc"] == "catisma":
        k["durum"] = "beklemede"
        k["beklemede_sira"] = L.sonraki_sira(k)
        k["birlestirme_catismasi"] = s["dosyalar"]
        k["gecmis"].append({"zaman": L.simdi(), "olay": "beklemede", "ajan": "orkestra",
                            "not": ("birleştirme çatışması (otomatik çözülmedi): " + ", ".join(s["dosyalar"]))[:500]})
        return False, s["mesaj"] + " — kart beklemede; çatışmayı elle çöz, sonra yeniden birleştir"
    k["gecmis"].append({"zaman": L.simdi(), "olay": "birlestirme-ret", "not": s["mesaj"][:500]})
    return False, s["mesaj"]


def cmd_kart_birlestir(a):
    sd = sd_gerekli()
    _, ajan_tipi = _kim(a)
    if ajan_tipi not in ("ana", "bilinmiyor"):
        hata("kart dalını yalnız ana ajan birleştirir.", 3)
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if not (k.get("calisma_agaci") or {}).get("yol"):
            hata(f"{a.gid} kartının çalışma ağacı yok (`orkestra kart agac {a.gid}`).")
        ok, mesaj = _birlestir(k)
        L.kart_yaz(sd, k)
    if not ok:
        hata(mesaj, 4)
    print(mesaj)


# ---------------------------------------------------------------- defter

def cmd_defter_ekle(a):
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    if a.surec not in L.SURECLER:
        hata(f"süreç şunlardan biri olmalı: {', '.join(L.SURECLER)}")
    L.defter_ekle(sd, {"gorev": a.gid, "surec": a.surec, "ajan": ajan_tipi, "agent_id": None if ajan_id in ("ana", "bilinmiyor") else ajan_id,
                       "model": "-", "yaptim": a.yaptim, "sonuc": a.sonuc, "not": a.not_, "kaynak": "ajan"})
    print("eklendi")


def _blok_metni(r: dict) -> str:
    return L.defter_blogu(r).strip()


def cmd_defter_baglam(a):
    sd = sd_gerekli()
    k = _kart_al(sd, a.gid)
    ilgili = set(k["bagimliliklar"]) | {a.gid}
    parcalar = [f"# Bağlam: {a.gid} — {k['baslik']}",
                f"Basamak {k['basamak']} · durum {L.kart_durumu_hesapla(k)}",
                "Kabul kriterleri:\n" + "\n".join(f"  {i+1}. {c}" for i, c in enumerate(k["kabul_kriterleri"])),
                "Yazma alanı: " + (", ".join(k["yazma_alani"]) or "(sınırsız)")]
    if k.get("girdi"):
        parcalar.append("Girdi: " + k["girdi"])
    son_ret = [d for d in k["denetimler"] if d["karar"] == "ret"][-1:]
    if son_ret:
        parcalar.append("SON RET — düzeltme talimatı: " + (son_ret[0].get("talimat") or son_ret[0].get("gerekce")))
    for b in k["bagimliliklar"]:
        bk = L.kart_oku(sd, b)
        if bk:
            parcalar.append(f"Bağımlılık {b} ({L.kart_durumu_hesapla(bk)}): çıktılar {', '.join(bk.get('ciktilar') or []) or '-'}"
                            + (f"\n  özet: {bk.get('son_ozet', '')[:400]}" if bk.get("son_ozet") else ""))
    kayitlar = [r for r in L.defter_kayitlari(sd) if r.get("gorev") in ilgili]
    metin = "\n".join(parcalar) + "\n\n# İlgili defter kayıtları (en yeni sonda)\n"
    bloklar = [_blok_metni(r) for r in kayitlar]
    secili = []
    toplam = len(metin)
    for b in reversed(bloklar):
        if toplam + len(b) > a.max:
            break
        secili.insert(0, b)
        toplam += len(b) + 2
    if len(secili) < len(bloklar):
        metin += f"(… {len(bloklar) - len(secili)} eski kayıt atlandı: `orkestra defter oku --gorev {a.gid}`)\n"
    print(metin + "\n\n".join(secili))


def cmd_defter_oku(a):
    sd = sd_gerekli()
    kayitlar = L.defter_kayitlari(sd)
    if a.gorev:
        kayitlar = [r for r in kayitlar if r.get("gorev") == a.gorev]
    for r in kayitlar[-a.son:]:
        print(_blok_metni(r) + "\n")


def cmd_defter_ozet(a):
    sd = sd_gerekli()
    son = {}
    for r in L.defter_kayitlari(sd):
        son[r.get("gorev", "-")] = r
    for g, r in son.items():
        print(f"{g:8s} {r.get('zaman', '')[:16]} {r.get('surec', '-'):10s} {r.get('ajan', '-'):24s} {str(r.get('sonuc') or r.get('yaptim') or '')[:80]}")


# ---------------------------------------------------------------- maliyet

def _maliyet_kayitlari(sd, gun):
    kayitlar = L.maliyet_kayitlari(sd)
    if gun:
        esik = (datetime.datetime.now().astimezone() - datetime.timedelta(days=gun)).isoformat()
        kayitlar = [r for r in kayitlar if r.get("zaman", "") >= esik]
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


def cmd_maliyet_rapor(a):
    sd = sd_gerekli()
    kayitlar = _maliyet_kayitlari(sd, a.gun)
    if a.csv:
        buf = io.StringIO()
        alanlar = ["zaman", "oturum", "gorev", "surec", "ajan", "agent_id", "model", "giris", "cikis", "onbellek_okuma",
                   "onbellek_yazma", "maliyet_usd", "sure_ms", "tur", "arac_cagrisi"]
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
        metin += "\n" + _md_tablo("Gün", ["gun"], _pivot([dict(r, gun=r.get("zaman", "")[:10]) for r in kayitlar], ["gun"]))
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
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ruya
    pdir = os.path.dirname(ruya.hafiza_dizini(L.proje_dizini()))
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
                surec = "denetim" if "denetci" in ajan else ("is" if "isci" in ajan else ("ruya" if "ruya" in ajan else
                        "arastirma" if ajan in ("Explore", "orkestra:arastirmaci") else "bilinmiyor"))
            L.atomik_yaz(onb, json.dumps({"gorev": gorev, "surec": surec, "ajan": ajan}))
    elif os.environ.get("ORKESTRA_RUYA"):
        surec, ajan = "ruya", "ruya-bakimcisi"
    u = {"input_tokens": a.giris, "output_tokens": a.cikis, "cache_read_input_tokens": a.onb_okuma,
         "cache_creation_input_tokens": a.onb_yazma}
    L.jsonl_ekle(os.path.join(sd, "maliyet.jsonl"), {
        "zaman": L.simdi(), "oturum": a.oturum, "gorev": gorev, "surec": surec, "ajan": ajan, "agent_id": a.agent_id,
        "model": a.model, "giris": a.giris, "cikis": a.cikis, "onbellek_okuma": a.onb_okuma, "onbellek_yazma": a.onb_yazma,
        "maliyet_usd": L.kullanim_maliyeti(a.model, u), "sure_ms": a.sure_ms, "kaynak": "tur"})


def cmd_maliyet_ozet(a):
    sd = sd_gerekli()
    kayitlar = L.maliyet_kayitlari(sd)
    bugun = datetime.date.today().isoformat()
    oid = oturum_id()
    o = {"bugun_usd": round(sum(r.get("maliyet_usd", 0) for r in kayitlar if r.get("zaman", "").startswith(bugun)), 4),
         "oturum_usd": round(sum(r.get("maliyet_usd", 0) for r in kayitlar if r.get("oturum") == oid), 4),
         "toplam_usd": round(sum(r.get("maliyet_usd", 0) for r in kayitlar), 4), "kosu": len(kayitlar)}
    print(json.dumps(o) if a.json else f"bugün ≈${o['bugun_usd']:.2f} · bu oturum ≈${o['oturum_usd']:.2f} · toplam ≈${o['toplam_usd']:.2f} ({o['kosu']} koşu)")


# ---------------------------------------------------------------- rüya

def cmd_ruya(a):
    sd = sd_gerekli()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ruya
    if a.islem == "durum":
        print(json.dumps(ruya.durum(sd), ensure_ascii=False, indent=2))
    elif a.islem == "basla":
        print(ruya.baslat(sd, L.proje_dizini(), zorla=True))
    elif a.islem == "bitti":
        ruya.bitti_isaretle(sd)
        print("rüya raporu okundu olarak işaretlendi")
    elif a.islem == "basladi":
        ruya.basladi_isaretle(sd)
        print("rüya başladı")
    elif a.islem == "kaydet":
        if not a.yol or not os.path.exists(a.yol):
            hata("rapor yolu gerekli ve var olmalı: orkestra ruya kaydet <yol>")
        ruya.kaydet(sd, a.yol)
        print(f"rüya raporu kaydedildi: {a.yol}")
    elif a.islem == "hafiza":
        print(ruya.hafiza_dizini(L.proje_dizini()))


# ---------------------------------------------------------------- günlük

def cmd_gunluk_ozet(a):
    sd = sd_gerekli()
    esik = (datetime.datetime.now().astimezone() - datetime.timedelta(days=a.gun)).isoformat()
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


# ---------------------------------------------------------------- arayüz özeti

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


# ---------------------------------------------------------------- güncelle

def cmd_guncelle(a):
    pazar = "claude-orchestration"
    exe = L.claude_exe()
    if not exe:
        hata("claude.exe bulunamadı (CLAUDE_CODE_EXECPATH ya da %APPDATA%/Claude/claude-code/<sürüm>/*/claude.exe).")
    kaynak = L.pazar_kaynagi(pazar)
    if kaynak and os.path.isdir(os.path.join(kaynak, ".git")):
        # Yayın klonu: önce kaynağı ilerlet; kirliyse (elle düzenlenmiş) güncellemeyi reddet.
        g = ["git", "-C", kaynak]
        print("$ " + " ".join(g + ["status", "--porcelain"]))
        if not a.kuru:
            r = subprocess.run(g + ["status", "--porcelain"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                hata(f"yayın klonu okunamadı ({kaynak}): {(r.stderr or r.stdout).strip()}")
            if r.stdout.strip():
                hata(f"yayın klonunda commitlenmemiş değişiklik var ({kaynak}); güncelleme reddedildi. Klon elle düzenlenmez: değişiklikleri geri al (git -C {kaynak} checkout -f .) ya da klonu yeniden kur (araclar/yayin_kur.py).")
        for k in (g + ["fetch", "-q", "origin"], g + ["merge", "--ff-only", "-q", "@{u}"]):
            print("$ " + " ".join(k))
            if a.kuru:
                continue
            r = subprocess.run(k, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                hata(f"yayın klonu ilerletilemedi ({' '.join(k[3:])}): {(r.stderr or r.stdout).strip()}")
    proje = L.proje_dizini()
    adlar = []
    try:
        with open(os.path.join(os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json"), encoding="utf-8") as f:
            for anahtar, girdiler in (json.load(f).get("plugins") or {}).items():
                ad, _, p = anahtar.partition("@")
                if p == pazar and any(os.path.normcase(os.path.abspath(g.get("projectPath") or "")) == os.path.normcase(proje)
                                      and g.get("scope") == "project" for g in girdiler):
                    adlar.append(ad)
    except Exception:
        pass
    if not adlar:
        hata(f"bu projede ({proje}) kurulu {pazar} plugin'i bulunamadı.")
    komutlar = [[exe, "plugin", "marketplace", "update", pazar]] + [[exe, "plugin", "update", f"{ad}@{pazar}", "--scope", "project"] for ad in adlar]
    for k in komutlar:
        print("$ " + " ".join(f'"{x}"' if " " in x else x for x in k))
        if a.kuru:
            continue
        r = subprocess.run(k, cwd=proje, capture_output=True, text=True, encoding="utf-8", errors="replace")
        cikti = (r.stdout + r.stderr).strip()
        if cikti:
            print("  " + cikti.replace(chr(10), chr(10) + "  "))
        if r.returncode != 0:
            hata(f"komut başarısız (çıkış {r.returncode}).")
    if not a.kuru:
        print("Tamam. Değişiklik yeni oturumda yüklenir: yeni oturum aç ya da /reload-plugins.")


# ---------------------------------------------------------------- argparse

def main():
    p = argparse.ArgumentParser(prog="orkestra", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ajan-id", dest="ajan_id", help=argparse.SUPPRESS)
    p.add_argument("--ajan-tipi", dest="ajan_tipi", help=argparse.SUPPRESS)
    alt = p.add_subparsers(dest="komut", required=True)

    alt.add_parser("baslat").set_defaults(f=cmd_baslat)
    gc = alt.add_parser("guncelle", help="plugin önbelleğini kaynak depodan yenile")
    gc.add_argument("--kuru", action="store_true", help="yalnız komutları yaz")
    gc.set_defaults(f=cmd_guncelle)

    kart = alt.add_parser("kart").add_subparsers(dest="alt", required=True)
    y = kart.add_parser("yeni")
    y.add_argument("--baslik", required=True)
    y.add_argument("--basamak", default="T2")
    y.add_argument("--sinif")
    y.add_argument("--girdi")
    y.add_argument("--kabul", action="append", default=[])
    y.add_argument("--yazma", action="append", default=[])
    y.add_argument("--bagimli", action="append", default=[])
    y.set_defaults(f=cmd_kart_yeni)
    t = kart.add_parser("toplu")
    t.add_argument("--json-dosya", required=True)
    t.set_defaults(f=cmd_kart_toplu)
    g = kart.add_parser("goster")
    g.add_argument("gid")
    g.set_defaults(f=cmd_kart_goster)
    li = kart.add_parser("liste")
    li.add_argument("--hepsi", action="store_true")
    li.add_argument("--json", action="store_true")
    li.set_defaults(f=cmd_kart_liste)
    du = kart.add_parser("durum")
    du.add_argument("gid")
    du.add_argument("durum", choices=["isleniyor", "is-bitti", "beklemede", "iptal", "planlandi"])
    du.add_argument("--ozet")
    du.add_argument("--cikti", action="append", default=[])
    du.add_argument("--not", dest="not_")
    du.set_defaults(f=cmd_kart_durum)
    de = kart.add_parser("denetim")
    de.add_argument("gid")
    de.add_argument("--karar", required=True, choices=["onay", "ret"])
    de.add_argument("--gerekce", required=True)
    de.add_argument("--talimat")
    de.set_defaults(f=cmd_kart_denetim)
    yu = kart.add_parser("yukselt")
    yu.add_argument("gid")
    yu.add_argument("--basamak", required=True)
    yu.add_argument("--neden", required=True)
    yu.set_defaults(f=cmd_kart_yukselt)
    te = kart.add_parser("teslim")
    te.add_argument("gid")
    te.add_argument("--ozet")
    te.set_defaults(f=cmd_kart_teslim)
    ag = kart.add_parser("agac", help="kart başına git çalışma ağacı aç")
    ag.add_argument("gid")
    ag.add_argument("--taban", default="HEAD", help="worktree'nin açılacağı commit (varsayılan: deponun HEAD'i)")
    ag.set_defaults(f=cmd_kart_agac)
    bi = kart.add_parser("birlestir", help="kart dalını --no-ff birleştir ve worktree'yi temizle")
    bi.add_argument("gid")
    bi.set_defaults(f=cmd_kart_birlestir)

    defter = alt.add_parser("defter").add_subparsers(dest="alt", required=True)
    e = defter.add_parser("ekle")
    e.add_argument("gid")
    e.add_argument("--surec", required=True)
    e.add_argument("--yaptim")
    e.add_argument("--sonuc")
    e.add_argument("--not", dest="not_")
    e.set_defaults(f=cmd_defter_ekle)
    b = defter.add_parser("baglam")
    b.add_argument("gid")
    b.add_argument("--max", type=int, default=2000)
    b.set_defaults(f=cmd_defter_baglam)
    o = defter.add_parser("oku")
    o.add_argument("--gorev")
    o.add_argument("--son", type=int, default=10)
    o.set_defaults(f=cmd_defter_oku)
    defter.add_parser("ozet").set_defaults(f=cmd_defter_ozet)

    mal = alt.add_parser("maliyet").add_subparsers(dest="alt", required=True)
    r = mal.add_parser("rapor")
    r.add_argument("--gun", type=int, default=0)
    r.add_argument("--md", action="store_true")
    r.add_argument("--csv", action="store_true")
    r.add_argument("--cikti")
    r.set_defaults(f=cmd_maliyet_rapor)
    tu = mal.add_parser("tur")
    tu.add_argument("--oturum", required=True)
    tu.add_argument("--agent-id")
    tu.add_argument("--model", required=True)
    for ad in ("--giris", "--cikis", "--onb-okuma", "--onb-yazma", "--sure-ms"):
        tu.add_argument(ad, type=int, default=0)
    tu.set_defaults(f=cmd_maliyet_tur)
    ge = mal.add_parser("gecmis")
    ge.add_argument("--bu-oturum-dahil", action="store_true")
    ge.set_defaults(f=cmd_maliyet_gecmis)
    oz = mal.add_parser("ozet")
    oz.add_argument("--json", action="store_true")
    oz.set_defaults(f=cmd_maliyet_ozet)

    ru = alt.add_parser("ruya")
    ru.add_argument("islem", choices=["durum", "basla", "basladi", "kaydet", "bitti", "hafiza"])
    ru.add_argument("yol", nargs="?")
    ru.set_defaults(f=cmd_ruya)

    ui = alt.add_parser("ui-ozet")
    ui.add_argument("--oturum")
    ui.add_argument("--yaz", action="store_true")
    ui.set_defaults(f=cmd_ui_ozet)
    pa = alt.add_parser("panel")
    pa.add_argument("--port", type=int, default=8765)
    pa.add_argument("--on-planda", action="store_true", help="sunucuyu bu süreçte çalıştır (Ctrl+C ile durur)")
    pa.add_argument("--ac", action="store_true", help="adresi varsayılan tarayıcıda aç")
    pa.set_defaults(f=cmd_panel)

    import niyet
    niyet.ekle_ayristirici(alt)

    gu = alt.add_parser("gunluk").add_subparsers(dest="alt", required=True)
    go = gu.add_parser("ozet")
    go.add_argument("--gun", type=int, default=7)
    go.set_defaults(f=cmd_gunluk_ozet)

    # Hook, kimlik argümanlarını komutun SONUNA ekler; argparse'tan önce her yerden ayıkla.
    argv, kimlik = [], {}
    it = iter(sys.argv[1:])
    for x in it:
        if x in ("--ajan-id", "--ajan-tipi"):
            kimlik[x] = next(it, "")
        elif x.startswith(("--ajan-id=", "--ajan-tipi=")):
            k, v = x.split("=", 1)
            kimlik[k] = v
        else:
            argv.append(x)
    a = p.parse_args(argv)
    a.ajan_id = kimlik.get("--ajan-id") or None
    a.ajan_tipi = kimlik.get("--ajan-tipi") or None
    a.f(a)
    # Durumu değiştiren komutlardan sonra arayüz anlık görüntüsünü yenile.
    alt_komut = getattr(a, "alt", None)
    degistiren = {"kart", "ruya", "baslat"}
    if a.komut in degistiren or (a.komut, alt_komut) in {("defter", "ekle"), ("maliyet", "tur"), ("maliyet", "gecmis")}:
        sd = L.durum_dizini()
        if sd and not (a.komut == "kart" and alt_komut in ("goster", "liste")):
            import ozet
            ozet.yaz(sd, L.proje_dizini())


if __name__ == "__main__":
    main()
