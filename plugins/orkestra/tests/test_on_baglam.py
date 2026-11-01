"""I-139 P9 (bce F04/F16/F19/F21/F27/F35, ADR-0024): göreve özgü ön bağlam hook'u.
Varsayılan kapalı; açıkken var olan yolu kaynak, neden ve değişim sayısıyla listeler; olmayan yolu yazmaz."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTLER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTLER)
sys.path.insert(0, os.path.join(os.path.dirname(TESTLER), "scripts"))
import hook  # noqa: E402
import is_kaydi  # noqa: E402
import on_baglam as OB  # noqa: E402
import test_hook_baglam_boyut as TB  # noqa: E402

ISTEK = "src/modul.py dosyasındaki hesaplamayı düzeltmek istiyorum lütfen"


def _yaz(kok, goreli, metin="x = 1\n"):
    yol = os.path.join(kok, goreli)
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)


def _commit(kok, mesaj="m"):
    subprocess.run(["git", "-C", kok, "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", kok, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", mesaj],
                   check=True, capture_output=True)


class OnBaglam(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_onb_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        subprocess.run(["git", "-C", self.proje, "init", "-q"], check=True, capture_output=True)
        _yaz(self.proje, "src/modul.py")
        _commit(self.proje)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORKESTRA_ON_BAGLAM", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def uret(self, istek=ISTEK):
        return OB.uret(istek, [self.proje], self.sd)

    def test_varsayilan_kapali(self):
        self.assertFalse(OB.ayar()["acik"])
        self.assertFalse(OB.acik_mi(self.sd))
        self.assertIsNone(self.uret())

    def test_ortam_degiskeni_ac_ve_kapat(self):
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        self.assertIsNotNone(self.uret())
        os.environ["ORKESTRA_ON_BAGLAM"] = "0"
        self.assertIsNone(self.uret())

    def test_var_olan_yol_kaynak_neden_ve_degisim_sayisi(self):
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        c = self.uret()
        self.assertIn("dosya: src/modul.py", c)
        self.assertIn("kaynak: istek", c)
        self.assertIn("istekte adı geçiyor", c)
        self.assertIn("son 90 günde 1 değişiklik", c)

    def test_olmayan_yol_yazilmaz(self):
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        c = self.uret("src/yok.py dosyasındaki hesaplamayı düzeltmek istiyorum lütfen")
        self.assertTrue(c is None or "yok.py" not in c)

    def test_kisa_istek_ve_komut_atlanir(self):
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        self.assertIsNone(self.uret("src/modul.py"))
        self.assertIsNone(self.uret("/auto " + ISTEK))

    def test_deterministik_ve_sinirli(self):
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        for i in range(10):
            _yaz(self.proje, f"src/m{i}.py")
        _commit(self.proje)
        istek = "bakılacak dosyalar: " + " ".join(f"src/m{i}.py" for i in range(10)) + " ve src/modul.py"
        a, b = self.uret(istek), self.uret(istek)
        self.assertEqual(a.encode("utf-8"), b.encode("utf-8"))
        self.assertLessEqual(len(a), 1200)
        self.assertLessEqual(a.count("- dosya:"), 6)

    def test_git_yoksa_degisim_sayisi_yazilmaz(self):
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        os.rename(os.path.join(self.proje, ".git"), os.path.join(self.proje, ".git_yedek"))
        c = self.uret()
        self.assertIn("dosya: src/modul.py", c)
        self.assertNotIn("değişiklik", c)

    def test_benzer_gecmis_is_dosyasini_gosterir(self):
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        g = is_kaydi.is_ac(self.sd, "Fatura hesaplama kuralı", os.path.join(self.proje, "is1"))
        _yaz(self.proje, "is1/plan.md", "# Fatura hesaplama kuralı\n\n- `src/modul.py` içinde fatura hesaplama kuralı değişir\n")
        c = self.uret("fatura hesaplama kuralı yeniden yazılacak mı acaba bakalım")
        self.assertIn("belge: is1/plan.md · kaynak: geçmiş iş " + g["id"], c)
        self.assertIn("dosya: src/modul.py · kaynak: geçmiş iş " + g["id"], c)

    def test_olcum_sizintisi_kendi_klasoru_haric(self):
        g = is_kaydi.is_ac(self.sd, "Fatura hesaplama kuralı", os.path.join(self.proje, "is1"))
        _yaz(self.proje, "is1/plan.md", "# Fatura hesaplama kuralı\n\n- `src/modul.py` değişir\n")
        istek = "Fatura hesaplama kuralı"
        self.assertEqual(OB.yollar(istek, [self.proje], self.sd), [os.path.join(self.proje, "src", "modul.py")])
        self.assertEqual(OB.yollar(istek, [self.proje], self.sd, haric_klasor=g["klasor"]), [])
        self.assertEqual(OB.yollar(istek, [self.proje], self.sd, once_id=g["id"]), [])

    def test_hata_hook_dusurmez(self):
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        with mock.patch.object(OB, "cipalar", side_effect=RuntimeError("x")):
            self.assertIsNone(self.uret())
        with mock.patch("belge_ara.belgeler", side_effect=RuntimeError("x")):
            self.assertIn("dosya: src/modul.py", self.uret())

    def test_kimlik_adi_degersiz(self):
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        with mock.patch("kimlik.liste", return_value=[("DemoRoot", "langfuse", ["LANGFUSE_HOST", "LANGFUSE_KEY"])]):
            c = self.uret("langfuse izlerini incelemek istiyorum lütfen yardım et")
        self.assertIn("kimlik: langfuse (LANGFUSE_HOST, LANGFUSE_KEY) · kaynak: kimlik klasörü", c)
        self.assertNotIn("=", c)


class HookEntegrasyonu(unittest.TestCase):
    def setUp(self):
        self.h = TB.BaglamBoyutu("test_kriter1_tablo_her_olay_icin_onceki_sonraki")
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        _yaz(self.h.proje, "src/modul.py")
        os.environ.pop("ORKESTRA_ON_BAGLAM", None)

    def tearDown(self):
        os.environ.pop("ORKESTRA_ON_BAGLAM", None)

    def _ups(self):
        c = self.h._calistir(hook.user_prompt_submit, {"prompt": ISTEK})
        return json.loads(c)["hookSpecificOutput"]["additionalContext"]

    def test_kapaliyken_cikti_degismez_acikken_yol_listelenir(self):
        kapali = self._ups()
        self.assertNotIn("ön bağlam", kapali)
        os.environ["ORKESTRA_ON_BAGLAM"] = "0"
        self.assertEqual(self._ups(), kapali)
        os.environ["ORKESTRA_ON_BAGLAM"] = "1"
        acik = self._ups()
        self.assertIn("Orkestra ön bağlam", acik)
        self.assertIn("dosya: src/modul.py · kaynak: istek", acik)
        self.assertTrue(acik.startswith(kapali.split("\n")[0]))


if __name__ == "__main__":
    unittest.main()
