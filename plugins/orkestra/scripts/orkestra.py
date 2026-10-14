"""orkestra — görev kartları, ortak defter, token defteri ve perspektif için komut satırı aracı.

Kullanım (ajanlar Bash'ten çağırır; `orkestra` plugin bin/ ile PATH'tedir):
  orkestra baslat                                   bu projede durum klasörünü açar
  orkestra kart yeni --baslik T --basamak T2 [--sinif S] [--girdi M] [--kabul K]... [--yazma GLOB]... [--bagimli G-001]...
                     [--test-komutu M] [--test-alani GLOB]...     (--sinif kod ise ikisi ZORUNLU; glob proje köküne göre)
                     [--test-koku MUTLAK_DIZIN]                    (kod kartı, isteğe bağlı: test kökü proje yerine bu dizin)
  orkestra kart toplu plan.json | --json-dosya plan.json   (liste: [{baslik, basamak, kabul_kriterleri, yazma_alani, bagimliliklar,
                                                    test_komutu, test_alani, ...}])
  orkestra kart goster G-001 | liste [--hepsi] [--json]
  orkestra kart durum G-001 isleniyor|is-bitti|beklemede|iptal|planlandi [--ozet M] [--cikti YOL]... [--not M]
  orkestra kart test-kos G-001 --asama kirmizi|yesil [--zaman-asimi SN]     (kod kartı; geçti → 0, geçmedi → 4)
        kirmizi: kod yokken test BAŞARISIZ olmalı; olursa test dosyaları sha256 ile kilitlenir (kilitliyken hata)
        yesil:   test GEÇMELİ ve test dosyaları kilitle birebir aynı olmalı
  orkestra kart test-kilit-ac G-001 --neden M                                (yalnız ana ajan)
  orkestra kart test-ayar G-001 [--test-koku YOL] [--test-komutu M] [--test-alani GLOB]...   (yalnız ana ajan;
        kilitliyken yalnız test_koku değişir ve yeni kökteki test dosyaları kilitle birebir aynı olmalı)
  orkestra kart denetim G-001 --karar onay|ret --gerekce M [--talimat M]      (yalnız denetçi ajan;
        kod kartında onay için son is-bitti'den sonraki en son test koşusu geçen yeşil olmalı ve dosyalar kilitle aynı)
  orkestra kart yukselt G-001 --basamak T3 --neden M
  orkestra kart teslim G-001 [--ozet M]                                        (yalnız ana ajan, onaylı kart)
  orkestra kart agac G-001 [--taban HEAD]         kart başına git çalışma ağacı (<depo>-kart-<id>, dal kart/<id>)
  orkestra kart birlestir G-001                  kart dalını --no-ff birleştirir; çatışmada geri alır, kart beklemede
  orkestra defter ekle G-001 --surec is [--yaptim M] [--sonuc M] [--not M]
  orkestra defter baglam G-001 [--max 2000]     ihtiyacın olan kayıtlar: kart + bağımlılıklar + aynı kartın geçmişi
  orkestra defter oku [--gorev G] [--son N] | ozet
  orkestra maliyet rapor [--gun N] [--md|--csv] [--cikti YOL] | ozet [--json] | yeniden-etiketle [--uygula]
  orkestra perspektif durum | basla | bitti
  orkestra gunluk ozet [--gun 7]
  orkestra onay liste [--durum D] [--tur T] [--json] | goster ID | iste --baslik B --metin M [--secenek S]... [--oturum O]
  orkestra onay karar ID (--onay|--ret) [--secim S] [--not N] | al ID [--oturum O] | uygulandi ID --ozet Z | iptal ID --not N | esitle
  orkestra kural liste [--json] | oner --metin M [--neden N] | ekle --metin M [--neden N] | duzenle ID --metin M | kaldir ID --not N
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
import hashlib
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import ret_nedeni as RN  # noqa: E402

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
| `perspektif/` | Hafıza bakım raporları | perspektif koşusu |
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


RISKLER = ("dusuk", "orta", "yuksek")


def _risk_dogrula(d: dict):
    """N3: verilmediyse None (alan yazılmaz); geçersizse hata."""
    r = d.get("risk")
    if r is None:
        return None
    if not isinstance(r, str) or r not in RISKLER:
        hata(f"risk dusuk|orta|yuksek olmalı: {r!r} ({d.get('baslik') or '(başlıksız)'})")
    return r


def _sayi_dogrula(ad: str, v, tam: bool):
    if v is None:
        return None
    try:
        if isinstance(v, bool):
            raise ValueError
        n = float(v)
        if tam:
            if n != int(n) or (isinstance(v, str) and not re.fullmatch(r"\s*\d+\s*", v)):
                raise ValueError
            n = int(n)
        elif n == int(n) and isinstance(v, int):
            n = int(v)
    except (TypeError, ValueError, OverflowError):
        hata(f"{ad} {'tam sayı' if tam else 'sayı'} olmalı: {v!r}")
    if n < 0:
        hata(f"{ad} negatif olamaz: {v!r}")
    return n


def _butce_dogrula(d: dict):
    """N4: yalnız kayıt. {usd, token} (ikisi de isteğe bağlı) -> {usd, token, kaynak:'elle', esik_surumu:None}."""
    b = d.get("butce")
    if b is None:
        return None
    if not isinstance(b, dict):
        hata(f"butce {{usd, token}} nesnesi olmalı: {b!r}")
    usd = _sayi_dogrula("butce.usd", b.get("usd"), False)
    token = _sayi_dogrula("butce.token", b.get("token"), True)
    if usd is None and token is None:
        return None
    return {"usd": usd, "token": token, "kaynak": "elle", "esik_surumu": None}


def _kart_kur(sd, d: dict, onbellek: dict | None = None) -> dict:
    basamak = (d.get("basamak") or "T2").upper()
    if basamak not in BASAMAKLAR:
        hata(f"basamak T0..T4 olmalı: {basamak}")
    test_alanlari = _test_alanlari_dogrula(d)
    risk = _risk_dogrula(d)
    butce = _butce_dogrula(d)
    _merkez_saglamla(sd)  # K2: bozuk/eksik isler.json bağ çözümünü düşürmez
    _acik_is_dogrula(sd, d.get("is"))  # doğrulama kart sayacından önce: hata sayacı ilerletmez
    gid = d.get("id") or L.yeni_kart_id(sd)
    if L.kart_oku(sd, gid):
        hata(f"kart zaten var: {gid}")
    yazma = list(d.get("yazma_alani") or [])
    bag = _kart_is_bag_kur(sd, gid, d.get("baslik") or "", yazma, d.get("is"), onbellek)
    k = {
        "id": gid,
        "baslik": d.get("baslik") or "(başlıksız)",
        "sinif": d.get("sinif") or "-",
        "basamak": basamak,
        "baslangic_basamak": basamak,
        "girdi": d.get("girdi") or "",
        "kabul_kriterleri": list(d.get("kabul_kriterleri") or []),
        "yazma_alani": yazma,
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
    if risk is not None:
        k["risk"] = risk
    if butce is not None:
        k["butce"] = butce
    if test_alanlari:
        k.update(test_alanlari)
    k["is"] = bag
    adim = _ik().adim_coz(k["baslik"])
    if adim:
        k["adim"] = adim
    return k


def _test_alanlari_dogrula(d: dict) -> dict | None:
    """sinif 'kod' ise test_komutu (boş olmayan metin) ve test_alani (boş olmayan glob listesi) zorunlu; değilse None.
    İsteğe bağlı test_koku (var olan mutlak dizin) yalnız kod kartında kabul edilir; test_alani ve test_komutu ona göredir."""
    ad = d.get("baslik") or "(başlıksız)"
    tk = d.get("test_koku")
    if (d.get("sinif") or "").strip().lower() != "kod":
        if tk:
            hata(f"test_koku yalnız kod kartında (sinif kod) anlamlı: {ad}")
        return None
    if tk is not None and tk != "":
        try:
            tk = L.test_koku_dogrula(tk)
        except ValueError as e:
            hata(f"{e}: {ad}")
    komut = d.get("test_komutu")
    if not isinstance(komut, str) or not komut.strip():
        hata(f"kod kartında test_komutu zorunlu (boş olmayan metin; --test-komutu): {ad}")
    alan = d.get("test_alani")
    if isinstance(alan, str):
        alan = [alan]
    if not isinstance(alan, list) or not [g for g in alan if isinstance(g, str) and g.strip()]:
        hata(f"kod kartında test_alani zorunlu (boş olmayan glob listesi; --test-alani): {ad}")
    sonuc = {"test_komutu": komut.strip(), "test_alani": [g.strip() for g in alan if isinstance(g, str) and g.strip()],
             "test_kilidi": None, "test_kosulari": []}
    if tk:
        sonuc["test_koku"] = tk
    return sonuc


def cmd_kart_yeni(a):
    sd = sd_gerekli()
    if not a.kabul:  # iş/klasör açılmadan önce
        hata("en az bir --kabul kriteri gerekli (denetçi buna göre karar verir).")
    k = _kart_kur(sd, {"baslik": a.baslik, "sinif": a.sinif, "basamak": a.basamak, "girdi": a.girdi,
                       "kabul_kriterleri": a.kabul, "yazma_alani": a.yazma, "bagimliliklar": a.bagimli,
                       "test_komutu": a.test_komutu, "test_alani": a.test_alani, "test_koku": a.test_koku,
                       "is": a.is_id, "risk": a.risk,
                       "butce": ({"usd": a.butce_usd, "token": a.butce_token}
                                 if a.butce_usd is not None or a.butce_token is not None else None)})
    if not k["kabul_kriterleri"]:
        hata("en az bir --kabul kriteri gerekli (denetçi buna göre karar verir).")
    L.kart_yaz(sd, k)
    _kart_is_bagla(sd, k)
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
    yol = a.json_dosya or a.json_yol
    if not yol:
        hata("plan dosyası gerekli: orkestra kart toplu plan.json (ya da --json-dosya plan.json)")
    with open(yol, encoding="utf-8") as f:
        liste = json.load(f)
    if isinstance(liste, dict):
        liste = liste.get("gorevler") or []
    yerel = {}
    olusan = []
    _merkez_saglamla(sd)
    for d in liste:  # hiçbir kart oluşmadan önce hepsini doğrula
        if not d.get("kabul_kriterleri"):
            hata(f"kabul kriteri eksik: {d.get('baslik')}")
        _test_alanlari_dogrula(d)
        _risk_dogrula(d)
        _butce_dogrula(d)
        _acik_is_dogrula(sd, d.get("is"))
    onbellek = {}  # aynı klasöre çözülen kartlar tek işe bağlanır
    for d in liste:
        takma = d.pop("ref", None)
        d["bagimliliklar"] = [yerel.get(b, b) for b in d.get("bagimliliklar") or []]
        k = _kart_kur(sd, d, onbellek)
        L.kart_yaz(sd, k)
        _kart_is_bagla(sd, k)
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


def _sha_birlestir(parcalar) -> str:
    h = hashlib.sha256()
    for p in parcalar:
        b = p if isinstance(p, bytes) else str(p).encode("utf-8")
        h.update(str(len(b)).encode() + b":" + b)
    return h.hexdigest()


def _cikti_ozeti_sha(k: dict) -> str:
    """Kartın ciktilar dosyalarının birleşik sha256'sı (var olmayan atlanır; liste sırası sabit)."""
    parcalar = []
    for c in k.get("ciktilar") or []:
        yol = c if os.path.isabs(c) else os.path.join(L.proje_dizini(), c)
        if os.path.isfile(yol):
            with open(yol, "rb") as f:
                parcalar.append(f.read())
    return _sha_birlestir(parcalar)


def _girdi_sha(k: dict) -> str:
    return _sha_birlestir([_girdi_agacsiz(k.get("girdi")), json.dumps(k.get("kabul_kriterleri") or [], ensure_ascii=False),
                           k.get("test_komutu") or ""])


def _is_turu(k: dict, a, ajan_id: str, ajan_tipi: str, sira: int) -> dict:
    """N2: o an koşan işçinin gerçek basamağı yalnız ajan tipinden ('orkestra:isci-tN' -> 'TN'); kart alanından kopyalanmaz."""
    ad = ajan_tipi.split(":", 1)[-1].lower()
    m = re.fullmatch(r"isci-t([0-4])", ad)
    t = {"sira": sira, "basamak": ("T" + m.group(1)) if m else None, "agent_id": ajan_id}
    if not m:
        t["basamak_kaynak"] = "bilinmiyor"
    surec = getattr(a, "surec", None)
    if not surec and ad.startswith("isci"):
        surec = "is"
    t["surec"] = surec or None
    t["cikti_ozeti_sha"] = _cikti_ozeti_sha(k)
    t["girdi_sha"] = _girdi_sha(k)
    return t


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
            k.setdefault("is_turlari", []).append(_is_turu(k, a, ajan_id, ajan_tipi, k["son_is_sira"]))
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


def _neden_kodlari() -> str:
    return ", ".join(RN.NEDENLER)


def _neden_yardim() -> str:
    satirlar = [f"  {k}: {v}" for k, v in RN.NEDENLER.items()]
    return "\n".join(["ret için ZORUNLU ret nedeni kodu (onayda yok sayılır). Geçerli kodlar:"] + satirlar)


def cmd_kart_denetim(a):
    neden = getattr(a, "neden", None)
    if a.karar == "ret":
        if not neden:
            hata(f"ret kararında --neden <kod> zorunlu. Geçerli kodlar: {_neden_kodlari()}", 2)
        if neden not in RN.NEDENLER:
            hata(f"geçersiz ret nedeni kodu: {neden!r}. Geçerli kodlar: {_neden_kodlari()}", 2)
    else:
        neden = None  # onayda --neden yok sayılır
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
        if a.karar == "onay" and k.get("sinif") == "kod":
            engel = _yesil_kapi_engeli(k)
            if engel:
                hata(f"kod kartında onay için taze ve geçen bir yeşil test koşusu gerekli: {engel} "
                     f"(`orkestra kart test-kos {a.gid} --asama yesil`). Karar kaydedilmedi.", 3)
        kayit = {"zaman": L.simdi(), "sira": L.sonraki_sira(k), "karar": a.karar, "gerekce": L.maskele(a.gerekce)[:3000],
                 "talimat": L.maskele(a.talimat or "")[:3000], "agent_id": ajan_id, "ajan": ajan_tipi,
                 "basamak": k["basamak"]}
        if neden:
            kayit["neden"] = neden
            kayit["kok"] = RN.kok(neden)
        k["denetimler"].append(kayit)
        if ajan_id not in k["denetciler"]:
            k["denetciler"].append(ajan_id)
        k["durum"] = L.kart_durumu_hesapla(k)
        olay = {"zaman": kayit["zaman"], "olay": f"denetim:{a.karar}", "ajan": ajan_tipi, "agent_id": ajan_id}
        if neden:
            olay["neden"] = neden
        k["gecmis"].append(olay)
        L.kart_yaz(sd, k)
        L.atomik_yaz(os.path.join(sd, "gorevler", f"{a.gid}.denetim.json"),
                     json.dumps(k["denetimler"], ensure_ascii=False, indent=2) + "\n")
    print(f"{a.gid} denetim: {a.karar} → {k['durum']}")


def _yesil_kapi_engeli(k: dict) -> str | None:
    """Kod kartı onayı için engel metni; engel yoksa None. Koşul: son is-bitti'den SONRAKİ en son test koşusu
    geçen bir yeşil VE şu an yeniden hesaplanan test dosyası özetleri kilitle birebir aynı."""
    try:  # ağaç proje kökünü kapsamıyorsa paylaşılan ağaca sessizce düşülmez (önceki yeşil de ağacı sınamadı)
        kok = L.kart_proje_koku(L.proje_dizini(), k)
    except ValueError as e:
        return str(e)
    kosular = k.get("test_kosulari") or []
    son_is_sira = k.get("son_is_sira")
    if son_is_sira is not None:
        sonraki = [x for x in kosular if (x.get("sira") or 0) > son_is_sira]
    else:
        sonraki = [x for x in kosular if x.get("zaman", "") >= (k.get("son_is_zamani") or "")]
    if not sonraki:
        return "son is-bitti'den sonra yeşil koşu yok (yoksa bayat)"
    son = sonraki[-1]
    if son.get("asama") != "yesil":
        return "en son test koşusu yeşil değil"
    if not son.get("gecti"):
        return "en son yeşil koşu geçmedi"
    # Koşunun kökü güncel test kökü olmalı (test-ayar ile kök değişince eski kökteki yeşil kanıt değildir).
    # Kök alanı olmayan eski kayıtlar yalnız test_koku'suz kartta geçerli kalır (geriye uyum).
    kosu_koku = son.get("kok")
    if kosu_koku is None:
        if k.get("test_koku"):
            return "en son yeşil koşunun test kökü kayıtlı değil; güncel test kökünde yeniden yeşil koşulmalı"
    elif L._kiyas(os.path.abspath(kosu_koku)) != L._kiyas(os.path.abspath(kok)):
        return (f"en son yeşil koşu başka bir test kökünde ({kosu_koku}); güncel test kökünde ({kok}) yeniden "
                "yeşil koşulmalı")
    if not k.get("test_kilidi"):
        return "test kilidi yok"
    mevcut = L.test_dosyasi_ozetleri(kok, k.get("test_alani") or [])
    if not L.kilitle_tutarli(k["test_kilidi"], mevcut):
        fark = L.kilit_farki(k["test_kilidi"].get("dosyalar"), mevcut)
        return "yeşilden sonra test dosyaları kilitten saptı (" + ", ".join(
            f"{ad}: {len(v)}" for ad, v in fark.items() if v) + ")"
    return None


def cmd_kart_test_kos(a):
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    path = L.kart_yolu(sd, a.gid)
    k = _kart_al(sd, a.gid)
    if k.get("sinif") != "kod":
        hata(f"test-kos yalnız kod kartında çalışır (sinif: {k.get('sinif')}).")
    if not k.get("test_komutu") or not k.get("test_alani"):
        hata("kartta test_komutu/test_alani yok.")
    if a.asama == "kirmizi" and k.get("test_kilidi"):
        hata("test dosyaları zaten kilitli: kırmızı yeniden koşulamaz (kilidi yalnız ana ajan açar: `kart test-kilit-ac`).")
    if a.asama == "yesil" and not k.get("test_kilidi"):
        hata("test dosyalarında kilit yok: önce kırmızı aşama koşulmalı (`kart test-kos … --asama kirmizi`).")
    if a.zaman_asimi <= 0:
        hata("--zaman-asimi pozitif olmalı.")
    try:  # kart ağacı varsa testler ve özetler ağaçtaki karşılıkta; ağaç proje kökünü kapsamıyorsa açık hata
        proje = L.kart_proje_koku(L.proje_dizini(), k)
    except ValueError as e:
        hata(str(e))
    once = L.test_dosyasi_ozetleri(proje, k["test_alani"])
    if not once:
        if k.get("test_koku"):
            hata(f"test dosyası yok: test_alani ({', '.join(k['test_alani'])}) test kökünde ({proje}) hiçbir dosyaya "
                 "uymuyor.")
        hata(f"test dosyası yok: test_alani ({', '.join(k['test_alani'])}) hiçbir proje dosyasına uymuyor.")
    zaman = L.simdi()
    kod, cikti, sure = L.kabuk_kos(k["test_komutu"], proje, a.zaman_asimi)
    sonra = L.test_dosyasi_ozetleri(proje, k["test_alani"])
    karar = _test_karari(sd, a.gid, k, proje, kod, cikti, once)
    with L.kilit(path):
        k = _kart_al(sd, a.gid)  # koşu sürerken kart değişmiş olabilir
        k.setdefault("test_kosulari", [])
        if a.asama == "kirmizi":
            if k.get("test_kilidi"):
                hata("test dosyaları koşu sırasında kilitlendi; kırmızı kaydedilmedi.")
            gecti = karar["kirmizi"]
            hash_tutarli = None  # kırmızıda kıyas yok: kilidi bu koşu kurar
            if gecti:
                k["test_kilidi"] = {"zaman": L.simdi(), "dosyalar": once}
        else:
            if not k.get("test_kilidi"):
                hata("test kilidi koşu sırasında açıldı; yeşil kaydedilmedi.")
            hash_tutarli = L.kilitle_tutarli(k["test_kilidi"], once) and L.kilitle_tutarli(k["test_kilidi"], sonra)
            gecti = karar["yesil"] and hash_tutarli
        kayit = {"zaman": zaman, "sira": L.sonraki_sira(k), "asama": a.asama, "cikis_kodu": kod,
                 "hash_tutarli": hash_tutarli, "gecti": gecti, "sure_s": sure,
                 "kok": os.path.abspath(proje).replace("\\", "/"),  # onay kapısı yalnız güncel kökteki koşuyu sayar
                 "dusenler": karar["dusenler"], "yabanci_dusenler": karar["yabanci_dusenler"]}
        if not karar["ayristirildi"]:
            kayit["ayristirilamadi"] = True
        if karar["toplama_nedeni"]:
            kayit["toplama_hatasi"] = karar["toplama_nedeni"]
        kayit.update({"cikti_kuyrugu": L.maskele(cikti)[-L.TEST_KUYRUK_MAX:], "ajan": ajan_tipi, "agent_id": ajan_id})
        k["test_kosulari"].append(kayit)
        L.kart_yaz(sd, k)
    durum = "GEÇTİ" if gecti else "GEÇMEDİ"
    ek = ""
    if a.asama == "kirmizi" and not gecti:
        if kod == -1:
            ek = " (zaman aşımı; kilit yazılmadı)"
        else:
            ek = f" ({karar['kirmizi_neden'] or 'kırmızı aşamada test BAŞARISIZ olmalıydı'}; kilit yazılmadı)"
    elif a.asama == "kirmizi":
        ek = f" — {len(once)} test dosyası kilitlendi"
    elif not hash_tutarli:
        fark = L.kilit_farki(k["test_kilidi"].get("dosyalar"), sonra)
        ek = " — test dosyaları kilitten saptı: " + ", ".join(f"{ad} {', '.join(v)}" for ad, v in fark.items() if v)
    elif not gecti and karar["yesil_neden"]:
        ek = f" — {karar['yesil_neden']}"
    print(f"{a.gid} test {a.asama}: {durum} (çıkış {kod}, {sure} sn){ek}")
    if karar["ozet"]:
        print(karar["ozet"])
    if not gecti:
        sys.exit(4)


def _test_sahibi(sd: str, gid: str, kimlik: str, kosu_koku: str) -> str | None:
    """Düşen test kimliği hangi AÇIK kod kartının (durumu teslim/iptal değil, kendisi hariç) test_alani'nda
    (o kartın kendi test köküne göre)? Sahip yoksa None."""
    proje = L.proje_dizini()
    for o in L.kartlar(sd):
        if o.get("id") == gid or o.get("sinif") != "kod" or o.get("durum") in ("teslim", "iptal"):
            continue
        if not o.get("test_alani"):
            continue
        if L.test_alaninda_mi(kimlik, L.kart_test_koku(proje, o), o["test_alani"], kosu_koku):
            return o["id"]
    return None


def _kisa(kimlikler: list[str], n: int = 3) -> str:
    return ", ".join(kimlikler[:n]) + (f" (+{len(kimlikler) - n})" if len(kimlikler) > n else "")


def _test_karari(sd: str, gid: str, k: dict, proje: str, kod: int, cikti: str, once: dict) -> dict:
    """Test kapısı kararı düşen test kimliklerinden (çıkış kodu tek başına değil).

    KIRMIZI geçer ⇔ çıkış 1, toplama/kullanım hatası yok VE kartın test_alani'ndan en az bir test düştü.
    YEŞİL geçer ⇔ toplama/kullanım hatası yok VE test_alani'ndan düşen yok VE sahipsiz dış düşen yok VE
    (çıkış 0 YA DA dışarıda düşen her test başka bir açık kod kartının test_alani'nda). Çıktı pytest/unittest
    olarak ayrıştırılamazsa eski kural: kırmızı çıkış ∉ {0, -1}, yeşil çıkış 0."""
    a = L.test_ciktisi_ayristir(cikti, kod)
    karar = {"ayristirildi": a["ayristirildi"], "toplama_nedeni": a["toplama_nedeni"], "dusenler": [],
             "yabanci_dusenler": [], "kirmizi_neden": None, "yesil_neden": None, "ozet": ""}
    if not a["ayristirildi"]:
        karar.update(kirmizi=kod not in (0, -1), yesil=kod == 0,
                     ozet="uyarı: test çıktısı pytest/unittest olarak ayrıştırılamadı; karar çıkış koduna göre")
        return karar
    kendi_dosyalar = {L._kiyas(y) for y in once}
    for kimlik in a["dusenler"]:
        dosyalar = L.test_kimligi_dosyalari(kimlik)
        if (any(L._kiyas(d) in kendi_dosyalar for d in dosyalar)
                or L.test_alaninda_mi(kimlik, proje, k.get("test_alani") or [])):
            karar["dusenler"].append(kimlik)
        else:
            karar["yabanci_dusenler"].append({"test": kimlik, "dosya": dosyalar[0] if dosyalar else None,
                                              "kart": _test_sahibi(sd, gid, kimlik, proje)})
    sahipsiz = [y["test"] for y in karar["yabanci_dusenler"] if not y["kart"]]
    toplama = a["toplama_hatasi"]
    karar["kirmizi"] = kod == 1 and not toplama and bool(karar["dusenler"])
    # Gizli düşüş: pytest özetindeki failed + error sayısı ayrıştırılan düşüş SATIRI sayısından fazlaysa (-rN,
    # kısaltılmış/eksik özet) düşenlerin hepsi görülmedi; yeşil buna güvenip geçmez. Kıyas tekil kimlik sayısıyla
    # değil: bir test birden çok satırla düşebilir (N SUBFAILED, FAILED + teardown ERROR) ve özet her satırı sayar.
    ozet = a.get("ozet_dusen")
    satir = a.get("dusus_satiri", 0)
    gizli = ozet is not None and ozet > satir
    karar["yesil"] = (not toplama and not gizli and not karar["dusenler"] and not sahipsiz
                      and (kod == 0 or (kod == 1 and bool(karar["yabanci_dusenler"]))))
    yabanci = len(karar["yabanci_dusenler"])
    if toplama:
        karar["kirmizi_neden"] = karar["yesil_neden"] = a["toplama_nedeni"] + "; testler güvenilir biçimde koşmadı"
    else:
        if kod == 0:
            karar["kirmizi_neden"] = "kırmızı aşamada test BAŞARISIZ olmalıydı"
        elif not karar["dusenler"]:
            karar["kirmizi_neden"] = f"test_alani'ndan düşen test yok (dış düşen: {yabanci})"
        if karar["dusenler"]:
            karar["yesil_neden"] = "test_alani'ndan düşen var: " + _kisa(karar["dusenler"])
        elif sahipsiz:
            karar["yesil_neden"] = "sahipsiz dış düşen (hiçbir açık kod kartının test_alani'nda değil): " + _kisa(sahipsiz)
        elif gizli:
            karar["yesil_neden"] = (f"gizli düşüş: pytest özeti {ozet} failed/error diyor, ayrıştırılan düşüş "
                                    f"satırı {satir}")
        elif kod != 0 and not yabanci:
            karar["yesil_neden"] = f"çıkış {kod} ama düşen test kimliği bulunamadı"
    parcalar = [f"düşen (test_alani): {len(karar['dusenler'])}"]
    if karar["yabanci_dusenler"]:
        sahipli = [f"{y['test']} → {y['kart']}" for y in karar["yabanci_dusenler"] if y["kart"]]
        parcalar.append(f"dış düşen: {len(karar['yabanci_dusenler'])} (sahipli {len(sahipli)}, sahipsiz {len(sahipsiz)})")
        if sahipli:
            parcalar.append("sahipli: " + _kisa(sahipli))
    karar["ozet"] = "; ".join(parcalar)
    return karar


def cmd_kart_test_kilit_ac(a):
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    if ajan_tipi != "ana":
        hata(f"test kilidini yalnız ana ajan açar (sen: {ajan_tipi}).", 3)
    if not (a.neden or "").strip():
        hata("--neden boş olamaz.")
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if not k.get("test_kilidi"):
            hata("kartta açılacak test kilidi yok.")
        k["test_kilidi"] = None
        k["gecmis"].append({"zaman": L.simdi(), "olay": "test-kilit-ac", "ajan": ajan_tipi, "agent_id": ajan_id,
                            "not": L.maskele(a.neden)[:500]})
        L.kart_yaz(sd, k)
    print(f"{a.gid} test kilidi açıldı")


def cmd_kart_test_ayar(a):
    """Kod kartının test ayarları (yalnız ana ajan). Kilit yokken test_koku/test_komutu/test_alani serbestçe değişir;
    kilit varken yalnız test_koku değişir ve yalnız yeni kökte hesaplanan test özetleri kilitle birebir aynıysa."""
    sd = sd_gerekli()
    ajan_id, ajan_tipi = _kim(a)
    if ajan_tipi != "ana":
        hata(f"test ayarlarını yalnız ana ajan değiştirir (sen: {ajan_tipi}).", 3)
    if a.test_koku is None and a.test_komutu is None and not a.test_alani:
        hata("değiştirilecek alan yok: --test-koku, --test-komutu ya da --test-alani verin.")
    yeni = {}
    if a.test_koku is not None:
        if a.test_koku.strip():
            try:
                yeni["test_koku"] = L.test_koku_dogrula(a.test_koku)
            except ValueError as e:
                hata(str(e))
        else:
            yeni["test_koku"] = None  # boş değer: test_koku kaldırılır, kök yeniden proje olur
    if a.test_komutu is not None:
        if not a.test_komutu.strip():
            hata("--test-komutu boş olamaz.")
        yeni["test_komutu"] = a.test_komutu.strip()
    if a.test_alani:
        alan = [g.strip() for g in a.test_alani if g and g.strip()]
        if not alan:
            hata("--test-alani boş olamaz.")
        yeni["test_alani"] = alan
    with L.kilit(L.kart_yolu(sd, a.gid)):
        k = _kart_al(sd, a.gid)
        if k.get("sinif") != "kod":
            hata(f"test-ayar yalnız kod kartında çalışır (sinif: {k.get('sinif')}).")
        if L.kart_durumu_hesapla(k) in ("teslim", "iptal"):
            hata(f"kapalı kartın test ayarı değişmez ({k.get('durum')}).")
        degisen = {ad: {"eski": k.get(ad), "yeni": v} for ad, v in yeni.items() if k.get(ad) != v}
        eklenen = []
        if yeni.get("test_alani"):
            kok = yeni["test_koku"] if "test_koku" in yeni else k.get("test_koku")
            kok = str(kok).replace("\\", "/").rstrip("/") if kok else ""
            ya = list(k.get("yazma_alani") or [])
            var = {os.path.normcase(x).replace("\\", "/") for x in ya}
            for desen in yeni["test_alani"]:
                girdi = kok + "/" + desen if kok else desen
                n = os.path.normcase(girdi).replace("\\", "/")
                if n not in var:
                    var.add(n)
                    ya.append(girdi)
                    eklenen.append(girdi)
            if eklenen:
                k["yazma_alani"] = ya
        if not degisen and not eklenen:
            print(f"{a.gid} test ayarı: değişiklik yok")
            return
        if k.get("test_kilidi"):
            yasak = [ad for ad in degisen if ad != "test_koku"]
            if yasak:
                hata(f"test dosyaları kilitli: yalnız test_koku değişebilir ({', '.join(yasak)} değişmez; önce ana ajan "
                     f"`orkestra kart test-kilit-ac {a.gid}` ile kilidi açar).")
            if "test_koku" in degisen:  # yalnız yazma_alani genişlemesinde kök doğrulaması gerekmez
                aday = dict(k)
                aday["test_koku"] = yeni["test_koku"]
                try:
                    kok = L.kart_proje_koku(L.proje_dizini(), aday)
                except ValueError as e:
                    hata(str(e))
                mevcut = L.test_dosyasi_ozetleri(kok, k.get("test_alani") or [])
                if not L.kilitle_tutarli(k["test_kilidi"], mevcut):
                    fark = L.kilit_farki(k["test_kilidi"].get("dosyalar"), mevcut)
                    hata(f"yeni test kökünde ({kok}) test dosyaları kilitle aynı değil (" + "; ".join(
                        f"{ad}: {', '.join(v)}" for ad, v in fark.items() if v) + "); test_koku değişmedi.")
        for ad, d in degisen.items():
            if d["yeni"] is None:
                k.pop(ad, None)
            else:
                k[ad] = d["yeni"]
        k["gecmis"].append({"zaman": L.simdi(), "olay": "test-ayar", "ajan": ajan_tipi, "agent_id": ajan_id,
                            "degisen": degisen})
        L.kart_yaz(sd, k)
    print(f"{a.gid} test ayarı: " + ", ".join(f"{ad} → {d['yeni'] if d['yeni'] is not None else '(proje)'}"
                                              for ad, d in degisen.items()))


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
        beklemeden = False
        if durum == "beklemede":
            # Beklemede'ye alınmadan önce onay almış kart teslim edilebilir (sığ kopyada durum çekilir).
            if L.kart_durumu_hesapla({**k, "durum": None}) == "onaylandi":
                beklemeden = True
                durum = "onaylandi"
        if durum != "onaylandi":
            hata(f"teslim için denetçi onayı gerekli (durum: {durum}).", 3)
        if beklemeden:
            k["gecmis"].append({"zaman": L.simdi(), "olay": "beklemeden-teslim"})
        if (k.get("calisma_agaci") or {}).get("yol"):
            ok, mesaj = _birlestir(sd, k)
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


def _birlestir(sd, k) -> tuple[bool, str]:
    """Kartın çalışma ağacını birleştirir ve kartı günceller (yazmaz). Çatışmada ya da kilit kapısı ihlalinde kart
    beklemede, dosyalar not edilir; worktree korunur. Kilit kapısı bütün kartların test kilitlerine bakar."""
    s = L.kart_agaci_birlestir(k, proje=L.proje_dizini(), ks=L.kartlar(sd))
    if s["sonuc"] == "tamam":
        ca = k.pop("calisma_agaci")
        ca.update(birlesme=L.simdi(), commit=s.get("commit"))
        k["calisma_agaci_birlesik"] = ca
        if "yazma_alani_ilk" in k:
            k["yazma_alani"] = k.pop("yazma_alani_ilk")
        k["girdi"] = _girdi_agacsiz(k.get("girdi"))
        k.pop("birlestirme_catismasi", None)
        k.pop("birlestirme_kilidi", None)
        k["gecmis"].append({"zaman": L.simdi(), "olay": "birlestirildi", "commit": s.get("commit"), "not": s["mesaj"][:500]})
        return True, s["mesaj"]
    if s["sonuc"] in ("catisma", "kilit"):
        k["durum"] = "beklemede"
        k["beklemede_sira"] = L.sonraki_sira(k)
        if s["sonuc"] == "catisma":
            k["birlestirme_catismasi"] = s["dosyalar"]
            not_ = "birleştirme çatışması (otomatik çözülmedi): " + ", ".join(s["dosyalar"])
            ek = " — kart beklemede; çatışmayı elle çöz, sonra yeniden birleştir"
        else:
            k["birlestirme_kilidi"] = s["dosyalar"]
            not_ = "birleştirme kilit kapısı: " + s["mesaj"]
            ek = " — kart beklemede"
        k["gecmis"].append({"zaman": L.simdi(), "olay": "beklemede", "ajan": "orkestra", "not": not_[:500]})
        return False, s["mesaj"] + ek
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
        ok, mesaj = _birlestir(sd, k)
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
        metin += "\n" + _md_tablo("Gün", ["gun"], _pivot([dict(r, gun=r.get("zaman", "")[:10]) for r in kayitlar], ["gun"]))
        metin += "\n" + _baglam_md(kayitlar)
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
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
         "cache_creation_input_tokens": a.onb_yazma}
    L.jsonl_ekle(os.path.join(sd, "maliyet.jsonl"), {
        "zaman": L.simdi(), "oturum": a.oturum, "gorev": gorev, "surec": surec, "ajan": ajan, "agent_id": a.agent_id,
        "model": a.model, "giris": a.giris, "cikis": a.cikis, "onbellek_okuma": a.onb_okuma, "onbellek_yazma": a.onb_yazma,
        "maliyet_usd": L.kullanim_maliyeti(a.model, u), "sure_ms": a.sure_ms, "kaynak": "tur",
        "is": _tur_isi(sd, gorev, a.oturum)})


def _tur_isi(sd, gorev, oturum):
    """hook.py `_kart_isi(...) or _oturum_isi(...)` ile aynı mantık; hata durumunda None (kayıt düşmez)."""
    try:
        if gorev and gorev != "-":
            k = L.kart_oku(sd, gorev)
            v = k.get("is") if isinstance(k, dict) else None
            if v:
                return str(v)
    except Exception:
        pass
    try:
        with open(os.path.join(sd, "oturumlar", f"{oturum}.json"), encoding="utf-8") as f:
            d = json.load(f)
        v = d.get("is") if isinstance(d, dict) else None
        return str(v) if v else None
    except Exception:
        return None


def cmd_maliyet_ozet(a):
    sd = sd_gerekli()
    kayitlar = L.maliyet_kayitlari(sd)
    bugun = datetime.date.today().isoformat()
    oid = oturum_id()
    o = {"bugun_usd": round(sum(r.get("maliyet_usd", 0) for r in kayitlar if r.get("zaman", "").startswith(bugun)), 4),
         "oturum_usd": round(sum(r.get("maliyet_usd", 0) for r in kayitlar if r.get("oturum") == oid), 4),
         "toplam_usd": round(sum(r.get("maliyet_usd", 0) for r in kayitlar), 4), "kosu": len(kayitlar)}
    print(json.dumps(o) if a.json else f"bugün ≈${o['bugun_usd']:.2f} · bu oturum ≈${o['oturum_usd']:.2f} · toplam ≈${o['toplam_usd']:.2f} ({o['kosu']} koşu)")


# ---------------------------------------------------------------- perspektif

def cmd_perspektif(a):
    if getattr(a, "komut", None) == "ruya":  # eski ad: takma ad olarak çalışır
        print("uyarı: `orkestra ruya` eski addır; `orkestra perspektif` kullan.", file=sys.stderr)
    sd = sd_gerekli()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import perspektif
    if a.islem == "durum":
        print(json.dumps(perspektif.durum(sd), ensure_ascii=False, indent=2))
    elif a.islem == "basla":
        print(perspektif.baslat(sd, L.proje_dizini(), zorla=True))
    elif a.islem == "bitti":
        perspektif.bitti_isaretle(sd)
        print("perspektif raporu okundu olarak işaretlendi")
    elif a.islem == "basladi":
        perspektif.basladi_isaretle(sd)
        print("perspektif başladı")
    elif a.islem == "kaydet":
        if not a.yol or not os.path.exists(a.yol):
            hata("rapor yolu gerekli ve var olmalı: orkestra perspektif kaydet <yol>")
        perspektif.kaydet(sd, a.yol)
        print(f"perspektif raporu kaydedildi: {a.yol}")
    elif a.islem == "hafiza":
        print(perspektif.hafiza_dizini(L.proje_dizini()))


# ---------------------------------------------------------------- onay merkezi

def _onay_oturumu(a) -> str:
    o = getattr(a, "oturum", None) or os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID")
    return o or "cli"


def _onay_calistir(f, *args, **kw):
    import onay
    try:
        return f(onay, *args, **kw)
    except ValueError as e:
        hata(str(e))


def _onay_satir(k: dict) -> str:
    return f"{k['id']}  {k['durum']:<11} {k['tur']:<10} {k['baslik']}"


def cmd_onay(a):
    sd = sd_gerekli()
    import onay
    i = a.alt
    if i == "liste":
        onay.esitle(sd)
        kayitlar = onay.liste(sd, durum=a.durum, tur=a.tur)
        if a.json:
            print(json.dumps(kayitlar, ensure_ascii=False, indent=2))
        else:
            for k in kayitlar:
                print(_onay_satir(k))
            if not kayitlar:
                print("kayıt yok")
    elif i == "goster":
        k = onay.goster(sd, a.id)
        if not k:
            hata(f"onay kaydı bulunamadı: {a.id}")
        print(json.dumps(k, ensure_ascii=False, indent=2))
    elif i == "iste":
        k = _onay_calistir(lambda m: m.iste(sd, a.baslik, a.metin, secenekler=a.secenek, oturum=a.oturum))
        print(k["id"])
    elif i == "karar":
        k = _onay_calistir(lambda m: m.karar_ver(sd, a.id, "onay" if a.onay else "ret", secim=a.secim,
                                                 not_=a.not_, kim="cli"))
        print(f"{k['id']} → {k['durum']}")
    elif i == "al":
        k = _onay_calistir(lambda m: m.al(sd, a.id, _onay_oturumu(a)))
        print(f"{k['id']} → {k['durum']}")
    elif i == "uygulandi":
        k = _onay_calistir(lambda m: m.uygulandi(sd, a.id, a.ozet, oturum=_onay_oturumu(a)))
        print(f"{k['id']} → {k['durum']}")
    elif i == "iptal":
        k = _onay_calistir(lambda m: m.iptal(sd, a.id, a.not_))
        print(f"{k['id']} → {k['durum']}")
    elif i == "esitle":
        onay.esitle(sd)
        s = onay.sayac(sd)
        print(f"eşitlendi: {s['bekliyor']} bekliyor, {s['uygulanacak']} uygulanacak")


def cmd_kural(a):
    sd = sd_gerekli()
    import onay
    i = a.alt
    kaynak = _onay_oturumu(a) if os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID") else "cli"
    if i == "liste":
        kayitlar = onay.kurallar(sd)
        if a.json:
            print(json.dumps(kayitlar, ensure_ascii=False, indent=2))
        else:
            for r in kayitlar:
                print(f"{r['id']}  {r['durum']:<11} {r['metin']}")
            if not kayitlar:
                print("kural yok")
    elif i == "oner":
        r = _onay_calistir(lambda m: m.kural_oner(sd, a.metin, a.neden, kaynak))
        k = onay._anahtarli(sd, f"kural:{r['id']}")
        print(f"{r['id']} önerildi" + (f" (onay {k['id']})" if k else ""))
    elif i == "ekle":
        r = _onay_calistir(lambda m: m.kural_ekle(sd, a.metin, a.neden, kaynak="cli"))
        print(f"{r['id']} etkin")
    elif i == "duzenle":
        r = _onay_calistir(lambda m: m.kural_duzenle(sd, a.id, a.metin, a.neden))
        print(f"{r['id']} güncellendi")
    elif i == "kaldir":
        r = _onay_calistir(lambda m: m.kural_kaldir(sd, a.id, a.not_))
        print(f"{r['id']} → {r['durum']}")


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

def cmd_kpi(a):
    """Hazır 8 KPI, salt okuma (kpi.py)."""
    sd = sd_gerekli()
    import kpi
    s = kpi.olcum(sd, a.gun)
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


# ---------------------------------------------------------------- is (kalıcı iş katmanı)

def _ik():
    import is_kaydi
    return is_kaydi


def _oturum_dosyasi(sd, kenar=False):
    ad = ("is_" if kenar else "") + oturum_id() + ".json"
    return os.path.join(sd, "oturumlar", ad)


def _json_oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _oturum_isi(sd):
    """Bu oturumun bağlı işi: önce oturum dosyası, yoksa Stop hook'unun ezmediği yan dosya."""
    return _json_oku(_oturum_dosyasi(sd)).get("is") or _json_oku(_oturum_dosyasi(sd, True)).get("is")


def _oturumu_bagla(sd, is_id):
    """Oturum dosyasındaki mevcut anahtarlar korunur (oku-birleştir-yaz, kilitli); is.json oturumlar[]'a eklenir."""
    an = L.simdi()
    yol = _oturum_dosyasi(sd)  # eski is_<oturum>.json yan dosyası yalnız okunur, yeniden yazılmaz
    with L.kilit(yol):
        v = _json_oku(yol)
        v["is"] = is_id
        v["is_baglanma"] = an
        v.setdefault("is_gecmis", []).append({"is": is_id, "zaman": an})
        L.atomik_yaz(yol, json.dumps(v, ensure_ascii=False, indent=2) + "\n")
    _ik().is_oturum_bagla(sd, is_id, oturum_id())


def _is_gerekli(sd, is_id):
    try:
        kayit = _ik().is_al(sd, is_id)
    except ValueError as e:
        hata(str(e))
    if not kayit:
        hata(f"iş yok: {is_id}")
    return kayit


def _todo_satiri(klasor):
    t = _ik().todo_ozet(klasor)
    return t, f"todo {t['biten']}/{t['toplam']}"


def cmd_is_ac(a):
    sd = sd_gerekli()
    kayit = _ik().is_ac(sd, a.baslik, a.klasor, a.etiket)
    _oturumu_bagla(sd, kayit["id"])
    print(kayit["id"])


def cmd_is_devam(a):
    sd = sd_gerekli()
    kayit = _is_gerekli(sd, a.is_id)
    _oturumu_bagla(sd, a.is_id)
    klasor = kayit["klasor"]
    t, satir = _todo_satiri(klasor)
    print(f"{a.is_id} — {kayit['baslik']} [{kayit['durum']}]")
    print(f"plan: {os.path.join(klasor, 'plan.md')}")
    print(satir)
    for m in t["acik_maddeler"]:
        print(f"  [ ] {m}")
    son = ""
    yol = os.path.join(klasor, "oturumlar.md")
    if os.path.exists(yol):
        with open(yol, encoding="utf-8", errors="replace") as f:
            dolu = [s.rstrip() for s in f if s.strip()]
        son = dolu[-1] if len(dolu) > 1 else ""  # ilk satır başlık
    print(f"oturumlar.md son satır: {son or '(henüz yok)'}")


def cmd_is_liste(a):
    sd = sd_gerekli()
    ik = _ik()
    satirlar = []
    for g in ik.is_liste(sd, None if a.durum == "hepsi" else a.durum):
        kayit = ik.is_al(sd, g["id"]) or {}
        _, todo = _todo_satiri(g["klasor"])
        satirlar.append([g["id"], g.get("durum", "-"), g.get("baslik", ""), todo.replace("todo ", ""),
                         str(len(kayit.get("kartlar", []))), str(len(kayit.get("oturumlar", []))), g["klasor"]])
    if not satirlar:
        print("iş yok")
        return
    print("\t".join(["id", "durum", "baslik", "todo", "kart", "oturum", "klasor"]))
    for s in satirlar:
        print("\t".join(s))


def cmd_is_kapat(a):
    sd = sd_gerekli()
    _is_gerekli(sd, a.is_id)
    _ik().is_durum(sd, a.is_id, "kapandi")
    print(f"{a.is_id} → kapandi")


def cmd_is_todo(a):
    sd = sd_gerekli()
    kayit = _is_gerekli(sd, a.is_id)
    ekle, bitti, not_ = getattr(a, "ekle", None), getattr(a, "bitti", None), getattr(a, "not_", None)
    if ekle is not None and bitti is not None:
        hata("--ekle ve --bitti birlikte verilemez.")
    if not_ is not None and bitti is None:
        hata("--not yalnız --bitti ile kullanılır.")
    if ekle is not None or bitti is not None:
        if ekle is not None and kayit.get("durum") == "kapandi":
            hata(f"{a.is_id} kapalı; --ekle yapılamaz.")
        try:
            if ekle is not None:
                _ik().todo_ekle(kayit["klasor"], ekle)
            else:
                _ik().todo_bitir(kayit["klasor"], bitti, not_)
        except (ValueError, OSError, TimeoutError) as e:
            hata(str(e))
    t, satir = _todo_satiri(kayit["klasor"])
    print(f"{a.is_id} {satir}")
    for m in t["acik_maddeler"]:
        print(f"  [ ] {m}")


def cmd_is_serit(a):
    sd = sd_gerekli()
    _is_gerekli(sd, a.is_id)
    s = _ik().is_serit(sd, a.is_id)
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return
    i, p = s["is"], s["ilerleme"]
    print(f"{i['id']} — {i['baslik']}  [{p['biten']}/{p['toplam']}]")
    for kova, baslik in (("yapildi", "✔ Yapıldı"), ("simdi", "◐ Şimdi"),
                         ("sirada", "○ Sırada"), ("planda_kart_yok", "◌ Planda, kart yok")):
        if not s[kova]:
            continue
        print(baslik)
        for o in s[kova]:
            if o["tur"] == "kart":
                adim, son = o["adim"], f"  ({o['kart']})"
                if o["bekledigi"]:
                    son += " ← " + ", ".join(o["bekledigi"])
            else:
                adim, son = (o["adimlar"][0] if o["adimlar"] else None), ""
            metin = o["metin"]
            if kova != "yapildi" and adim and metin.startswith(adim) and (len(metin) == len(adim) or metin[len(adim)] in " :"):
                metin = metin[len(adim):].lstrip(" :")
            print("  " + (f"{adim}  " if adim else "") + metin + son)
    if s["iptal"]:
        print(f"⊘ İptal ({len(s['iptal'])})")


def cmd_is_aktif(a):
    sd = sd_gerekli()
    i = _oturum_isi(sd)
    if not i:
        print("bağlı iş yok")
        return
    kayit = _ik().is_al(sd, i)
    print(f"{i} — {kayit['baslik']} [{kayit['durum']}]" if kayit else i)


def _alan_listesi(v):
    if isinstance(v, str):
        return [v]
    return [x for x in (v or []) if isinstance(x, str)]


def _gorev_klasoru(sd, yazma, test):
    """Yazma + test alanı yollarından çözülen bağlam GÖREV düzeyindeyse görev klasörünün mutlak yolu; yoksa None."""
    import baglam as B
    esleme = B.esleme_oku(sd)
    if not esleme:
        return None
    proje = L.proje_dizini()
    b = B.coz(esleme, proje, _alan_listesi(yazma), _alan_listesi(test))
    parcalar = [p for p in b.split("/") if p]
    if len(parcalar) < 2 or not B._desen_uyar(esleme.get("gorev_deseni"), parcalar[-1]):
        return None
    return os.path.join(proje, *parcalar)


def _gorev_isi(sd, klasor, olustur):
    """Görev klasörünün açık işi; yoksa (olustur) yeni iş açar. Klasörde kapalı iş/yetim is.json varsa None (ezilmez)."""
    ik = _ik()
    i = ik.is_klasorle_bul(sd, klasor)
    if i:
        return i
    if not olustur or ik.is_klasorle_bul(sd, klasor, True) or os.path.exists(os.path.join(klasor, "is.json")):
        return None
    return ik.is_ac(sd, os.path.basename(klasor), klasor)["id"]


def _acik_is_dogrula(sd, acik_is):
    """--is / plan 'is' verilmişse iş var olmalı (yoksa hata). Kapalı olması hata değildir: kart açık bir işe bağlanır."""
    if acik_is:
        _is_gerekli(sd, acik_is)


def _goreli(yol):
    """Proje köküne göre göreli gösterim (dışarıdaysa mutlak); yalnız ileti için."""
    try:
        r = os.path.relpath(yol, L.proje_dizini())
    except ValueError:
        r = ".."
    return (yol if r.startswith("..") else r).replace("\\", "/")


def _is_kaydi_guvenli(sd, i):
    try:
        return _ik().is_al(sd, i) if i else None
    except Exception:
        return None


def _bilinen_is_klasorleri(sd, derinlik=3):
    """is.json bulunan klasörler: baglam.json projeleri (Proje/Süreç/Görev, en çok `derinlik` düzey; gizli ve haric
    dizinler atlanır) ve <durum dizini>/isler. Merkez yok/bozukken yeniden kurulum ve sayaç için kullanılır."""
    import baglam
    proje = L.proje_dizini()
    esleme = baglam.esleme_oku(sd) or {}
    haric = {str(h).casefold() for h in esleme.get("haric") or []}
    kokler = [os.path.join(sd, "isler")]
    if proje:
        kokler += [os.path.normpath(os.path.join(proje, str(p))) for p in esleme.get("projeler") or [] if str(p).strip()]
    bulunan, gorulen = [], set()
    for kok in kokler:
        if not os.path.isdir(kok):
            continue
        for yol, dizinler, dosyalar in os.walk(kok):
            goreli = os.path.relpath(yol, kok)
            if (0 if goreli == "." else goreli.count(os.sep) + 1) >= derinlik:
                dizinler[:] = []
            else:
                dizinler[:] = [d for d in dizinler if not d.startswith(".") and d.casefold() not in haric]
            anahtar = os.path.normcase(os.path.abspath(yol))
            if "is.json" in dosyalar and anahtar not in gorulen:
                gorulen.add(anahtar)
                bulunan.append(os.path.abspath(yol))
    return bulunan


def _merkez_saglamla(sd):
    """K2: isler.json bozuksa yedeğe alınır; yoksa/yedeklendiyse bilinen is.json'lardan yeniden kurulur. Hata vermez."""
    ik = _ik()
    try:
        if os.path.exists(os.path.join(sd, "isler.json")) and not ik.merkez_bozuk_mu(sd):
            return
        r = ik.merkez_kurtar(sd, _bilinen_is_klasorleri(sd))
    except Exception as e:  # kurtarma kart oluşturmayı asla durdurmaz
        print(f"orkestra: uyarı: isler.json kurtarılamadı ({e})", file=sys.stderr)
        return
    if r.get("yedek"):
        print(f"orkestra: uyarı: isler.json bozuktu; {_goreli(r['yedek'])} olarak yedeklendi, "
              f"{len(r.get('farklar') or [])} kayıtla yeniden kuruldu", file=sys.stderr)


def _yeni_is(sd, baslik, klasor, uygula):
    """Klasörde iş açar (uygula değilse yalnız planlar). Klasör açılamazsa <durum dizini>/isler altında sıradaki NNN denenir."""
    if not uygula:
        return {"is": None, "klasor": klasor, "yeni": True}
    ik = _ik()
    try:
        return {"is": ik.is_ac(sd, baslik, klasor)["id"], "klasor": klasor, "yeni": True}
    except OSError as e:
        kok = os.path.join(sd, "isler")
        yedek = os.path.join(kok, ik.sonraki_klasor_adi(kok, baslik))
        print(f"orkestra: uyarı: {_goreli(klasor)} açılamadı ({e}); {_goreli(yedek)} kullanılıyor", file=sys.stderr)
        return {"is": ik.is_ac(sd, baslik, yedek)["id"], "klasor": yedek, "yeni": True}


def _is_coz(sd, baslik, yazma, onbellek, uygula=True):
    """K1 (c)/(d): yazma alanının ilk girdisi baglam.json ile Proje[/Süreç]/Görev klasörüne çözülür.

    (c) görev klasöründe açık iş varsa o; is.json yoksa orada yeni iş.
    (d) görev klasörü yoksa (ya da işi kapalıysa) çözülen kökte — çözülmezse eşlemedeki ilk projede,
        eşleme de yoksa <durum dizini>/isler altında — sıradaki NNN-YYYYMMDD-<slug> klasöründe yeni iş.
    onbellek aynı komutta aynı klasöre çözülen kartları tek işe toplar. Hata vermez.
    Dönüş: {"is": id|None (kuru koşuda yeni iş), "klasor", "yeni", "kaynak", "notlar"}.
    """
    import baglam
    ik = _ik()
    proje = L.proje_dizini()
    esleme = baglam.esleme_oku(sd)
    notlar = []
    c = baglam.klasor_coz(esleme, proje, yazma[0]) if yazma else None
    if c:
        kok, gorev = c
        kaynak = "yazma_alani"
    else:
        projeler = [str(p) for p in ((esleme or {}).get("projeler") or []) if str(p).strip()]
        # eşleme yoksa iş klasörü proje ağacını kirletmesin: durum dizininde (çoğunlukla git dışı) tutulur
        kok = os.path.normpath(os.path.join(proje, projeler[0])) if projeler else os.path.join(sd, "isler")
        gorev = None
        kaynak = "ilk proje" if projeler else "eşleme yok"

    def onbellekten(anahtar):
        r = onbellek.get(anahtar)
        if r is None:
            return None
        r = dict(r, kaynak=kaynak, notlar=notlar)
        if uygula:
            r["yeni"] = False
        return r

    if gorev:
        anahtar = "g:" + os.path.normcase(os.path.abspath(gorev))
        r = onbellekten(anahtar)
        if r:
            return r
        kayit = ik.is_klasorden(sd, gorev)
        if kayit is None:  # is.json geçerli ama merkezde kayıtlı değilse merkeze kaydedilir (kimlik çakışmıyorsa)
            kayit = ik.yetim_kaydet(sd, gorev, uygula)
            if kayit:
                notlar.append(f"{_goreli(gorev)}/is.json merkeze " + ("kaydedildi" if uygula else "kaydedilecek"))
        if kayit and kayit.get("durum") != "kapandi":
            r = {"is": kayit["id"], "klasor": gorev, "yeni": False}
        elif not os.path.exists(os.path.join(gorev, "is.json")):
            r = _yeni_is(sd, os.path.basename(gorev), gorev, uygula)
        else:
            notlar.append(f"{_goreli(gorev)} işi kapalı" if kayit
                          else f"{_goreli(gorev)}/is.json geçersiz ya da kimliği merkezde başka klasöre ait")
        if r:
            onbellek[anahtar] = r
            return dict(r, kaynak=kaynak, notlar=notlar)
    anahtar = "k:" + os.path.normcase(os.path.abspath(kok))
    r = onbellekten(anahtar)
    if r:
        return r
    r = _yeni_is(sd, baslik or "is", os.path.join(kok, ik.sonraki_klasor_adi(kok, baslik)), uygula)
    onbellek[anahtar] = r
    return dict(r, kaynak=kaynak, notlar=notlar)


def _bag_aciklamasi(r):
    m = f"{r['kaynak']}: {_goreli(r['klasor'])}" + (", yeni iş" if r.get("yeni") else "")
    return m + "".join(f"; {n}" for n in r.get("notlar") or [])


def _bag_satiri(gid, is_id, aciklama):
    """K5: bağın hangi yoldan kurulduğu — kart başına tek satır, stderr (stdout biçimi değişmez)."""
    print(f"orkestra: {gid} → {is_id} ({aciklama})", file=sys.stderr)


def _kart_is_bag_kur(sd, gid, baslik, yazma, acik_is=None, onbellek=None):
    """Kartın işi — asla boş dönmez, bağ yüzünden ret vermez (var olmayan açık kimlik dışında).

    (a) --is / plan 'is' açıksa o; (b) oturumun açık işi; (c)/(d) `_is_coz`. Otomatik bulunan ya da açılan iş
    oturuma bağlanır (bu noktada oturumun açık işi yoktur)."""
    onbellek = {} if onbellek is None else onbellek
    notlar = []
    if acik_is:
        if _is_gerekli(sd, acik_is).get("durum") != "kapandi":
            _bag_satiri(gid, acik_is, "--is")
            return acik_is
        notlar.append(f"{acik_is} kapalı")
    i = _oturum_isi(sd)
    kayit = _is_kaydi_guvenli(sd, i)
    if kayit and kayit.get("durum") != "kapandi":
        _bag_satiri(gid, i, "oturum işi" + "".join(f"; {n}" for n in notlar))
        return i
    if kayit:
        notlar.append(f"oturum işi {i} kapalı")
    r = _is_coz(sd, baslik, yazma, onbellek, True)
    r["notlar"] = notlar + r["notlar"]
    _oturumu_bagla(sd, r["is"])
    _bag_satiri(gid, r["is"], _bag_aciklamasi(r))
    return r["is"]


def _kart_no(gid):
    try:
        return int(str(gid).split("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def _sahipsiz_kartlar(sd, uygula):
    """K7: 'is' alanı boş kartlar; kuru koşu yalnız önerir (dosya yazmaz, oturum bağlamaz), --uygula bağlar."""
    sahipsiz = sorted((k for k in L.kartlar(sd) if not k.get("is")), key=lambda k: _kart_no(k["id"]))
    if not sahipsiz:
        print("sahipsiz kart yok")
        return
    if uygula:
        _merkez_saglamla(sd)
    onbellek = {}
    baglanan = 0
    for k in sahipsiz:
        r = _is_coz(sd, k.get("baslik") or "", list(k.get("yazma_alani") or []), onbellek, uygula)
        if uygula:
            with L.kilit(L.kart_yolu(sd, k["id"])):
                guncel = L.kart_oku(sd, k["id"])
                if guncel and not guncel.get("is"):
                    guncel["is"] = r["is"]
                    L.kart_yaz(sd, guncel)
                    _ik().is_kart_ekle(sd, r["is"], k["id"])
                    baglanan += 1
        print(f"{k['id']} → {r['is'] or 'yeni iş'} ({_bag_aciklamasi(r)})")
    if uygula:
        print(f"{baglanan} sahipsiz kart işe bağlandı")
    else:
        print(f"{len(sahipsiz)} sahipsiz kart; bağlamak için --uygula")


def cmd_is_bagla(a):
    sd = sd_gerekli()
    if not a.geriye:
        hata("şimdilik yalnız `orkestra is bagla --geriye [--uygula]` var.")
    ik = _ik()
    satirlar = []
    acik_isler = None
    for k in L.kartlar(sd):
        gid = k["id"]
        yeni_is, neden, yeni_klasor = None, None, None
        if not k.get("is"):
            klasor = _gorev_klasoru(sd, k.get("yazma_alani"), k.get("test_alani"))
            if klasor:
                i = ik.is_klasorle_bul(sd, klasor)
                if i:
                    yeni_is, neden = i, "baglam"
                elif not ik.is_klasorle_bul(sd, klasor, True) and not os.path.exists(os.path.join(klasor, "is.json")):
                    yeni_klasor = klasor
                    neden = "baglam"
            if not yeni_is and not yeni_klasor and k.get("oturum"):
                if acik_isler is None:
                    acik_isler = [(g["id"], ik.is_al(sd, g["id"]) or {}) for g in ik.is_liste(sd) if g.get("durum") != "kapandi"]
                for iid, kayit in acik_isler:
                    if any(o.get("oturum") == k["oturum"] for o in kayit.get("oturumlar", [])):
                        yeni_is, neden = iid, "oturum"
                        break
        adim = ik.adim_coz(k.get("baslik"))
        adim_eksik = bool(adim) and not k.get("adim")
        if not (yeni_is or yeni_klasor or adim_eksik):
            continue
        if a.uygula:
            if yeni_klasor:
                yeni_is = _gorev_isi(sd, yeni_klasor, True)
            with L.kilit(L.kart_yolu(sd, gid)):
                guncel = L.kart_oku(sd, gid) or k
                degisti = False
                if yeni_is and not guncel.get("is"):
                    guncel["is"] = yeni_is
                    degisti = True
                else:
                    yeni_is = None
                if adim_eksik and not guncel.get("adim"):
                    guncel["adim"] = adim
                    degisti = True
                if degisti:
                    L.kart_yaz(sd, guncel)
            if yeni_is:
                ik.is_kart_ekle(sd, yeni_is, gid)
        if yeni_is or yeni_klasor:
            hedef = yeni_is or f"(yeni iş: {os.path.basename(yeni_klasor)})"
            satirlar.append(f"{gid} → {hedef} ({neden})")
        if adim_eksik:
            satirlar.append(f"{gid} adim={adim}")
    if not satirlar:
        print("fark yok")
        return
    for m in satirlar:
        print(m)
    if not a.uygula:
        print(f"{len(satirlar)} fark; uygulamak için --uygula")


def cmd_is_onar(a):
    sd = sd_gerekli()
    if a.kartlar:
        _sahipsiz_kartlar(sd, a.uygula)
        return
    r = _ik().onar(sd, a.klasor, a.uygula)
    for m in r["farklar"]:
        print(m)
    for m in r["uyarilar"]:
        print(f"uyarı: {m}", file=sys.stderr)
    if not r["farklar"]:
        print("fark yok")
    elif a.uygula:
        print(f"isler.json onarıldı ({len(r['farklar'])} fark)")
    else:
        print(f"{len(r['farklar'])} fark; uygulamak için --uygula")


def _kart_is_bagla(sd, k):
    if k.get("is"):
        _ik().is_kart_ekle(sd, k["is"], k["id"])


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
    y.add_argument("--test-komutu", dest="test_komutu", help="kod kartında zorunlu: proje kökünde kabukla koşulan test komutu")
    y.add_argument("--test-alani", dest="test_alani", action="append", default=[],
                   help="kod kartında zorunlu (tekrarlanabilir): test dosyası glob'u, test köküne göre")
    y.add_argument("--test-koku", dest="test_koku",
                   help="kod kartında isteğe bağlı: test kökü (var olan mutlak dizin; yoksa proje kökü)")
    y.add_argument("--risk", help="dusuk|orta|yuksek (isteğe bağlı; ölçüm kaydı)")
    y.add_argument("--butce-usd", dest="butce_usd", help="isteğe bağlı bütçe (USD); yalnız kayıt")
    y.add_argument("--butce-token", dest="butce_token", help="isteğe bağlı bütçe (token); yalnız kayıt")
    y.add_argument("--is", dest="is_id", help="kartı bu işe bağla (I-NNN); verilmezse oturumun bağlı işi")
    y.set_defaults(f=cmd_kart_yeni)
    ty = kart.add_parser("test-ayar", help="kod kartının test ayarları (yalnız ana ajan; kilitliyken yalnız test_koku)")
    ty.add_argument("gid")
    ty.add_argument("--test-koku", dest="test_koku", help="mutlak dizin; boş değer kaldırır (kök yeniden proje)")
    ty.add_argument("--test-komutu", dest="test_komutu")
    ty.add_argument("--test-alani", dest="test_alani", action="append", default=[])
    ty.set_defaults(f=cmd_kart_test_ayar)
    t = kart.add_parser("toplu")
    t.add_argument("json_yol", nargs="?")
    t.add_argument("--json-dosya")
    t.set_defaults(f=cmd_kart_toplu)
    tk = kart.add_parser("test-kos")
    tk.add_argument("gid")
    tk.add_argument("--asama", required=True, choices=["kirmizi", "yesil"])
    tk.add_argument("--zaman-asimi", dest="zaman_asimi", type=float, default=600)
    tk.set_defaults(f=cmd_kart_test_kos)
    ka = kart.add_parser("test-kilit-ac")
    ka.add_argument("gid")
    ka.add_argument("--neden", required=True)
    ka.set_defaults(f=cmd_kart_test_kilit_ac)
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
    du.add_argument("--surec", help="is-bitti: süreç adı (verilmezse ajan tipinden: isci -> is)")
    du.add_argument("--cikti", action="append", default=[])
    du.add_argument("--not", dest="not_")
    du.set_defaults(f=cmd_kart_durum)
    de = kart.add_parser("denetim", formatter_class=argparse.RawTextHelpFormatter)
    de.add_argument("gid")
    de.add_argument("--karar", required=True, choices=["onay", "ret"])
    de.add_argument("--gerekce", required=True)
    de.add_argument("--talimat")
    de.add_argument("--neden", metavar="KOD",
                    help=_neden_yardim())
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
    r.add_argument("--baglam", help="yalnız bu önekle başlayan baglamlar (ör. RNV ya da RNV/05_sohbet_ajani)")
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
    ye = mal.add_parser("yeniden-etiketle")
    ye.add_argument("--uygula", action="store_true")
    ye.add_argument("--transkript-dizini", help=argparse.SUPPRESS)
    ye.set_defaults(f=cmd_maliyet_yeniden_etiketle)
    oz = mal.add_parser("ozet")
    oz.add_argument("--json", action="store_true")
    oz.set_defaults(f=cmd_maliyet_ozet)

    ru = alt.add_parser("perspektif", aliases=["ruya"])  # "ruya": eski ad, geriye uyumlu takma ad
    ru.add_argument("islem", choices=["durum", "basla", "basladi", "kaydet", "bitti", "hafiza"])
    ru.add_argument("yol", nargs="?")
    ru.set_defaults(f=cmd_perspektif)

    ui = alt.add_parser("ui-ozet")
    ui.add_argument("--oturum")
    ui.add_argument("--yaz", action="store_true")
    ui.set_defaults(f=cmd_ui_ozet)
    pa = alt.add_parser("panel")
    pa.add_argument("--port", type=int, default=8765)
    pa.add_argument("--on-planda", action="store_true", help="sunucuyu bu süreçte çalıştır (Ctrl+C ile durur)")
    pa.add_argument("--ac", action="store_true", help="adresi varsayılan tarayıcıda aç")
    pa.set_defaults(f=cmd_panel)

    on = alt.add_parser("onay").add_subparsers(dest="alt", required=True)
    x = on.add_parser("liste")
    x.add_argument("--durum")
    x.add_argument("--tur")
    x.add_argument("--json", action="store_true")
    x = on.add_parser("goster")
    x.add_argument("id")
    x = on.add_parser("iste")
    x.add_argument("--baslik", required=True)
    x.add_argument("--metin", required=True)
    x.add_argument("--secenek", action="append", default=[])
    x.add_argument("--oturum")
    x = on.add_parser("karar")
    x.add_argument("id")
    g_ = x.add_mutually_exclusive_group(required=True)
    g_.add_argument("--onay", action="store_true")
    g_.add_argument("--ret", action="store_true")
    x.add_argument("--secim")
    x.add_argument("--not", dest="not_")
    x = on.add_parser("al")
    x.add_argument("id")
    x.add_argument("--oturum")
    x = on.add_parser("uygulandi")
    x.add_argument("id")
    x.add_argument("--ozet", required=True)
    x.add_argument("--oturum")
    x = on.add_parser("iptal")
    x.add_argument("id")
    x.add_argument("--not", dest="not_", required=True)
    on.add_parser("esitle")
    alt.choices["onay"].set_defaults(f=cmd_onay)

    ku = alt.add_parser("kural").add_subparsers(dest="alt", required=True)
    x = ku.add_parser("liste")
    x.add_argument("--json", action="store_true")
    for ad in ("oner", "ekle"):
        x = ku.add_parser(ad)
        x.add_argument("--metin", required=True)
        x.add_argument("--neden", default="")
    x = ku.add_parser("duzenle")
    x.add_argument("id")
    x.add_argument("--metin", required=True)
    x.add_argument("--neden")
    x = ku.add_parser("kaldir")
    x.add_argument("id")
    x.add_argument("--not", dest="not_", required=True)
    alt.choices["kural"].set_defaults(f=cmd_kural)

    import niyet
    niyet.ekle_ayristirici(alt)

    is_ = alt.add_parser("is", help="kalıcı iş katmanı (bir iş birden çok sohbete/karta yayılır)").add_subparsers(dest="alt", required=True)
    ia = is_.add_parser("ac")
    ia.add_argument("baslik")
    ia.add_argument("--klasor", required=True)
    ia.add_argument("--etiket", action="append", default=[])
    ia.set_defaults(f=cmd_is_ac)
    idv = is_.add_parser("devam")
    idv.add_argument("is_id")
    idv.set_defaults(f=cmd_is_devam)
    il = is_.add_parser("liste")
    il.add_argument("--durum", choices=["acik", "beklemede", "kapandi", "hepsi"], default="acik")
    il.set_defaults(f=cmd_is_liste)
    ik_ = is_.add_parser("kapat")
    ik_.add_argument("is_id")
    ik_.set_defaults(f=cmd_is_kapat)
    it_ = is_.add_parser("todo")
    it_.add_argument("is_id")
    it_.add_argument("--ekle", metavar="METİN", help="todo.md sonuna açık madde ekler")
    it_.add_argument("--bitti", metavar="SEÇİCİ", help="açık maddeyi [x] yapar (sıra no ya da alt dize)")
    it_.add_argument("--not", dest="not_", metavar="METİN", help="--bitti ile satır sonuna tarihli not")
    it_.set_defaults(f=cmd_is_todo)
    isr = is_.add_parser("serit", help="iş şeridi: yapıldı/şimdi/sırada/planda kart yok")
    isr.add_argument("is_id")
    isr.add_argument("--json", action="store_true")
    isr.set_defaults(f=cmd_is_serit)
    is_.add_parser("aktif").set_defaults(f=cmd_is_aktif)
    io_ = is_.add_parser("onar", help="isler.json'u iş klasörlerindeki is.json'lardan yeniden kur (varsayılan kuru koşu)")
    io_.add_argument("--uygula", action="store_true", help="farkları isler.json'a yaz")
    io_.add_argument("--klasor", action="append", default=[], help="ek iş klasörü (tekrarlanabilir)")
    io_.add_argument("--kartlar", action="store_true",
                     help="'is' alanı boş kartları listele ve önerilen işi yaz (--uygula ile bağla, gerekirse iş/klasör aç)")
    io_.set_defaults(f=cmd_is_onar)
    ib_ = is_.add_parser("bagla", help="iş alanı boş kartları görev klasörü/oturum işine bağla (varsayılan kuru koşu)")
    ib_.add_argument("--geriye", action="store_true", help="mevcut kartları geriye dönük bağla")
    ib_.add_argument("--uygula", action="store_true", help="değişiklikleri yaz")
    ib_.set_defaults(f=cmd_is_bagla)

    kp = alt.add_parser("kpi", help="8 KPI salt okuma ölçümü")
    kp.add_argument("--json", action="store_true", help="makine çıktısı")
    kp.add_argument("--gun", type=float, default=None, help="son N gün")
    kp.set_defaults(f=cmd_kpi)

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
    degistiren = {"kart", "perspektif", "ruya", "baslat"}
    if a.komut in degistiren or (a.komut, alt_komut) in {("defter", "ekle"), ("maliyet", "tur"), ("maliyet", "gecmis"), ("maliyet", "yeniden-etiketle")}:
        sd = L.durum_dizini()
        if sd and not (a.komut == "kart" and alt_komut in ("goster", "liste")):
            import ozet
            ozet.yaz(sd, L.proje_dizini())


if __name__ == "__main__":
    main()
