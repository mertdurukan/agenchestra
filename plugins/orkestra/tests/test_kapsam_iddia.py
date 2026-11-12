"""ADR-0181: kısmi okuma anında kapsam notu (T4: `-k notu`) ve Stop'ta gölge kapsam ölçümü (T5: `-k golge`).
Döküm ve yanıt metinleri sentetiktir; hepsi geçici projede koşar.
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402
import kapsam_iddia as KA  # noqa: E402
from test_kanitsiz_iddia import arac, arac_sonucu, kullanici, metin  # noqa: E402

OTURUM = "kapsam12345678-oturum"
KAPSAMLI = "`select_runtime` yalnız modüle bakar."


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_kapsam_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.dosya = os.path.join(self.tmp, "uzun.py")
        with open(self.dosya, "w", encoding="utf-8") as f:
            f.write("".join(f"x{i} = {i}\n" for i in range(100)))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORKESTRA_KAPSAM_KAPISI", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def not_(self, girdi, oid=OTURUM):
        return KA.okuma_notu(self.sd, oid, "Read", girdi, self.tmp)

    def transkript(self, *kayitlar):
        p = os.path.join(self.tmp, "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for k in kayitlar:
                f.write(json.dumps(k, ensure_ascii=False) + "\n")
        return p

    def gunluk(self):
        p = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(p):
            return []
        return [json.loads(s) for s in open(p, encoding="utf-8") if s.strip()]


class OkumaNotu(_Proje):
    def test_notu_kismi_okumada_verilir_ve_kisadir(self):
        n = self.not_({"file_path": "uzun.py", "offset": 10, "limit": 20})
        self.assertIn("uzun.py kısmi okundu (10-29)", n)
        self.assertIn("yalnız/hiç/tümü", n)
        self.assertLessEqual(len(n), 220)

    def test_notu_tam_okumada_yok(self):
        self.assertEqual(self.not_({"file_path": "uzun.py"}), "")
        self.assertEqual(self.not_({"file_path": "uzun.py", "offset": 1, "limit": 2000}), "")  # dosya sığıyor

    def test_notu_ayni_dosyada_oturum_basina_bir_kez(self):
        self.assertTrue(self.not_({"file_path": "uzun.py", "offset": 10, "limit": 5}))
        self.assertEqual(self.not_({"file_path": "uzun.py", "offset": 40, "limit": 5}), "")
        self.assertTrue(self.not_({"file_path": "uzun.py", "offset": 40, "limit": 5}, oid="baska-oturum"))

    def test_notu_baska_aracta_ve_kapali_modda_yok(self):
        self.assertEqual(KA.okuma_notu(self.sd, OTURUM, "Grep", {"pattern": "x"}, self.tmp), "")
        os.environ["ORKESTRA_KAPSAM_KAPISI"] = "0"
        self.assertEqual(self.not_({"file_path": "uzun.py", "offset": 10, "limit": 5}), "")


class GolgeOlcum(_Proje):
    def calistir(self, *kayitlar):
        t = self.transkript(*kayitlar)
        hook._kapsam_iddia_yanit(self.sd, OTURUM, {"transcript_path": t})
        return [g for g in self.gunluk() if g.get("kural") == KA.KURAL]

    def test_golge_kismi_okuma_ve_kapsam_cumlesi_kaydedilir(self):
        k = self.calistir(kullanici("select_runtime neye bakar?"),
                          arac("Read", {"file_path": "r.py", "offset": 120, "limit": 30}), arac_sonucu(), metin(KAPSAMLI))
        self.assertEqual(len(k), 1)
        self.assertEqual((k[0]["mod"], k[0]["sozcuk"], k[0]["tur"]), ("golge", "yalnız", "kural_ihlal"))
        self.assertNotIn("cumle", k[0])  # yanıt metni günlüğe yazılmaz

    def test_golge_tam_okumada_yazilmaz(self):
        k = self.calistir(kullanici("soru?"), arac("Read", {"file_path": "r.py"}), arac_sonucu(), metin(KAPSAMLI))
        self.assertEqual(k, [])

    def test_golge_arama_varken_yazilmaz(self):
        for cagri in (arac("Grep", {"pattern": "provider"}), arac("Bash", {"command": "grep -n provider r.py"})):
            k = self.calistir(kullanici("soru?"), arac("Read", {"file_path": "r.py", "offset": 1, "limit": 30}),
                              arac_sonucu(), cagri, arac_sonucu(), metin(KAPSAMLI))
            self.assertEqual(k, [], cagri)

    def test_golge_kod_adi_ya_da_kapsam_sozcugu_yoksa_yazilmaz(self):
        for yanit in ("Fonksiyon yalnız modüle bakar.", "`select_runtime` modüle bakar."):
            k = self.calistir(kullanici("soru?"), arac("Read", {"file_path": "r.py", "offset": 1, "limit": 30}),
                              arac_sonucu(), metin(yanit))
            self.assertEqual(k, [], yanit)

    def test_golge_olc_gercek_dokum_sayar(self):
        t = self.transkript(kullanici("soru?"), arac("Read", {"file_path": "r.py", "offset": 1, "limit": 30}),
                            arac_sonucu(), metin(KAPSAMLI))
        s = KA.olc([t])
        self.assertEqual((s["transkript"], s["kismi_tur"], s["bulgu"]), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
