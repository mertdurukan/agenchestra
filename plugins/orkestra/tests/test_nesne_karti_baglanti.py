"""ADR-0177: nesne kartı CLI komutu (P3), skill (P4) ve gölge Stop kapısı + hook bağlantısı (P5)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_nesne_karti import GECERLI  # noqa: E402

ORKESTRA = os.path.join(KOK, "scripts", "orkestra.py")
DOKUM = ("SELECT data_type FROM information_schema.columns WHERE column_name = 'is_applied'\n"
         "SELECT pg_get_functiondef('sportive.sp_transfer_applied_check'::regproc)\n")


def cli(*args, cwd=None):
    env = dict(os.environ, PYTHONUTF8="1")
    return subprocess.run([sys.executable, ORKESTRA, *args], capture_output=True, text=True, encoding="utf-8", cwd=cwd, env=env)


class KomutTesti(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.kart = os.path.join(self.d, "kart.md")
        self.dokum = os.path.join(self.d, "dokum.txt")
        self._yaz(self.kart, GECERLI)
        self._yaz(self.dokum, DOKUM)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    @staticmethod
    def _yaz(yol, metin):
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)

    def test_temiz_kart_cikis_0(self):
        r = cli("nesne-karti", "dogrula", self.kart, "--dokum", self.dokum, cwd=self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("bulgu=0", r.stdout)

    def test_bulgulu_kart_cikis_1(self):
        self._yaz(self.kart, GECERLI + "\n- Derecesiz iddia (K1)")
        r = cli("nesne-karti", "dogrula", self.kart, cwd=self.d)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("derece_yok", r.stdout)

    def test_dokumde_olmayan_kaynak_cikis_1(self):
        self._yaz(self.dokum, "alakasız\n")
        r = cli("nesne-karti", "dogrula", self.kart, "--dokum", self.dokum, cwd=self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("kaynak_okunmadi", r.stdout)

    def test_kart_dosyasi_yok_cikis_2(self):
        r = cli("nesne-karti", "dogrula", os.path.join(self.d, "yok.md"), cwd=self.d)
        self.assertEqual(r.returncode, 2)

    def test_dokum_dosyasi_yok_cikis_2(self):
        r = cli("nesne-karti", "dogrula", self.kart, "--dokum", os.path.join(self.d, "yok.txt"), cwd=self.d)
        self.assertEqual(r.returncode, 2)

    def test_json_cikti(self):
        self._yaz(self.kart, GECERLI + "\n- Derecesiz iddia (K1)")
        r = cli("nesne-karti", "dogrula", self.kart, "--json", cwd=self.d)
        d = json.loads(r.stdout)
        self.assertEqual(d["sayi"], 1)
        self.assertEqual(d["bulgular"][0]["tur"], "derece_yok")
        self.assertEqual(r.returncode, 1)


class SkillTesti(unittest.TestCase):  # S6
    def setUp(self):
        with open(os.path.join(KOK, "skills", "nesne-karti", "SKILL.md"), encoding="utf-8") as f:
            self.metin = f.read()

    def test_frontmatter_alanlari(self):
        m = re.match(r"---\n(.*?)\n---\n", self.metin, re.S)
        self.assertIsNotNone(m)
        on = m.group(1)
        self.assertRegex(on, r"(?m)^name: nesne-karti$")
        self.assertRegex(on, r"(?m)^description: ")
        self.assertRegex(on, r"(?m)^when_to_use: ")

    def test_tetik_ifadeleri_en_az_uc(self):
        m = re.search(r"when_to_use: >-\n(.*?)\n(?=\w[\w_-]*:|---)", self.metin, re.S)
        ifadeler = re.findall(r'"([^"]+)"', m.group(1))
        self.assertGreaterEqual(len(ifadeler), 3)
        self.assertIn("kaynakça göster", ifadeler)

    def test_uc_adim_basligi(self):
        basliklar = re.findall(r"(?m)^## \d\. (.+)$", self.metin)
        self.assertEqual(len(basliklar), 3)
        for anahtar in ("Kartı üret", "Ayrı denetçiye", "Doğrulayıcıyı"):
            self.assertTrue(any(anahtar in b for b in basliklar), anahtar)

    def test_komut_ve_denetci_anilir(self):
        self.assertIn("orkestra nesne-karti dogrula", self.metin)
        self.assertIn("orkestra:denetci", self.metin)

    def test_proje_adi_yok(self):
        self.assertIsNone(re.search(r"klibre|Boyner|RNV|McD|sportive", self.metin, re.I))


class GolgeTesti(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def _satirlar(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        return [json.loads(s) for s in open(yol, encoding="utf-8")] if os.path.exists(yol) else []

    def test_gecerli_kart_sessiz(self):
        import nesne_karti_golge as G
        self.assertIsNone(G.degerlendir(GECERLI, self.sd))

    def test_bulgulu_kart_nesne_karti_bulgu(self):
        import nesne_karti_golge as G
        k = G.degerlendir(GECERLI.replace("; saat=10.11.2026 14:39", ""), self.sd)
        self.assertEqual(k["kapi"], "nesne_karti_bulgu")
        self.assertEqual(k["bulgu_sayilari"], {"kaynakca_eksik": 1})

    def test_kartsiz_uc_tanimlayici_isaretlenir(self):  # S9
        import nesne_karti_golge as G
        y = "sportive.fact_transfer_report tablosu sportive.fact_transfer_suggest ile sportive.fact_transfer_actual_analysis arasında."
        k = G.degerlendir(y, self.sd)
        self.assertEqual(k["kapi"], "kartsiz_nesne_anlatimi")
        self.assertEqual(k["bulgu_sayilari"], {"tanimlayici": 3})

    def test_iki_tanimlayici_sessiz(self):  # S9
        import nesne_karti_golge as G
        self.assertIsNone(G.degerlendir("sportive.fact_transfer_report ile sportive.fact_transfer_suggest farklı.", self.sd))

    def test_dosya_adlari_ve_url_sayilmaz(self):
        import nesne_karti_golge as G
        y = "scripts/hook.py, orkestra.py, ayar.json, notlar.md ve https://example.com/a.b.c var."
        self.assertEqual(G.tanimlayicilar(y, G.NK.ayar_oku()), [])

    def test_kod_blogu_sayilmaz(self):
        import nesne_karti_golge as G
        y = "Sorgu:\n```sql\nselect a.b, c.d, e.f from x.y\n```\n"
        self.assertEqual(G.tanimlayicilar(y, G.NK.ayar_oku()), [])

    def test_sade_maddeler_derece_yok_saymaz(self):
        import nesne_karti_golge as G
        y = GECERLI + "\n- Sıradan bir madde\n"
        self.assertIsNone(G.degerlendir(y, self.sd))

    def test_kapali_ortam_degiskeni(self):
        import nesne_karti_golge as G
        y = "a.bc d.ef g.hi"
        with mock.patch.dict(os.environ, {"ORKESTRA_NESNE_KARTI": "0"}):
            self.assertIsNone(G.degerlendir(y, self.sd))

    def test_dogrulayici_hatasi_sessiz(self):
        import nesne_karti_golge as G
        with mock.patch.object(G.NK, "dogrula", side_effect=RuntimeError("x")):
            self.assertIsNone(G.degerlendir(GECERLI, self.sd))

    def test_ihlal_ayari_engellemez_mesaj_vermez(self):
        import nesne_karti_golge as G
        with open(os.path.join(self.sd, "nesne_karti.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "ihlal"}, f)
        k = G.degerlendir("sportive.aa_tablo sportive.bb_tablo sportive.cc_tablo", self.sd)
        self.assertEqual(set(k), {"kapi", "bulgu_sayilari", "ornek"})  # karar/mesaj alanı yok

    def test_bos_yanit(self):
        import nesne_karti_golge as G
        self.assertIsNone(G.degerlendir("", self.sd))
        self.assertIsNone(G.degerlendir(None, self.sd))


class HookBaglantiTesti(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def _satirlar(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        return [json.loads(s) for s in open(yol, encoding="utf-8")] if os.path.exists(yol) else []

    def test_kartsiz_anlatim_kapi_golge_yazar(self):
        import hook
        hook._nesne_karti_yanit(self.sd, "o1", {"last_assistant_message": "sportive.a_tablo sportive.b_tablo sportive.c_tablo"})
        son = self._satirlar()[-1]
        self.assertEqual((son["tur"], son["kapi"]), ("kapi_golge", "kartsiz_nesne_anlatimi"))

    def test_gecerli_kart_sessiz(self):
        import hook
        hook._nesne_karti_yanit(self.sd, "o1", {"last_assistant_message": GECERLI})
        self.assertEqual(self._satirlar(), [])

    def test_hata_sessiz(self):
        import hook
        with mock.patch("nesne_karti_golge.degerlendir", side_effect=RuntimeError("x")):
            self.assertIsNone(hook._nesne_karti_yanit(self.sd, "o1", {"last_assistant_message": "x"}))
        self.assertEqual(self._satirlar(), [])

    def test_stop_zincirinde_cagrilir(self):
        with open(os.path.join(KOK, "scripts", "hook.py"), encoding="utf-8") as f:
            kaynak = f.read()
        self.assertEqual(kaynak.count("_nesne_karti_yanit(sd, oid, inp)"), 1)
        self.assertLess(kaynak.index("_iddia_kaynak_yanit(sd, oid, inp)\n        _nesne"), kaynak.index("_nesne_karti_yanit(sd, oid, inp)\n        _cikti"))


if __name__ == "__main__":
    unittest.main()
