"""ADR-0111, P-045: Write/Edit hedefi belge türüne denkse kapı kuralı yazım anında bağlama eklenir (scripts/uretim_enjeksiyonu.py).
`python -m pytest -q plugins/orkestra/tests/test_uretim_enjeksiyonu.py`
Hepsi geçici projede koşar; eşleme ayardan gelir, testte sabitlenmez.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import uretim_enjeksiyonu as U  # noqa: E402

ISARET = "ORKESTRA ÜRETİM ANI"


def _gunluk(sd):
    yol = os.path.join(sd, "gunluk.jsonl")
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_uretim_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(self.sd)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORKESTRA_URETIM_ENJEKSIYON", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class Esleme(_Proje):
    def test_belge_turu_enjekte_edilir_ve_gunluge_yazilir(self):
        m = U.metin(os.path.join(self.tmp, "is", "plan.md"), self.sd, "o1")
        self.assertTrue(m.startswith(ISARET), m)
        k = [x for x in _gunluk(self.sd) if x.get("tur") == "uretim_enjekte"]
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["belge"], "plan")
        self.assertNotIn("Alternatifler", json.dumps(k[0]))  # içerik günlüğe yazılmaz

    def test_ilgisiz_dosyada_enjeksiyon_yok(self):
        for ad in ("hook.py", "README.md", "plan_notu.txt", "ayar.json"):
            self.assertEqual(U.metin(os.path.join(self.tmp, ad), self.sd, "o1"), "", ad)
        self.assertEqual(_gunluk(self.sd), [])

    def test_tarihli_belge_adlari_denk_gelir(self):
        for ad, tur in (("mevcut_durum_20261031.md", "mevcut_durum"), ("sozlesme_20261031.md", "sozlesme"),
                        ("calisma_ozeti_20261031.md", "calisma_ozeti"), ("todo.md", "todo")):
            self.assertEqual(U.esleme_bul(U.ayar_oku(self.sd), ad)["tur"], tur)

    def test_her_esleme_metni_sinira_sigar(self):
        ayar = U.ayar_oku(self.sd)
        for e in ayar["eslemeler"]:
            self.assertLessEqual(len(e["metin"]), ayar["metin_max"], e["tur"])

    def test_oturum_basina_sinir(self):
        yol = os.path.join(self.tmp, "plan.md")
        self.assertTrue(U.metin(yol, self.sd, "o1"))
        self.assertEqual(U.metin(yol, self.sd, "o1"), "")
        self.assertTrue(U.metin(yol, self.sd, "o2"))  # başka oturum yeniden alır

    def test_kapatma_ortam_degiskeni(self):
        os.environ["ORKESTRA_URETIM_ENJEKSIYON"] = "0"
        self.assertEqual(U.metin(os.path.join(self.tmp, "plan.md"), self.sd, "o1"), "")
        self.assertEqual(_gunluk(self.sd), [])

    def test_proje_ezmesi_kapatir_ve_degistirir(self):
        with open(os.path.join(self.sd, U.PROJE_DOSYA), "w", encoding="utf-8") as f:
            json.dump({"mod": "kapali"}, f)
        self.assertEqual(U.metin(os.path.join(self.tmp, "plan.md"), self.sd, "o1"), "")
        with open(os.path.join(self.sd, U.PROJE_DOSYA), "w", encoding="utf-8") as f:
            json.dump({"mod": "etkin", "onek": "X: ", "eslemeler": [{"tur": "ozel", "dosya": ["ozel.md"], "metin": "kural"}]}, f)
        self.assertEqual(U.metin(os.path.join(self.tmp, "ozel.md"), self.sd, "o1"), "X: kural")

    def test_hata_yolu_bos_doner(self):
        self.assertEqual(U.metin(None, self.sd, "o1"), "")
        self.assertEqual(U.metin(os.path.join(self.tmp, "plan.md"), None, "o1"), "")

    def test_kodda_belge_adi_yok(self):
        with open(os.path.join(KOK, "scripts", "uretim_enjeksiyonu.py"), encoding="utf-8") as f:
            kod = f.read()
        for ad in ("plan.md", "todo.md", "mevcut_durum", "sozlesme", "calisma_ozeti"):
            self.assertNotIn(f'"{ad}', kod)


class HookBaglantisi(unittest.TestCase):
    def test_hook_modulu_cagiriyor(self):
        with open(os.path.join(KOK, "scripts", "hook.py"), encoding="utf-8") as f:
            kod = f.read()
        self.assertIn("import uretim_enjeksiyonu as _ue", kod)
        self.assertIn("_ue.metin(", kod)


if __name__ == "__main__":
    unittest.main()
