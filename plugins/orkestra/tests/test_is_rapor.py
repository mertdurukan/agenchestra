"""G-068: scripts/is_rapor.py ve `orkestra is rapor [IS] [--csv] [--cikti DOSYA]` (salt okuma iş raporu).

Modül sözleşmesi (testin tanımladığı arayüz; sd = .claude/orkestra durum dizini):
  rapor(sd) -> {
    "satirlar": [ {"is": "I-001", "baslik": str, "usd": float, "token": int, "claude_sn": float, "alt_sn": float,
                   "oturum": int, "kart": int, "todo_biten": int, "todo_toplam": int,
                   "ilk": "YYYY-MM-DD"|None, "son": "YYYY-MM-DD"|None}, ... ],   # iş sırası; I-000 (varsa) en sonda
    "kalite": {"todo_basina_usd": float|None, "ret_orani": float|None, "onbellek_isabet": float|None,
               "baglanmamis_emek_yuzde": float}
  }
  detay(sd, is_id) -> {"is": str, "oturum_gun": [{"oturum","gun","usd","token","claude_sn","alt_sn"}],
                       "kirilim": [{"surec","ajan","model","usd","token"}]} | None (iş yok)
  csv_metni(rapor_sozlugu) -> str          # başlık: is,baslik,usd,token,claude_sn,alt_sn,oturum,kart,todo_biten,todo_toplam,ilk,son
  metin(rapor_sozlugu) -> str              # kalite satırları dahil okunur tablo
  metin_detay(detay_sozlugu) -> str
Kurallar:
  - maliyet satırları ork_lib.maliyet_kayitlari ile tekilleştirilir; token = giris+cikis+onbellek_okuma+onbellek_yazma.
  - 'is' alanı '-', '' ya da yok -> I-000 kovası (yalnız raporda; dosyalar değişmez).
  - claude_sn = zaman.jsonl tur='ana' sure_ms toplamı/1000; alt_sn = tur='alt'. oturum = maliyet+zaman'daki ayrık oturum.
  - kart = kartlarda kart['is']==iş; todo = is.json 'klasor' altındaki todo.md ([x] biten, [ ] açık).
  - kalite: todo_basina_usd = (I-000 hariç toplam USD)/(toplam biten todo), biten 0 ise None;
    ret_orani = ret/(ret+onay) tüm kartların 'denetimler' kararlarından, karar yoksa None;
    onbellek_isabet = okuma/(giris+okuma+yazma) (kesir 0..1), payda 0 ise None;
    baglanmamis_emek_yuzde = 100*I-000 USD/toplam USD, toplam 0 ise 0.
CLI: `orkestra is rapor` (tablo), `orkestra is rapor I-001` (detay), `--csv` (stdout), `--cikti DOSYA` (--csv ile dosyaya).
"""
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
ORKESTRA = os.path.join(SCRIPTS, "orkestra.py")
sys.path.insert(0, SCRIPTS)

SIR = "sk-SIRDEGERI123"
AD_SOYAD = "Ayse Yilmaz"


def mal(oturum, gun, gorev, is_, surec, ajan, model, g, c, o, y, usd, aid, kaynak="tur", **ek):
    r = {"zaman": f"2026-03-{gun}T10:00:00+03:00", "oturum": oturum, "gorev": gorev, "agent_id": aid,
         "model": model, "surec": surec, "ajan": ajan, "giris": g, "cikis": c, "onbellek_okuma": o,
         "onbellek_yazma": y, "maliyet_usd": usd, "kaynak": kaynak, "tarife": "1sa"}
    if is_ is not None:
        r["is"] = is_
    r.update(ek)
    return r


MALIYET = [
    mal("s1", "10", "G-001", "I-001", "is", "orkestra:isci", "sonnet", 100, 50, 300, 50, 1.00, "a1",
        kullanici=AD_SOYAD, anahtar=SIR),
    mal("s1", "11", "G-001", "I-001", "denetim", "orkestra:denetci", "sonnet", 10, 10, 0, 0, 0.25, "a2"),
    mal("s2", "11", "-", "I-001", "plan", "ana", "opus", 20, 30, 100, 0, 0.75, None, "hook"),
    # a1 için 'tur' var: bu hook kopyası tekilleştirmede atılmalı (9 USD sayılmamalı)
    mal("s1", "10", "G-001", "I-001", "is", "orkestra:isci", "sonnet", 100, 50, 300, 50, 9.00, "a1", "hook"),
    mal("s3", "12", "G-003", "I-002", "is", "orkestra:isci", "sonnet", 10, 10, 0, 0, 1.00, "a4"),
    mal("s9", "12", "-", "-", "plan", "ana", "opus", 100, 0, 0, 0, 0.50, "a5"),
    mal("s9", "12", "-", "", "plan", "ana", "opus", 50, 50, 0, 0, 0.50, "a6"),
    mal("s9", "12", "-", None, "plan", "ana", "opus", 0, 0, 0, 0, 0.25, "a7"),  # 'is' alanı hiç yok
]


def zr(oturum, gun, is_, tur, sn):
    return {"zaman": f"2026-03-{gun}T10:05:00+03:00", "oturum": oturum, "is": is_, "tur": tur, "sure_ms": sn * 1000}


ZAMAN = [
    zr("s1", "10", "I-001", "ana", 60), zr("s1", "10", "I-001", "alt", 30), zr("s2", "11", "I-001", "ana", 120),
    zr("s3", "12", "I-002", "ana", 10), zr("s9", "12", "-", "ana", 5),
]


def kart(gid, is_, kararlar):
    return {"id": gid, "baslik": "x", "sinif": "kod", "basamak": "T2", "durum": "onaylandi", "is": is_,
            "gecmis": [], "denetimler": [{"zaman": "2026-03-10T11:00:00+03:00", "sira": i + 1, "karar": k}
                                           for i, k in enumerate(kararlar)]}


KARTLAR = [kart("G-001", "I-001", ["ret", "onay"]), kart("G-002", "I-001", ["onay"]), kart("G-003", "I-002", [])]


def jyaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)


def jsonl_yaz(yol, satirlar):
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        for r in satirlar:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def is_kur(kok, is_id, baslik, todo):
    klasor = os.path.join(kok, "isler", is_id)
    os.makedirs(klasor, exist_ok=True)
    with open(os.path.join(klasor, "todo.md"), "w", encoding="utf-8") as f:
        f.write(todo)
    jyaz(os.path.join(klasor, "is.json"), {"id": is_id, "baslik": baslik, "durum": "acik", "klasor": klasor,
                                           "olusturma": "2026-03-10T09:00:00+03:00", "kartlar": [], "oturumlar": []})
    return klasor


def durum_kur(kok):
    """kok/.claude/orkestra altında tam sahte durum; döner sd."""
    sd = os.path.join(kok, ".claude", "orkestra")
    os.makedirs(os.path.join(sd, "gorevler"), exist_ok=True)
    jsonl_yaz(os.path.join(sd, "maliyet.jsonl"), MALIYET)
    jsonl_yaz(os.path.join(sd, "zaman.jsonl"), ZAMAN)
    for k in KARTLAR:
        jyaz(os.path.join(sd, "gorevler", k["id"] + ".json"), k)
    k1 = is_kur(kok, "I-001", "Birinci is", "# T\n- [x] a\n- [x] b\n- [ ] c\n- [ ] d\n")
    k2 = is_kur(kok, "I-002", "Ikinci is", "# T\n- [ ] a\n")
    jyaz(os.path.join(sd, "isler.json"), {"sayac": 2, "isler": {
        "I-001": {"klasor": k1, "baslik": "Birinci is", "durum": "acik", "olusturma": "2026-03-10T09:00:00+03:00"},
        "I-002": {"klasor": k2, "baslik": "Ikinci is", "durum": "acik", "olusturma": "2026-03-12T09:00:00+03:00"}}})
    return sd


def agac_ozeti(kok):
    out = {}
    for d, _, dosyalar in os.walk(kok):
        for f in dosyalar:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, kok)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def cli(proje, *args):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=proje, PYTHONUTF8="1")
    return subprocess.run([sys.executable, ORKESTRA, "is", "rapor", *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, cwd=proje, timeout=120)


def satir(r, is_id):
    s = [x for x in r["satirlar"] if x["is"] == is_id]
    assert len(s) == 1, f"{is_id} satırı {len(s)} adet"
    return s[0]


class Temel(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.kok = self._t.name
        self.sd = durum_kur(self.kok)

    def tearDown(self):
        self._t.cleanup()


class Tablo(Temel):  # kriter 1
    def test_her_is_icin_satir_ve_kolonlar(self):
        import is_rapor
        r = is_rapor.rapor(self.sd)
        self.assertEqual([x["is"] for x in r["satirlar"]], ["I-001", "I-002", "I-000"])
        for alan in ("is", "baslik", "usd", "token", "claude_sn", "alt_sn", "oturum", "kart", "todo_biten",
                     "todo_toplam", "ilk", "son"):
            self.assertIn(alan, r["satirlar"][0])

    def test_i001_degerleri_tekillestirilmis(self):
        import is_rapor
        s = satir(is_rapor.rapor(self.sd), "I-001")
        self.assertEqual(s["baslik"], "Birinci is")
        self.assertAlmostEqual(s["usd"], 2.00, places=6)  # 9 USD'lik hook kopyası sayılmaz
        self.assertEqual(s["token"], 670)
        self.assertAlmostEqual(s["claude_sn"], 180.0, places=3)
        self.assertAlmostEqual(s["alt_sn"], 30.0, places=3)
        self.assertEqual(s["oturum"], 2)
        self.assertEqual(s["kart"], 2)
        self.assertEqual((s["todo_biten"], s["todo_toplam"]), (2, 4))
        self.assertEqual((s["ilk"], s["son"]), ("2026-03-10", "2026-03-11"))

    def test_i002_degerleri(self):
        import is_rapor
        s = satir(is_rapor.rapor(self.sd), "I-002")
        self.assertAlmostEqual(s["usd"], 1.00, places=6)
        self.assertEqual(s["token"], 20)
        self.assertAlmostEqual(s["claude_sn"], 10.0, places=3)
        self.assertEqual(s["alt_sn"], 0)
        self.assertEqual((s["oturum"], s["kart"]), (1, 1))
        self.assertEqual((s["todo_biten"], s["todo_toplam"]), (0, 1))

    def test_metin_tablosu_is_ve_todo_icerir(self):
        import is_rapor
        m = is_rapor.metin(is_rapor.rapor(self.sd))
        for beklenen in ("I-001", "I-002", "I-000", "2/4", "0/1"):
            self.assertIn(beklenen, m)

    def test_cli_tablo(self):
        p = cli(self.kok)
        self.assertEqual(p.returncode, 0, p.stderr)
        for beklenen in ("I-001", "I-002", "I-000", "2/4"):
            self.assertIn(beklenen, p.stdout)


class Detay(Temel):  # kriter 2
    def test_oturum_gun_kirilimi(self):
        import is_rapor
        d = is_rapor.detay(self.sd, "I-001")
        self.assertEqual(d["is"], "I-001")
        og = {(x["oturum"], x["gun"]): x for x in d["oturum_gun"]}
        self.assertEqual(set(og), {("s1", "2026-03-10"), ("s1", "2026-03-11"), ("s2", "2026-03-11")})
        self.assertAlmostEqual(og[("s1", "2026-03-10")]["usd"], 1.00, places=6)
        self.assertEqual(og[("s1", "2026-03-10")]["token"], 500)
        self.assertAlmostEqual(og[("s1", "2026-03-10")]["claude_sn"], 60.0, places=3)
        self.assertAlmostEqual(og[("s1", "2026-03-10")]["alt_sn"], 30.0, places=3)
        self.assertAlmostEqual(og[("s2", "2026-03-11")]["usd"], 0.75, places=6)
        self.assertAlmostEqual(og[("s2", "2026-03-11")]["claude_sn"], 120.0, places=3)
        self.assertAlmostEqual(sum(x["usd"] for x in d["oturum_gun"]), 2.00, places=6)

    def test_surec_ajan_model_kirilimi(self):
        import is_rapor
        d = is_rapor.detay(self.sd, "I-001")
        k = {(x["surec"], x["ajan"], x["model"]): x for x in d["kirilim"]}
        self.assertEqual(set(k), {("is", "orkestra:isci", "sonnet"), ("denetim", "orkestra:denetci", "sonnet"),
                                  ("plan", "ana", "opus")})
        self.assertAlmostEqual(k[("is", "orkestra:isci", "sonnet")]["usd"], 1.00, places=6)
        self.assertEqual(k[("is", "orkestra:isci", "sonnet")]["token"], 500)
        self.assertAlmostEqual(k[("plan", "ana", "opus")]["usd"], 0.75, places=6)

    def test_i000_detayi(self):
        import is_rapor
        d = is_rapor.detay(self.sd, "I-000")
        self.assertAlmostEqual(sum(x["usd"] for x in d["oturum_gun"]), 1.25, places=6)

    def test_olmayan_is_none(self):
        import is_rapor
        self.assertIsNone(is_rapor.detay(self.sd, "I-999"))

    def test_cli_detay(self):
        p = cli(self.kok, "I-001")
        self.assertEqual(p.returncode, 0, p.stderr)
        for beklenen in ("s1", "2026-03-10", "orkestra:isci", "orkestra:denetci", "opus"):
            self.assertIn(beklenen, p.stdout)

    def test_cli_olmayan_is_hata(self):
        p = cli(self.kok, "I-999")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("I-999", p.stdout + p.stderr)


class Csv(Temel):  # kriter 3
    BASLIK = ["is", "baslik", "usd", "token", "claude_sn", "alt_sn", "oturum", "kart", "todo_biten", "todo_toplam",
              "ilk", "son"]

    def test_csv_metni_basligi_ve_satirlari(self):
        import is_rapor
        satirlar = list(csv.DictReader(io.StringIO(is_rapor.csv_metni(is_rapor.rapor(self.sd)))))
        self.assertEqual(list(satirlar[0].keys()), self.BASLIK)
        self.assertEqual([s["is"] for s in satirlar], ["I-001", "I-002", "I-000"])
        self.assertAlmostEqual(float(satirlar[0]["usd"]), 2.0, places=4)
        self.assertEqual(satirlar[0]["token"], "670")
        self.assertEqual((satirlar[0]["todo_biten"], satirlar[0]["todo_toplam"]), ("2", "4"))

    def test_cli_csv_stdout(self):
        p = cli(self.kok, "--csv")
        self.assertEqual(p.returncode, 0, p.stderr)
        satirlar = list(csv.DictReader(io.StringIO(p.stdout)))
        self.assertEqual([s["is"] for s in satirlar], ["I-001", "I-002", "I-000"])

    def test_cli_csv_cikti_dosyasi(self):
        hedef = os.path.join(self.kok, "cikti", "rapor.csv")
        os.makedirs(os.path.dirname(hedef))
        p = cli(self.kok, "--csv", "--cikti", hedef)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(hedef, encoding="utf-8", newline="") as f:
            satirlar = list(csv.DictReader(f))
        self.assertEqual([s["is"] for s in satirlar], ["I-001", "I-002", "I-000"])
        self.assertNotIn("I-001,", p.stdout)  # CSV içeriği stdout'a basılmaz

    def test_csv_bayraksiz_tablo_csv_degil(self):
        p = cli(self.kok)
        self.assertNotIn("is,baslik,usd", p.stdout)


class IsizKova(Temel):  # kriter 4
    def test_i000_toplami(self):
        import is_rapor
        s = satir(is_rapor.rapor(self.sd), "I-000")
        self.assertAlmostEqual(s["usd"], 1.25, places=6)  # '-', '' ve alanı olmayan satırlar
        self.assertEqual(s["token"], 200)
        self.assertAlmostEqual(s["claude_sn"], 5.0, places=3)
        self.assertEqual(s["oturum"], 1)

    def test_i000_yoksa_satir_yok(self):
        import is_rapor
        jsonl_yaz(os.path.join(self.sd, "maliyet.jsonl"), [m for m in MALIYET if m.get("is") not in (None, "", "-")])
        jsonl_yaz(os.path.join(self.sd, "zaman.jsonl"), [z for z in ZAMAN if z["is"] != "-"])
        self.assertNotIn("I-000", [x["is"] for x in is_rapor.rapor(self.sd)["satirlar"]])

    def test_dosyalar_degismez(self):
        import is_rapor
        once = agac_ozeti(self.kok)
        r = is_rapor.rapor(self.sd)
        is_rapor.detay(self.sd, "I-001")
        is_rapor.csv_metni(r)
        is_rapor.metin(r)
        self.assertEqual(agac_ozeti(self.kok), once)
        cli(self.kok)
        cli(self.kok, "I-001")
        cli(self.kok, "--csv")
        self.assertEqual(agac_ozeti(self.kok), once)
        with open(os.path.join(self.sd, "maliyet.jsonl"), encoding="utf-8") as f:
            self.assertNotIn("I-000", f.read())  # kova yalnız raporda


class Kalite(Temel):  # kriter 5
    def test_kalite_degerleri(self):
        import is_rapor
        k = is_rapor.rapor(self.sd)["kalite"]
        self.assertAlmostEqual(k["todo_basina_usd"], 3.00 / 2, places=4)   # I-000 hariç 3 USD / 2 biten todo
        self.assertAlmostEqual(k["ret_orani"], 1 / 3, places=4)            # 1 ret / (1 ret + 2 onay)
        self.assertAlmostEqual(k["onbellek_isabet"], 400 / 740, places=4)  # okuma / (giris+okuma+yazma)
        self.assertAlmostEqual(k["baglanmamis_emek_yuzde"], 100 * 1.25 / 4.25, places=2)

    def test_biten_todo_yoksa_none(self):
        import is_rapor
        for i in ("I-001", "I-002"):
            with open(os.path.join(self.kok, "isler", i, "todo.md"), "w", encoding="utf-8") as f:
                f.write("- [ ] a\n")
        self.assertIsNone(is_rapor.rapor(self.sd)["kalite"]["todo_basina_usd"])

    def test_karar_yoksa_ret_orani_none(self):
        import is_rapor
        for k in KARTLAR:
            jyaz(os.path.join(self.sd, "gorevler", k["id"] + ".json"), dict(k, denetimler=[]))
        self.assertIsNone(is_rapor.rapor(self.sd)["kalite"]["ret_orani"])

    def test_cli_kalite_satirlari(self):
        p = cli(self.kok)
        self.assertEqual(p.returncode, 0, p.stderr)
        alt = p.stdout.lower()
        self.assertIn("29.4", alt.replace(",", "."))  # işe bağlanmamış emek %
        for anahtar in ("todo", "ret", "önbellek", "bağlanmamış"):
            self.assertIn(anahtar, alt)


class VeriYok(unittest.TestCase):  # kriter 6
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.kok = self._t.name
        self.sd = os.path.join(self.kok, ".claude", "orkestra")
        os.makedirs(self.sd)

    def tearDown(self):
        self._t.cleanup()

    def test_bos_durum_dizini(self):
        import is_rapor
        r = is_rapor.rapor(self.sd)
        self.assertEqual(r["satirlar"], [])
        self.assertEqual(r["kalite"]["baglanmamis_emek_yuzde"], 0)
        self.assertIsNone(r["kalite"]["todo_basina_usd"])
        self.assertIsNone(r["kalite"]["ret_orani"])
        self.assertIsNone(r["kalite"]["onbellek_isabet"])
        self.assertIsInstance(is_rapor.metin(r), str)
        self.assertEqual(list(csv.reader(io.StringIO(is_rapor.csv_metni(r))))[0][0], "is")

    def test_yalniz_maliyet_var_diger_dosyalar_yok(self):
        import is_rapor
        jsonl_yaz(os.path.join(self.sd, "maliyet.jsonl"), MALIYET)
        r = is_rapor.rapor(self.sd)
        s = satir(r, "I-001")
        self.assertAlmostEqual(s["usd"], 2.0, places=6)
        self.assertEqual((s["claude_sn"], s["alt_sn"], s["kart"], s["todo_toplam"]), (0, 0, 0, 0))

    def test_bozuk_satir_ve_todo_klasoru_yok(self):
        import is_rapor
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
            f.write("bozuk{\n" + json.dumps(MALIYET[0]) + "\n")
        jyaz(os.path.join(self.sd, "isler.json"), {"sayac": 1, "isler": {
            "I-001": {"klasor": os.path.join(self.kok, "yok"), "baslik": "B", "durum": "acik"}}})
        s = satir(is_rapor.rapor(self.sd), "I-001")
        self.assertEqual(s["todo_toplam"], 0)

    def test_detay_veri_yok_none(self):
        import is_rapor
        self.assertIsNone(is_rapor.detay(self.sd, "I-001"))

    def test_cli_bos(self):
        for args in ((), ("--csv",)):
            p = cli(self.kok, *args)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertNotIn("Traceback", p.stderr)


class SaltOkuma(Temel):  # kriter 7
    def test_sir_ve_ad_ciktiya_girmez(self):
        import is_rapor
        r = is_rapor.rapor(self.sd)
        metinler = [is_rapor.metin(r), is_rapor.csv_metni(r), is_rapor.metin_detay(is_rapor.detay(self.sd, "I-001"))]
        for args in ((), ("--csv",), ("I-001",)):
            p = cli(self.kok, *args)
            self.assertEqual(p.returncode, 0, p.stderr)
            metinler.append(p.stdout + p.stderr)
        for m in metinler:
            self.assertNotIn(SIR, m)
            self.assertNotIn(AD_SOYAD, m)

    def test_modul_yazma_cagrisi_yok(self):
        yol = os.path.join(SCRIPTS, "is_rapor.py")
        with open(yol, encoding="utf-8") as f:
            kod = f.read()
        for yasak in ("kart_yaz(", "atomik_yaz(", "jsonl_ekle(", "defter_ekle("):
            self.assertNotIn(yasak, kod)
        self.assertIn("maliyet_kayitlari", kod)  # ikinci maliyet okuyucusu yazılmaz


class Yalitim(unittest.TestCase):  # kriter 8
    def test_testler_gecici_dizinde(self):
        with tempfile.TemporaryDirectory() as t:
            sd = durum_kur(t)
            self.assertTrue(os.path.abspath(sd).startswith(os.path.abspath(t)))
            import is_rapor
            is_rapor.rapor(sd)
            p = cli(t)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("I-001", p.stdout)


if __name__ == "__main__":
    unittest.main()
