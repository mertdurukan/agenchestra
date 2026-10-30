"""I-271: `kural_ihlal` ve `kapi_ret` satırları tetikleyen kalıbı (`eslesen`) ve metin parçasını (`cumle`) taşır.
`python -m pytest tests/test_ihlal_kanit.py -x -q`. Hepsi geçici projede koşar; gerçek gunluk.jsonl'a yazılmaz.
"""
import contextlib
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
import kapi_mod as KM  # noqa: E402

OTURUM = "ihlalkanit1234-oturum"
SAHTE_SIR = "SahteDeger12345xyz"  # gerçek sır değil; maskelemenin sınanması için


class _Proje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_ihlal_kanit_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_KIMLIK_HATIRLATMA",
                  "ORKESTRA_SECIM_HATIRLATMA"):
            os.environ.pop(k, None)
        os.environ["ORKESTRA_DURUM_YEREL"] = "1"

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ayar(self, ad, icerik):
        with open(os.path.join(self.sd, ad + ".json"), "w", encoding="utf-8") as f:
            json.dump(icerik, f)

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.isfile(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def kos(self, islev, yanit):
        girdi = {"session_id": OTURUM, "cwd": self.tmp, "last_assistant_message": yanit}
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                islev(self.sd, OTURUM, girdi)
            except SystemExit:
                pass

    def kayit(self, kural):
        k = [g for g in self.gunluk() if g.get("tur") == "kural_ihlal" and g.get("kural") == kural]
        self.assertEqual(len(k), 1, self.gunluk())
        return k[0]


class TestKuralIhlal(_Proje):  # K1, K4, K5
    def test_k1_kimlik_once_bak_eslesen_ve_cumle(self):
        self.ayar("kimlik_hatirlatma", {"mod": "golge", "yanit_kaliplari": ["erişimi bekleniyor"]})
        self.kos(hook._kimlik_kapisi_yanit, "Testler geçti. Cosmos Erişimi bekleniyor, kullanıcı eklemeli! Son.")
        k = self.kayit("kimlik_once_bak")
        self.assertEqual(k["eslesen"], "erişimi bekleniyor")
        self.assertEqual(k["cumle"], "Cosmos Erişimi bekleniyor, kullanıcı eklemeli!")  # özgün harfler korunur

    def test_k1_secim_ekrani_eslesen_ve_cumle(self):
        self.ayar("secim_ekrani_hatirlatma", {"mod": "golge", "yanit_kaliplari": ["hangisini (seçersin|istersin)"],
                                              "yanit_muaf_kaliplari": []})
        self.kos(hook._secim_kapisi_yanit, "İki yol var.\nHangisini istersin, A mı B mi?")
        k = self.kayit("secim_ekrani")
        self.assertEqual(k["eslesen"], "hangisini (seçersin|istersin)")
        self.assertEqual(k["cumle"], "Hangisini istersin, A mı B mi?")

    def test_k4_cumle_sir_maskeli(self):
        self.ayar("kimlik_hatirlatma", {"mod": "golge", "yanit_kaliplari": ["erişimi bekleniyor"]})
        self.kos(hook._kimlik_kapisi_yanit, f"Cosmos erişimi bekleniyor, password={SAHTE_SIR} denendi.")
        k = self.kayit("kimlik_once_bak")
        self.assertNotIn(SAHTE_SIR, json.dumps(k, ensure_ascii=False))
        self.assertIn("<gizli>", k["cumle"])

    def test_k4_ortak_yardimci_onekli_anahtar(self):
        d = KM.kanit_alanlari("k", "anahtar sk-" + "A1b2C3d4E5f6G7h8J9k0 kullanıldı")
        self.assertIn("<gizli-anahtar>", d["cumle"])
        self.assertNotIn("A1b2C3d4E5f6G7h8J9k0", d["cumle"])

    def test_k5_bilinmeyen_alan_yazilmaz_satir_eskisi_gibi(self):
        self.assertEqual(KM.kanit_alanlari(), {})
        self.assertEqual(KM.kanit_alanlari("", ""), {})
        self.assertEqual(hook._kalip_kaniti(["yok-kalip"], "metin", str.lower), {})
        self.ayar("kimlik_hatirlatma", {"mod": "golge", "yanit_kaliplari": ["erişimi bekleniyor"]})
        with mock.patch.object(KM, "kanit_alanlari", side_effect=RuntimeError("bozuk")):
            self.kos(hook._kimlik_kapisi_yanit, "Cosmos erişimi bekleniyor.")
        k = self.kayit("kimlik_once_bak")
        # yardımcı bozulsa da eski şema (`v`: jsonl_ekle'nin şema sürümü)
        self.assertEqual(set(k) - {"v"}, {"zaman", "oturum", "tur", "kural", "mod", "is"})


class TestKapiRet(_Proje):  # K2, K3
    def is_klasoru(self):
        k = os.path.join(self.tmp, "isler", "I-900")
        os.makedirs(k)
        return k

    def test_k2_kapi_ret_eslesen_ve_cumle(self):
        with mock.patch.object(KM, "mod", return_value="ihlal"):
            red = KM.ret_ver(self.is_klasoru(), "uretim_noktasi",
                             ["P3: `**Üretim noktası:**` alanı yok", "P4: gerekçe tekrar"])
        self.assertEqual(len(red), 2)
        r = [g for g in self.gunluk() if g.get("tur") == "kapi_ret"]
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["eslesen"], "P3")
        self.assertEqual(r[0]["cumle"], "P3: `**Üretim noktası:**` alanı yok")
        self.assertEqual(r[0]["kapi"], "uretim_noktasi")  # eski alanlar yerinde

    def test_k3_cumle_200_karakterde_kesilir(self):
        KM.ret_kaydet(self.is_klasoru(), "paralellik", "P1: " + "x" * 500)
        r = [g for g in self.gunluk() if g.get("tur") == "kapi_ret"][0]
        self.assertEqual(len(r["cumle"]), 200)
        self.assertEqual(len(r["neden"]), 300)  # eski alan değişmedi
        self.assertEqual(len(KM.kanit_alanlari("e" * 300, "y" * 900)["cumle"]), 200)
        self.assertEqual(len(KM.kanit_alanlari("e" * 300, None)["eslesen"]), 200)

    def test_k4_kapi_ret_cumle_maskeli(self):
        KM.ret_kaydet(self.is_klasoru(), "paralellik", f"P2: token={SAHTE_SIR} satırı")
        r = [g for g in self.gunluk() if g.get("tur") == "kapi_ret"][0]
        self.assertNotIn(SAHTE_SIR, r["cumle"])

    def test_k5_oneksiz_neden_eslesen_yazilmaz(self):
        KM.ret_kaydet(self.is_klasoru(), "paralellik", "önek taşımayan neden")
        r = [g for g in self.gunluk() if g.get("tur") == "kapi_ret"][0]
        self.assertNotIn("eslesen", r)
        self.assertEqual(r["cumle"], "önek taşımayan neden")


class TestRapor(_Proje):  # rapor dökümü
    def test_son_kanitlar_raporda(self):
        import ork_lib as L
        import is_rapor
        yol = os.path.join(self.sd, "gunluk.jsonl")
        L.jsonl_ekle(yol, {"zaman": "2026-10-30T10:00:00", "tur": "kural_ihlal", "kural": "eski"})  # alansız eski satır
        L.jsonl_ekle(yol, {"zaman": "2026-10-30T10:01:00", "tur": "kapi_ret", "kapi": "paralellik", "is": "I-1",
                           "neden": "P1: x", "eslesen": "P1", "cumle": "P1: x"})
        r = is_rapor.rapor(self.sd)
        self.assertEqual([x["eslesen"] for x in r["ihlal_kanit"]], ["P1"])
        m = is_rapor.metin(r)
        self.assertIn("eşleşen", m)
        self.assertIn("P1: x", m)

    def test_kanitsiz_gunlukte_bolum_yok(self):
        import is_rapor
        r = is_rapor.rapor(self.sd)
        self.assertEqual(r["ihlal_kanit"], [])
        self.assertNotIn("ihlal/ret kanıtı", is_rapor.metin(r))


if __name__ == "__main__":
    unittest.main()
