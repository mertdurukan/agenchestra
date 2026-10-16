"""G-157 / I-030 P6-P7: `orkestra iz` ağaç çıktısı ve `orkestra iz kapsama` ölçeri.

`py -3.13 -m pytest plugins/orkestra/tests/test_iz.py -q -p no:cacheprovider`

Modül sözleşmesi (testin tanımladığı arayüz; sd = .claude/orkestra durum dizini):

  iz.toplam(kayitlar) -> {"usd","token","giris","cikis","onbellek_okuma","onbellek_yazma"}
      defter satırı listesinin tek toplama fonksiyonu (token = dört kalemin toplamı). is_rapor.py de bunu çağırır.
  iz.agac(sd, secici) -> {"secici","tur","kok","toplam"} | None (eşleşen defter satırı yok)
      secici: 'I-nnn' (tur='is'), '<oturum8>-<sıra4>' istek kimliği (tur='istek'), diğer her şey oturum kimliği
      (tur='oturum'). Satır seçimi ork_lib.maliyet_kayitlari üzerindendir (ham dosya toplanmaz).
      toplam = iz.toplam(seçilen defter satırları); kok[giris..usd] ona birebir eşittir.
      Düğüm: {"tip","ad","span_id","sure_ms","giris","cikis","onbellek_okuma","onbellek_yazma","usd","model",
              "tahmin","cocuklar"}.
        istek seçicide kök tip='istek' (ad = gunluk istek satırının 'ne'si), çocukları tip='tur' (ana tur,
        span_id '<istek>.t<n>') ve tip='alt' (alt ajan, span_id '<istek>.a-<agent_id>'); bunların çocukları
        tip='arac' (zaman.jsonl tur='arac', ust_span_id ile bağlı).
        is / oturum seçicide kök tip='is' / 'oturum'; çocukları tip='istek' düğümleridir (istek_id'siz satırlar
        ad='(istek kimliği yok)', span_id=None tek düğümde toplanır); her istek düğümü yukarıdaki gibi açılır.
      tur/alt/istek düğümünün token ve usd'si kendi defter satırlarındandır. Araç düğümü tahmin=True taşır ve
      defter toplamına KATILMAZ (token'ı mesaj usage'ından paylaştırılmış tahmindir; çifte sayım olur).
      istek metni: 'ne' yoksa gunluk 'metin'i ad olur. sure_ms: tur/alt düğümünde zaman.jsonl'deki kendi span'ının süresi; araçta kendi süresi.
  iz.metin(agac_sozlugu) -> str     her düğüm bir satır: süre 'N.Ns', 'giris=N cikis=N okuma=N yazma=N', '$<usd:.6f>',
      model; araç satırlarında 'tahmin', başka satırda 'tahmin' geçmez.
  iz.json_metni(agac_sozlugu) -> str ; iz.csv_metni(agac_sozlugu) -> str
      csv başlığı: tip,ad,span_id,ust_span_id,sure_ms,giris,cikis,onbellek_okuma,onbellek_yazma,usd,model,tahmin
      ilk veri satırı kök (toplamlar), sonra derinlik-öncelikli.
  iz.kapsama(sd) -> {"olcum_saati","satir_sayisi","is_bos_yuzde","istek_id_bos_yuzde","ne_bos_yuzde","atif_nedeni",
                     "esik_yuzde","asildi"}
      is_bos_yuzde / istek_id_bos_yuzde: maliyet_kayitlari satırlarında is ('', '-', yok) / istek_id boş oranı;
      ne_bos_yuzde: gunluk tur='istek' satırlarında 'ne' boş oranı; yüzdeler 1 ondalığa yuvarlı;
      atif_nedeni: {neden: satır sayısı}; esik_yuzde: iz.AYAR_YOLU json'unun 'is_bos_esik_yuzde' değeri (yoksa 10);
      asildi: is_bos_yuzde > esik (eşit değil).
  iz.kapsama_satiri(sd) -> str      eşik aşılmadıysa '' ; aşıldıysa tek satır ('orkestra iz kapsama' geçer).
  iz.AYAR_YOLU                      ayarlar/iz_kapsama.json yolu (çağrı anında okunur; test yamalar).
CLI: `orkestra iz <secici> [--json|--csv]`, `orkestra iz kapsama [--json]`; bilinmeyen seçici -> çıkış 2, stderr dolu.
hook.session_start: eşik aşılırsa bağlama kapsama_satiri'ni TEK satır ekler; aşılmazsa eklemez.
"""
import contextlib
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(KOK, "scripts")
ORKESTRA = os.path.join(SCRIPTS, "orkestra.py")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OT = "abcd1234-aaaa-bbbb-cccc-333344445555"
OT2 = "efgh5678-aaaa-bbbb-cccc-333344445555"
I1 = "abcd1234-0001"
I2 = "abcd1234-0002"
I3 = "efgh5678-0001"
KALEMLER = ("giris", "cikis", "onbellek_okuma", "onbellek_yazma")


def jyaz(yol, satirlar):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        for s in satirlar:
            f.write(json.dumps({"v": 1, **s}, ensure_ascii=False) + "\n")


def mal(oturum, istek, span, is_, usd, g, c, o, y, model="claude-haiku-5-5", agent_id="", gorev="-", **ek):
    r = {"zaman": "2026-10-16T10:00:00+03:00", "oturum": oturum, "gorev": gorev, "agent_id": agent_id, "model": model,
         "surec": "-", "ajan": "ana", "giris": g, "cikis": c, "onbellek_okuma": o, "onbellek_yazma": y,
         "maliyet_usd": usd, "kaynak": "hook", "tarife": "1sa"}
    if is_ is not None:
        r["is"] = is_
    if istek:
        r.update({"istek_id": istek, "span_id": span, "ust_span_id": istek})
    r.update(ek)
    return r


def zam(tur, oturum, istek, span, ust, sure_ms, **ek):
    r = {"zaman": "2026-10-16T10:00:05+03:00", "oturum": oturum, "tur": tur, "sure_ms": sure_ms,
         "istek_id": istek, "span_id": span, "ust_span_id": ust}
    r.update(ek)
    return r


def arac(ad, oturum, istek, ust, n, sure_ms, g, c, o, y):
    return zam("arac", oturum, istek, f"{ust}.c{n}", ust, sure_ms, arac=ad, giris=g, cikis=c, onbellek_okuma=o,
               onbellek_yazma=y, tahmin=True)


def cli(proje, *args):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=proje, PYTHONUTF8="1")
    return subprocess.run([sys.executable, ORKESTRA, "iz", *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, cwd=proje, timeout=120)


def dugumler(d):
    yield d
    for c in d.get("cocuklar") or []:
        yield from dugumler(c)


class _Ortak(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.proje = self._t.name
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        for a in ("oturumlar", "gorevler"):
            os.makedirs(os.path.join(self.sd, a))
        self.addCleanup(self._t.cleanup)
        t1, a1 = f"{I1}.t1", f"{I1}.a-ag1"
        jyaz(os.path.join(self.sd, "maliyet.jsonl"), [
            mal(OT, I1, t1, "I-030", 0.012345, 100, 40, 31, 7),
            mal(OT, I1, a1, "I-030", 0.034567, 200, 50, 10, 5, model="claude-sonnet-5-5", agent_id="ag1", gorev="G-007"),
            mal(OT, I2, f"{I2}.t1", "I-030", 0.001001, 10, 5, 0, 0),
            mal(OT, None, None, "-", 0.5, 1000, 100, 900, 20),       # istek kimliksiz, işsiz -> I-000
            mal(OT2, I3, f"{I3}.t1", "I-031", 0.25, 77, 33, 11, 3),
        ])
        jyaz(os.path.join(self.sd, "zaman.jsonl"), [
            zam("ana", OT, I1, t1, I1, 10000),
            zam("alt", OT, I1, a1, I1, 30000, agent_id="ag1"),
            zam("ana", OT, I2, f"{I2}.t1", I2, 5000),
            arac("Read", OT, I1, t1, 1, 2500, 50, 20, 15, 3),
            arac("Bash", OT, I1, t1, 2, 4000, 50, 20, 16, 4),
            arac("Edit", OT, I1, a1, 1, 1000, 100, 25, 5, 2),
        ])
        jyaz(os.path.join(self.sd, "gunluk.jsonl"), [
            {"zaman": "2026-10-16T09:59:00+03:00", "oturum": OT, "tur": "istek", "metin": "hook bağlamını ölç",
             "istek_id": I1, "ne": "hook bağlamını ölç"},
            {"zaman": "2026-10-16T10:30:00+03:00", "oturum": OT, "tur": "istek", "metin": "devam", "istek_id": I2},
        ])
        self.mal = None

    def defter(self):
        import ork_lib as L
        return L.maliyet_kayitlari(self.sd)

    def sec(self, **f):
        return [r for r in self.defter() if all(r.get(k) == v for k, v in f.items())]


class AgacYapisi(_Ortak):  # K1
    def test_istek_secici_agac_yapisi(self):
        import iz
        a = iz.agac(self.sd, I1)
        self.assertEqual(a["tur"], "istek")
        k = a["kok"]
        self.assertEqual(k["tip"], "istek")
        self.assertEqual(k["ad"], "hook bağlamını ölç")
        tipler = sorted(c["tip"] for c in k["cocuklar"])
        self.assertEqual(tipler, ["alt", "tur"])
        tur = next(c for c in k["cocuklar"] if c["tip"] == "tur")
        alt = next(c for c in k["cocuklar"] if c["tip"] == "alt")
        self.assertEqual(tur["span_id"], f"{I1}.t1")
        self.assertEqual(alt["span_id"], f"{I1}.a-ag1")
        self.assertEqual(sorted(c["ad"] for c in tur["cocuklar"]), ["Bash", "Read"])
        self.assertEqual([c["ad"] for c in alt["cocuklar"]], ["Edit"])
        for c in tur["cocuklar"] + alt["cocuklar"]:
            self.assertEqual(c["tip"], "arac")
            self.assertEqual(c["cocuklar"], [])

    def test_her_dugumde_alanlar_ve_arac_tahmin_isareti(self):
        import iz
        for d in dugumler(iz.agac(self.sd, I1)["kok"]):
            for alan in ("sure_ms",) + KALEMLER + ("usd", "model", "tahmin", "cocuklar"):
                self.assertIn(alan, d, f"{d.get('tip')}/{d.get('ad')}: {alan} yok")
            if d["tip"] == "arac":
                self.assertIs(d["tahmin"], True)
            else:
                self.assertFalse(d["tahmin"])

    def test_sure_ve_token_kendi_span_inden(self):
        import iz
        k = iz.agac(self.sd, I1)["kok"]
        tur = next(c for c in k["cocuklar"] if c["tip"] == "tur")
        alt = next(c for c in k["cocuklar"] if c["tip"] == "alt")
        self.assertEqual(tur["sure_ms"], 10000)
        self.assertEqual(alt["sure_ms"], 30000)
        self.assertEqual((tur["giris"], tur["cikis"], tur["onbellek_okuma"], tur["onbellek_yazma"]), (100, 40, 31, 7))
        self.assertAlmostEqual(alt["usd"], 0.034567, places=9)
        self.assertIn("sonnet", alt["model"])
        okuma = next(c for c in tur["cocuklar"] if c["ad"] == "Read")
        self.assertEqual(okuma["sure_ms"], 2500)
        self.assertEqual((okuma["giris"], okuma["cikis"], okuma["onbellek_okuma"], okuma["onbellek_yazma"]), (50, 20, 15, 3))

    def test_is_ve_oturum_seciciler_istek_dugumleri_verir(self):
        import iz
        a = iz.agac(self.sd, "I-030")
        self.assertEqual(a["tur"], "is")
        self.assertEqual(a["kok"]["tip"], "is")
        self.assertEqual(sorted(c["span_id"] for c in a["kok"]["cocuklar"]), sorted([I1, I2]))
        self.assertTrue(all(c["tip"] == "istek" for c in a["kok"]["cocuklar"]))
        o = iz.agac(self.sd, OT)
        self.assertEqual(o["tur"], "oturum")
        self.assertEqual(o["kok"]["tip"], "oturum")
        yok = [c for c in o["kok"]["cocuklar"] if c["span_id"] is None]
        self.assertEqual(len(yok), 1)
        self.assertEqual(yok[0]["ad"], "(istek kimliği yok)")
        self.assertEqual(len(o["kok"]["cocuklar"]), 3)

    def test_istek_dugumleri_koke_esit_toplanir(self):
        import iz
        for sec in ("I-030", OT, "I-000"):
            k = iz.agac(self.sd, sec)["kok"]
            self.assertAlmostEqual(sum(c["usd"] for c in k["cocuklar"]), k["usd"], places=9, msg=sec)
            for f in KALEMLER:
                self.assertEqual(sum(c[f] for c in k["cocuklar"]), k[f], f"{sec} {f}")

    def test_metin_cikti_satirlari(self):
        import iz
        a = iz.agac(self.sd, I1)
        m = iz.metin(a)
        satirlar = m.splitlines()
        self.assertIn(f"${a['kok']['usd']:.6f}", m)
        tahminli = [s for s in satirlar if "tahmin" in s]
        self.assertEqual(len(tahminli), 3)
        for ad in ("Read", "Bash", "Edit"):
            self.assertTrue(any(ad in s for s in tahminli), ad)
        self.assertIn("hook bağlamını ölç", satirlar[0])
        self.assertNotIn("tahmin", satirlar[0])
        okuma = next(s for s in tahminli if "Read" in s)
        self.assertIn("2.5s", okuma)
        self.assertIn("giris=50 cikis=20 okuma=15 yazma=3", okuma)
        self.assertTrue(any("claude-sonnet-5-5" in s for s in satirlar))

    def test_bilinmeyen_secici_none(self):
        import iz
        self.assertIsNone(iz.agac(self.sd, "I-999"))
        self.assertIsNone(iz.agac(self.sd, "abcd1234-9999"))
        self.assertIsNone(iz.agac(self.sd, "yok-oturum"))

    def test_bos_defterde_none(self):
        import iz
        bos = os.path.join(self.proje, "bos", ".claude", "orkestra")
        os.makedirs(bos)
        self.assertIsNone(iz.agac(bos, "I-030"))

    def test_arac_satiri_olmayan_istekte_agac_yine_kurulur(self):
        import iz
        a = iz.agac(self.sd, I2)
        tur = a["kok"]["cocuklar"][0]
        self.assertEqual(tur["tip"], "tur")
        self.assertEqual(tur["cocuklar"], [])
        self.assertEqual(a["kok"]["ad"], "devam")  # 'ne' yok: istek metni
        self.assertEqual(a["kok"]["sure_ms"], 5000)


class ToplamEsitligi(_Ortak):  # K2
    def _esit(self, a, satirlar):
        import iz
        beklenen = {f: sum(int(r.get(f) or 0) for r in satirlar) for f in KALEMLER}
        self.assertTrue(satirlar)
        for f in KALEMLER:
            self.assertEqual(a["kok"][f], beklenen[f], f)
            self.assertEqual(a["toplam"][f], beklenen[f], f)
        self.assertEqual(a["toplam"]["token"], sum(beklenen.values()))
        usd = sum(r["maliyet_usd"] for r in satirlar)
        self.assertAlmostEqual(a["kok"]["usd"], usd, places=9)
        self.assertAlmostEqual(a["toplam"]["usd"], usd, places=9)
        self.assertEqual(a["toplam"], {**a["toplam"], **iz.toplam(satirlar)})

    def test_sentetik_defterde_uc_secici(self):
        import iz
        self._esit(iz.agac(self.sd, I1), self.sec(istek_id=I1))
        self._esit(iz.agac(self.sd, "I-030"), self.sec(**{"is": "I-030"}))
        self._esit(iz.agac(self.sd, OT), self.sec(oturum=OT))

    def test_arac_tahmini_toplama_katilmaz(self):
        import iz
        a = iz.agac(self.sd, I1)
        # defter: 100+40+31+7 + 200+50+10+5 = 443; araç tahmin kalemleri (toplam 308) eklenseydi fazla olurdu
        self.assertEqual(a["toplam"]["token"], 443)

    def test_tekilleştirme_ve_duzeltme_ork_lib_ile_ayni(self):
        """Birikimli hook satırı (aynı agent_id iki kez) ve düzeltme dosyası: iz ham dosyayı değil
        ork_lib.maliyet_kayitlari sonucunu toplar."""
        import iz
        t = f"{I1}.a-ag1"
        eski = mal(OT, I1, t, "I-030", 0.01, 20, 5, 0, 0, model="claude-sonnet-5-5", agent_id="ag1", gorev="G-007",
                   zaman="2026-10-16T09:00:00+03:00")
        yol = os.path.join(self.sd, "maliyet.jsonl")
        with open(yol, encoding="utf-8") as f:
            onceki = [json.loads(s) for s in f if s.strip()]
        jyaz(yol, [eski] + onceki)   # eski (daha küçük, daha erken) satır birikimli kopya: atılmalı
        a = iz.agac(self.sd, I1)
        self.assertEqual(a["toplam"]["giris"], 300)       # 100 + 200; 20 sayılmaz
        self._esit(a, self.sec(istek_id=I1))

    def test_cli_json_defter_toplamina_esit_gercek_surec(self):
        r = cli(self.proje, "I-030", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        satirlar = self.sec(**{"is": "I-030"})
        self.assertAlmostEqual(d["kok"]["usd"], sum(x["maliyet_usd"] for x in satirlar), places=9)
        for f in KALEMLER:
            self.assertEqual(d["kok"][f], sum(x[f] for x in satirlar), f)

    def test_cli_metin_kok_usd_defterle_ayni(self):
        r = cli(self.proje, "I-030")
        self.assertEqual(r.returncode, 0, r.stderr)
        usd = sum(x["maliyet_usd"] for x in self.sec(**{"is": "I-030"}))
        self.assertIn(f"${usd:.6f}", r.stdout)

    def test_cli_bilinmeyen_secici_hata(self):
        r = cli(self.proje, "I-999")
        self.assertEqual(r.returncode, 2)
        self.assertIn("I-999", r.stderr)

    def test_cli_secicisiz_hata(self):
        r = cli(self.proje)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("invalid choice", r.stderr)  # komut kayıtlı, yalnız seçici eksik


class CiktiBicimleri(_Ortak):  # K3
    def test_json_agacla_ayni_toplam(self):
        import iz
        a = iz.agac(self.sd, "I-030")
        j = json.loads(iz.json_metni(a))
        self.assertEqual(j["toplam"], a["toplam"])
        self.assertEqual(j["kok"]["usd"], a["kok"]["usd"])

    def test_csv_ilk_satir_koke_esit_ve_baslik(self):
        import iz
        a = iz.agac(self.sd, I1)
        satirlar = list(csv.DictReader(io.StringIO(iz.csv_metni(a))))
        self.assertEqual(list(satirlar[0].keys()), ["tip", "ad", "span_id", "ust_span_id", "sure_ms", "giris", "cikis",
                                                   "onbellek_okuma", "onbellek_yazma", "usd", "model", "tahmin"])
        k = satirlar[0]
        self.assertEqual(k["tip"], "istek")
        self.assertAlmostEqual(float(k["usd"]), a["kok"]["usd"], places=6)
        for f in KALEMLER:
            self.assertEqual(int(k[f]), a["kok"][f])
        self.assertEqual(len(satirlar), 1 + 2 + 3)  # kök + tur + alt + 3 araç
        self.assertEqual(sum(1 for s in satirlar if s["tip"] == "arac" and s["tahmin"].lower() == "true"), 3)

    def test_cli_csv_json_metin_ayni_kok_usd(self):
        j = json.loads(cli(self.proje, I1, "--json").stdout)
        r = cli(self.proje, I1, "--csv")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = next(csv.DictReader(io.StringIO(r.stdout)))
        self.assertAlmostEqual(float(k["usd"]), j["kok"]["usd"], places=6)
        self.assertIn(f"${j['kok']['usd']:.6f}", cli(self.proje, I1).stdout)

    def test_is_rapor_iz_ile_ayni_toplam(self):
        import is_rapor
        import iz
        r = is_rapor.rapor(self.sd)
        for i in ("I-030", "I-031", "I-000"):
            s = next(x for x in r["satirlar"] if x["is"] == i)
            t = iz.agac(self.sd, i)["toplam"]
            self.assertAlmostEqual(s["usd"], t["usd"], places=6, msg=i)
            self.assertEqual(s["token"], t["token"], i)

    def test_is_rapor_iz_toplam_fonksiyonunu_cagirir(self):
        import is_rapor
        import iz
        gercek = iz.toplam
        cagrilar = []

        def sarmal(kayitlar):
            cagrilar.append(len(kayitlar))
            return gercek(kayitlar)

        with mock.patch.object(iz, "toplam", side_effect=sarmal):
            is_rapor.rapor(self.sd)
            self.assertGreaterEqual(len(cagrilar), 3)
            iz.agac(self.sd, "I-030")
        self.assertGreaterEqual(len(cagrilar), 4, "is_rapor her iş (3) ve iz.agac iz.toplam'ı çağırmalı (kopya hesap yok)")

    def test_is_rapor_kopya_hesap_icermez(self):
        with open(os.path.join(SCRIPTS, "is_rapor.py"), encoding="utf-8") as f:
            kaynak = f.read()
        self.assertTrue("import iz" in kaynak or "from iz import" in kaynak)

    def test_toplam_bos_ve_eksik_alan(self):
        import iz
        self.assertEqual(iz.toplam([]), {"usd": 0, "token": 0, **{f: 0 for f in KALEMLER}})
        t = iz.toplam([{"giris": 5}, {"cikis": None, "maliyet_usd": 0.5}])
        self.assertEqual((t["giris"], t["token"]), (5, 5))
        self.assertAlmostEqual(t["usd"], 0.5, places=9)


class _KapsamaOrtak(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.proje = self._t.name
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        for a in ("oturumlar", "gorevler"):
            os.makedirs(os.path.join(self.sd, a))
        self.ayar = os.path.join(self.proje, "iz_kapsama.json")
        # 10 satır: 3 işsiz (2 oturum-isiz, 1 cursor), 5 istek_id'siz (3'ü işsiz değil)
        satirlar = []
        for n in range(10):
            ek = {}
            is_ = "I-030"
            istek = f"abcd1234-{n + 1:04d}" if n >= 5 else None
            if n == 0:
                is_, ek = "-", {"atif_nedeni": "oturum-isiz"}
            if n == 1:
                is_, ek = "", {"atif_nedeni": "oturum-isiz"}
            if n == 2:
                is_, ek = "-", {"atif_nedeni": "cursor"}
            satirlar.append(mal(OT, istek, f"{istek}.t1" if istek else None, is_, 0.01, 10 + n, 1, 0, 0, **ek))
        jyaz(os.path.join(self.sd, "maliyet.jsonl"), satirlar)
        jyaz(os.path.join(self.sd, "gunluk.jsonl"), [
            {"zaman": "2026-10-16T10:00:00+03:00", "oturum": OT, "tur": "istek", "metin": "a", "istek_id": "x-0001", "ne": "a"},
            {"zaman": "2026-10-16T10:01:00+03:00", "oturum": OT, "tur": "istek", "metin": "b", "istek_id": "x-0002", "ne": "b"},
            {"zaman": "2026-10-16T10:02:00+03:00", "oturum": OT, "tur": "istek", "metin": "c", "istek_id": "x-0003", "ne": "c"},
            {"zaman": "2026-10-16T10:03:00+03:00", "oturum": OT, "tur": "istek", "metin": "d", "istek_id": "x-0004"},
            {"zaman": "2026-10-16T10:04:00+03:00", "oturum": OT, "tur": "skill", "metin": "istek değil"},
        ])

    def esik(self, deger):
        with open(self.ayar, "w", encoding="utf-8") as f:
            json.dump({"surum": 1, "is_bos_esik_yuzde": deger}, f)
        import iz
        return mock.patch.object(iz, "AYAR_YOLU", self.ayar)


class Kapsama(_KapsamaOrtak):  # K4
    def test_uc_oran_ve_atif_nedeni_dagilimi(self):
        import iz
        with self.esik(10):
            k = iz.kapsama(self.sd)
        self.assertEqual(k["satir_sayisi"], 10)
        self.assertEqual(k["is_bos_yuzde"], 30.0)
        self.assertEqual(k["istek_id_bos_yuzde"], 50.0)
        self.assertEqual(k["ne_bos_yuzde"], 25.0)   # yalnız tur='istek' satırları paydada
        self.assertEqual(k["atif_nedeni"], {"oturum-isiz": 2, "cursor": 1})
        self.assertEqual(k["esik_yuzde"], 10)
        self.assertIs(k["asildi"], True)

    def test_olcum_saati_yazilir(self):
        import datetime
        import iz
        with self.esik(10):
            k = iz.kapsama(self.sd)
        z = datetime.datetime.fromisoformat(k["olcum_saati"])
        self.assertIsNotNone(z.tzinfo)
        self.assertLess(abs((datetime.datetime.now().astimezone() - z).total_seconds()), 120)

    def test_esik_sinirinda_asilmaz(self):
        import iz
        with self.esik(30):
            self.assertIs(iz.kapsama(self.sd)["asildi"], False)
        with self.esik(29.9):
            self.assertIs(iz.kapsama(self.sd)["asildi"], True)

    def test_bos_defter_sifira_bolmez(self):
        import iz
        bos = os.path.join(self.proje, "b", ".claude", "orkestra")
        os.makedirs(bos)
        with self.esik(10):
            k = iz.kapsama(bos)
        self.assertEqual(k["satir_sayisi"], 0)
        self.assertEqual((k["is_bos_yuzde"], k["istek_id_bos_yuzde"], k["ne_bos_yuzde"]), (0, 0, 0))
        self.assertEqual(k["atif_nedeni"], {})
        self.assertIs(k["asildi"], False)

    def test_varsayilan_ayar_dosyasi_esigi_tasir(self):
        yol = os.path.join(KOK, "ayarlar", "iz_kapsama.json")
        self.assertTrue(os.path.isfile(yol))
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["is_bos_esik_yuzde"], 10)
        import iz
        self.assertEqual(os.path.normcase(os.path.abspath(iz.AYAR_YOLU)), os.path.normcase(os.path.abspath(yol)))

    def test_ayar_dosyasi_yoksa_varsayilan_10(self):
        import iz
        with mock.patch.object(iz, "AYAR_YOLU", os.path.join(self.proje, "yok.json")):
            self.assertEqual(iz.kapsama(self.sd)["esik_yuzde"], 10)

    def test_kapsama_satiri_asimda_tek_satir(self):
        import iz
        with self.esik(10):
            s = iz.kapsama_satiri(self.sd)
        self.assertTrue(s)
        self.assertNotIn("\n", s)
        self.assertIn("orkestra iz kapsama", s)
        self.assertIn("30", s)
        self.assertLessEqual(len(s), 300)

    def test_kapsama_satiri_altinda_bos(self):
        import iz
        with self.esik(30):
            self.assertEqual(iz.kapsama_satiri(self.sd), "")

    def test_cli_kapsama_metin_ve_json(self):
        r = cli(self.proje, "kapsama")
        self.assertEqual(r.returncode, 0, r.stderr)
        for s in ("30.0", "50.0", "25.0", "oturum-isiz", "cursor", "2026-"):
            self.assertIn(s, r.stdout)
        j = cli(self.proje, "kapsama", "--json")
        self.assertEqual(j.returncode, 0, j.stderr)
        d = json.loads(j.stdout)
        self.assertEqual((d["is_bos_yuzde"], d["istek_id_bos_yuzde"], d["ne_bos_yuzde"]), (30.0, 50.0, 25.0))
        self.assertEqual(d["atif_nedeni"], {"oturum-isiz": 2, "cursor": 1})
        self.assertTrue(d["olcum_saati"])


class SessionStartSatiri(_KapsamaOrtak):  # K4 hook
    def baglam(self):
        import hook
        import perspektif
        import ork_lib as L
        buf = io.StringIO()
        rapor = {"okunmamis_rapor": None, "zamani_geldi": False, "calisiyor": False}
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(L, "bayatlik", return_value=None))
            st.enter_context(mock.patch.object(perspektif, "durum", return_value=rapor))
            st.enter_context(mock.patch.object(hook, "_yonlendirme_ipucu", return_value=""))
            st.enter_context(mock.patch.object(hook, "_panel_ac_satiri", return_value=""))
            st.enter_context(mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.proje}))
            st.enter_context(contextlib.redirect_stdout(buf))
            try:
                hook.session_start({"session_id": OT, "cwd": self.proje, "source": "startup",
                                    "transcript_path": os.path.join(self.proje, "tr.jsonl")})
            except SystemExit:
                pass
        return json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]

    def test_esik_asilinca_tek_satir_eklenir(self):
        with self.esik(10):
            c = self.baglam()
        satirlar = [s for s in c.splitlines() if "orkestra iz kapsama" in s]
        self.assertEqual(len(satirlar), 1, c)

    def test_esik_altinda_eklenmez(self):
        with self.esik(30):
            c = self.baglam()
        self.assertNotIn("orkestra iz kapsama", c)

    def test_olcer_hatasi_hook_u_dusurmez(self):
        import iz
        with self.esik(10), mock.patch.object(iz, "kapsama_satiri", side_effect=RuntimeError("bozuk")):
            c = self.baglam()
        self.assertIn("Orkestra bu projede açık", c)
        self.assertNotIn("orkestra iz kapsama", c)


if __name__ == "__main__":
    unittest.main()
