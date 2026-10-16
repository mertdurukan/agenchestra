"""Kart akışı: 'iş bitti → denetim kararı' süresi denetçi başlamayı bekleme + denetçi çalışması diye ayrılır.

SubagentStart denetçi için karta 'denetim-basladi' olayı yazar; eski kartlarda başlangıç denetçi koşu kaydından
türetilir; ikisi de yoksa iki sütun boş kalır (ortalamaya girmez), toplam denetim süresi yine görünür.
Akış özeti medyan verir; 30 dk üzeri bekleyenler sayılır; denetimsiz tekrar is-bitti çifte sayılmaz.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import analitik as A  # noqa: E402
import hook  # noqa: E402
import ork_lib as L  # noqa: E402


def z(dk):
    """2026-10-16 10:00 + dk dakika (UTC)."""
    return f"2026-10-16T{10 + dk // 60:02d}:{dk % 60:02d}:00+00:00"


def kart(gid, olaylar):
    return {"id": gid, "baslik": "t", "basamak": "isci-t2", "olusturma": z(0), "durum": "teslim",
            "gecmis": [{"zaman": z(d), "olay": o} for d, o in olaylar]}


GECMIS = [(0, "olusturuldu"), (2, "isleniyor"), (10, "is-bitti")]
KARAR = [(50, "denetim:onay"), (52, "teslim")]


class AkisAyrim(unittest.TestCase):
    def test_olaydan_ayirir(self):
        k = kart("G-001", GECMIS + [(40, "denetim-basladi")] + KARAR)
        o = A._akis([k], [])["kartlar"][0]
        self.assertEqual((o["denetim_bekleme_dk"], o["denetim_calisma_dk"], o["denetim_toplam_dk"]), (30.0, 10.0, 40.0))

    def test_kosu_kaydindan_turetir(self):
        k = kart("G-002", GECMIS + KARAR)
        kosu = {"gorev": "G-002", "ajan": "orkestra:denetci", "zaman": z(50), "sure_ms": 10 * 60000, "agent_id": "d1"}
        o = A._akis([k], [kosu])["kartlar"][0]
        self.assertEqual((o["denetim_bekleme_dk"], o["denetim_calisma_dk"]), (30.0, 10.0))

    def test_baslangic_bilinmiyorsa_bos_ve_ortalamaya_girmez(self):
        a = A._akis([kart("G-003", GECMIS + KARAR)], [])
        o = a["kartlar"][0]
        self.assertIsNone(o["denetim_bekleme_dk"])
        self.assertIsNone(o["denetim_calisma_dk"])
        self.assertEqual(o["denetim_toplam_dk"], 40.0)
        self.assertEqual(a["ozet"]["denetim_ayrilan"], 0)
        self.assertIsNone(a["ozet"]["denetim_bekleme_ort"])

    def test_ret_turlari_toplanir(self):
        k = kart("G-004", GECMIS + [(20, "denetim-basladi"), (30, "denetim:ret"), (32, "isleniyor"), (40, "is-bitti"),
                                    (45, "denetim-basladi"), (50, "denetim:onay"), (52, "teslim")])
        o = A._akis([k], [])["kartlar"][0]
        self.assertEqual((o["denetim_bekleme_dk"], o["denetim_calisma_dk"]), (15.0, 15.0))


class AkisMedyanVeEsik(unittest.TestCase):
    def test_denetimsiz_tekrar_is_bitti_cifte_sayilmaz(self):
        # 10:10, 10:20, 10:30 is-bitti; denetçi 10:40'ta başlar, karar 10:50: bekleme son is-bitti'den = 10 dk
        k = kart("G-010", [(0, "olusturuldu"), (2, "isleniyor"), (10, "is-bitti"), (20, "is-bitti"), (30, "is-bitti"),
                           (40, "denetim-basladi"), (50, "denetim:onay"), (52, "teslim")])
        o = A._akis([k], [])["kartlar"][0]
        self.assertEqual((o["denetim_bekleme_dk"], o["denetim_calisma_dk"], o["denetim_toplam_dk"]), (10.0, 10.0, 20.0))

    def kartlar(self, bekler):
        """Her kart: iş 10. dk'da biter, denetçi bekler dk sonra başlar, 5 dk sürer."""
        return [kart(f"G-{i:03d}", [(0, "olusturuldu"), (2, "isleniyor"), (10, "is-bitti"), (10 + b, "denetim-basladi"),
                                    (15 + b, "denetim:onay"), (16 + b, "teslim")]) for i, b in enumerate(bekler, 1)]

    def test_medyan_uc_degerden_etkilenmez(self):
        o = A._akis(self.kartlar([2, 3, 4, 300]), [])["ozet"]
        self.assertEqual(o["denetim_bekleme_medyan"], 3.5)
        self.assertGreater(o["denetim_bekleme_ort"], 70)

    def test_otuz_dk_ustu_sayilir_esit_sayilmaz(self):
        o = A._akis(self.kartlar([29, 30, 31, 45]), [])["ozet"]
        self.assertEqual((o["uzun_esik_dk"], o["denetim_uzun"]), (30, 2))

    def test_darbogaz_medyana_gore(self):
        # ortalamada denetçi bekleme en uzun (300 dk uç değer), medyanda iş (8 dk) en uzun
        o = A._akis(self.kartlar([2, 3, 4, 300]), [])["ozet"]
        self.assertEqual(o["darbogaz"], "is")


class DenetciBasladiOlayi(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_denetim_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        os.makedirs(os.path.join(self.sd, "gorevler"))
        self._eski = os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def tearDown(self):
        if self._eski is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = self._eski
        shutil.rmtree(self.proje, ignore_errors=True)

    def kart_yaz(self, durum_icin_is=True):
        k = {"id": "G-001", "baslik": "t", "basamak": "isci-t2", "durum": "denetimde", "denetimler": [],
             "isciler": [], "denetciler": [], "gecmis": [{"zaman": z(0), "olay": "olusturuldu"}, {"zaman": z(5), "olay": "is-bitti"}]}
        if durum_icin_is:
            k["son_is_zamani"] = z(5)
        L.kart_yaz(self.sd, k)

    def baslat(self, aid, tip):
        with open(os.path.join(self.sd, "oturumlar", f"ajan_{aid}.json"), "w", encoding="utf-8") as f:
            json.dump({"gorev": "G-001", "surec": "is", "ajan": tip}, f)
        girdi = {"session_id": "s", "cwd": self.proje, "agent_id": aid, "agent_type": tip,
                 "transcript_path": os.path.join(self.proje, "yok.jsonl")}
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            hook.subagent_start(girdi)

    def olaylar(self):
        return [g["olay"] for g in L.kart_oku(self.sd, "G-001")["gecmis"]]

    def test_denetci_baslayinca_olay_yazar_bir_kez(self):
        self.kart_yaz()
        self.baslat("d1", "orkestra:denetci")
        self.baslat("d2", "orkestra:denetci")
        self.assertEqual(self.olaylar().count("denetim-basladi"), 1)

    def test_isci_baslayinca_yazmaz(self):
        self.kart_yaz()
        self.baslat("i1", "orkestra:isci-t2")
        self.assertNotIn("denetim-basladi", self.olaylar())

    def test_denetimde_degilse_yazmaz(self):
        self.kart_yaz(durum_icin_is=False)
        k = L.kart_oku(self.sd, "G-001")
        k["durum"] = "isleniyor"
        L.kart_yaz(self.sd, k)
        self.baslat("d1", "orkestra:denetci")
        self.assertNotIn("denetim-basladi", self.olaylar())


if __name__ == "__main__":
    unittest.main()
