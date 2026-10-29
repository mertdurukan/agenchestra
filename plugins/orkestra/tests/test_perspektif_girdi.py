"""ADR-0094 P4: perspektif girdisinin yeni alanları (zaman, gunluk, hata, atif, trend), 64 KB tavanı, imza,
md'den türetilen başsız istem ve oturum açılışındaki "perspektif zamanı geldi" uyarısı.
python -m pytest tests/test_perspektif_girdi.py
"""
import contextlib
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif as P  # noqa: E402


def _iso(gun_once=0, dakika=0):
    return (datetime.datetime.now().astimezone() - datetime.timedelta(days=gun_once, minutes=dakika)).isoformat()


def _jsonl(yol, kayitlar):
    with open(yol, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(k, ensure_ascii=False) + "\n" for k in kayitlar))


class Ortam(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_pgirdi_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        self.hafiza = os.path.join(self.proje, "memory")
        for d in (self.sd, self.hafiza, os.path.join(self.sd, "gorevler"), os.path.join(self.sd, "perspektif")):
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(self.hafiza, "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("# Dizin\n- bir\n")
        _jsonl(os.path.join(self.sd, "zaman.jsonl"),
               [{"v": 1, "zaman": _iso(1, i), "oturum": "o1", "is": "I-1", "tur": "ana", "sure_ms": 20000 + i * 1000}
                for i in range(5)])
        _jsonl(os.path.join(self.sd, "gunluk.jsonl"),
               [{"zaman": _iso(1), "tur": "kapi_ret", "kapi": "uretim_noktasi", "neden": "alan yok", "is": "I-1"},
                {"zaman": _iso(1), "tur": "kapi_golge", "kapi": "best_in_class"},
                {"zaman": _iso(1), "tur": "kural_ihlal", "kural": "P-001", "mod": "golge"}])
        _jsonl(os.path.join(self.sd, "hata.jsonl"), [{"zaman": _iso(1), "sinif": "test", "kok": {"kaynak": "betik"}}])
        _jsonl(os.path.join(self.sd, "atif.jsonl"), [{"zaman": _iso(1), "kaynak": "denetci"}])

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def girdi(self):
        return P.girdi(self.sd, self.proje, self.hafiza)


class YeniAlanlar(Ortam):
    def test_yeni_alanlar_dolu(self):
        g = self.girdi()
        self.assertEqual(g["zaman"]["olcum"]["ana_tur"]["adet"], 5)
        self.assertIn("anomali", g["zaman"])
        self.assertEqual(g["gunluk"]["kapi_ret"], {"uretim_noktasi": 1})
        self.assertEqual(g["gunluk"]["kapi_golge"], {"best_in_class": 1})
        self.assertEqual(g["gunluk"]["kural_ihlal"], {"P-001": 1})
        for alan in ("yukseltilen_kart", "denetim_payi", "ret_nedenleri", "tekrarlayan_ret", "kullanilmayan_skill"):
            self.assertIn(alan, g["gunluk"], alan)
        self.assertIn("tur", g["gunluk"])  # mevcut tür sayımı korunur
        self.assertEqual(g["hata"]["sinif"], {"test": 1})
        self.assertEqual(g["atif"], {"denetci": 1})
        self.assertTrue(g["trend"]["kpi"])
        self.assertIn("uretim_zamani", g)

    def test_girdi_yaz_dosyasi_tavan_altinda(self):
        P.girdi_yaz(self.sd, self.proje, self.hafiza)
        yol = os.path.join(self.sd, "perspektif", "girdi.json")
        self.assertLessEqual(os.path.getsize(yol), P.GIRDI_TAVANI)
        with open(yol, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["zaman"]["olcum"]["ana_tur"]["adet"], 5)


class Tavan(unittest.TestCase):
    def test_tavan_buyuk_liste_kisalir_sayimlar_korunur(self):
        sayim = {f"kural_{i}": i for i in range(50)}
        g = {"imza": "x", "gunluk": {"kapi_ret": dict(sayim), "istekler": ["ü" * 200] * 2000},
             "hafiza": {"olu_yollar": [{"yol": "a" * 100}] * 1500, "olu_yol_sayisi": 1500}, "kisa": [1, 2]}
        r = P._kisalt(g)
        bayt = len(L.maskele(json.dumps(r, ensure_ascii=False, indent=1)).encode("utf-8"))
        self.assertLessEqual(bayt, 65536)
        self.assertEqual(r["gunluk"]["kapi_ret"], sayim)
        self.assertEqual(r["hafiza"]["olu_yol_sayisi"], 1500)
        self.assertLess(len(r["gunluk"]["istekler"]), 2000)
        self.assertEqual(r["_kisaltma"]["ozgun_uzunluk"]["gunluk.istekler"], 2000)
        self.assertEqual(r["kisa"], [1, 2])  # küçük liste dokunulmadan kalır

    def test_tavan_altinda_degismez(self):
        g = {"a": [1, 2, 3], "b": {"c": 1}}
        self.assertEqual(P._kisalt(g), {"a": [1, 2, 3], "b": {"c": 1}})


class Imza(Ortam):
    def test_imza_zaman_anomali_kumesi_degisince_degisir(self):
        once = self.girdi()["imza"]
        self.assertEqual(once, self.girdi()["imza"])  # aynı girdi → aynı imza
        klasor = os.path.join(self.proje, "is_eski")
        os.makedirs(klasor)
        with open(os.path.join(klasor, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "I-9", "guncelleme": _iso(30)}, f)
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            json.dump({"sayac": 1, "isler": {"I-9": {"klasor": klasor, "durum": "acik", "olusturma": _iso(30)}}}, f)
        sonra = self.girdi()
        self.assertTrue(any(a["kural"] == "K10" for a in sonra["zaman"]["anomali"]))
        self.assertNotEqual(once, sonra["imza"])


class Istem(unittest.TestCase):
    def test_istem_yayin(self):
        x = P.istem("H", "PR", "SD")
        self.assertGreaterEqual(x.count("Yayın:"), 1)
        self.assertTrue(x.startswith("#SUREC:perspektif\n"))
        self.assertIn("SD\\perspektif\\girdi.json", x)
        with open(P.__file__, encoding="utf-8") as f:
            self.assertNotIn("Yayın", f.read())  # sabit metin yok; md'den türetilir

    def test_istem_sablonu_geriye_uyumlu(self):
        self.assertEqual(P.ISTEM.format(hafiza="H", proje="PR", sd="SD"), P.istem("H", "PR", "SD"))


class OturumUyarisi(unittest.TestCase):
    """session_start bağlamında tek satır: eşik dolmuş + oto kapalı → var; yoksay ya da oto açık → yok."""

    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_puyari_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "perspektif"))
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        with open(os.path.join(self.sd, "perspektif", "durum.json"), "w", encoding="utf-8") as f:
            json.dump({"son_perspektif": _iso(10), "oturum_sayaci": 25, "son_rapor": None,
                       "rapor_okundu": True, "calisiyor": None}, f)
        self._env = mock.patch.dict(os.environ, {"ORKESTRA_PANEL_SERVIS": "0"}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_PERSPEKTIF", "ORKESTRA_PERSPEKTIF_OTO", "ORKESTRA_RUYA"):
            os.environ.pop(k, None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def baglam(self):
        buf = io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(L, "bayatlik", return_value=None))
            st.enter_context(mock.patch.object(hook, "_yonlendirme_ipucu", return_value=""))
            st.enter_context(mock.patch.object(hook, "_panel_ac_satiri", return_value=""))
            st.enter_context(contextlib.redirect_stdout(buf))
            try:
                hook.session_start({"session_id": "uyari-oturum-0001", "cwd": self.proje, "source": "resume"})
            except SystemExit:
                pass
        c = buf.getvalue()
        return json.loads(c)["hookSpecificOutput"]["additionalContext"] if c.strip() else ""

    def test_uyari_esik_ustu_oto_kapali_satir_var(self):
        ek = self.baglam()
        satirlar = [s for s in ek.splitlines() if "perspektif zamanı geldi" in s]
        self.assertEqual(satirlar, ["perspektif zamanı geldi (25 oturum / 10 gün): /orkestra:perspektif şimdi"])
        self.assertEqual(P.zaman_uyarisi(self.sd, False), satirlar[0])

    def test_uyari_yoksay_ya_da_oto_acik_satir_yok(self):
        os.environ["ORKESTRA_PERSPEKTIF_OTO"] = "1"
        self.assertNotIn("perspektif zamanı geldi", self.baglam())
        self.assertIsNone(P.zaman_uyarisi(self.sd, True))
        os.environ.pop("ORKESTRA_PERSPEKTIF_OTO")
        P.yoksay(self.sd)
        self.assertNotIn("perspektif zamanı geldi", self.baglam())
        self.assertIsNone(P.zaman_uyarisi(self.sd, False))


if __name__ == "__main__":
    unittest.main()
