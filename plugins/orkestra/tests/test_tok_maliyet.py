"""Token maliyeti düzeltmeleri (TOK-1/3/4/5/9/11) CLI ve modül testleri.

`python -m pytest -q plugins/orkestra/tests/test_tok_maliyet.py`

- Kart kilidi: teslim/onaylı/iptal ya da başka ajanda işlenen kart `isleniyor`'a geçemez (çıkış 6).
- is-bitti kapısı: işçinin is-bitti'si test + ön kontrolü koşar, geçmezse kaydetmez (çıkış 4).
- TDD'siz kod kartı: kırmızı yok, testler işçinin yazma alanında, kilit yeşilde kurulur ve onay kapısı geçer.
- Bayat açık ajan kaydı (transkripti yazılmayan) asılı sayılmaz.
- Maliyet anomali kuralları (saf denetim).
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import test_test_kapisi as TK  # noqa: E402
import maliyet_anomali as MA  # noqa: E402

ISCI = dict(ajan_id="w1", ajan_tipi="orkestra:isci-t2")
ISCI2 = dict(ajan_id="w2", ajan_tipi="orkestra:isci-t2")
DENETCI = dict(ajan_id="d1", ajan_tipi="orkestra:denetci")
YAZAR = dict(ajan_id="ty", ajan_tipi="orkestra:test-yazari")


class Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_tok_")
        r = TK.kos([TK.CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.yaz("testler/test_a.py", TK.BETIK)
        self.komut = f'"{sys.executable}" testler/test_a.py'

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def yaz(self, goreli, icerik):
        yol = os.path.join(self.proje, *goreli.split("/"))
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(icerik)

    def bayrak(self, var):
        yol = os.path.join(self.proje, "bayrak.txt")
        if var:
            with open(yol, "w") as f:
                f.write("1")
        elif os.path.exists(yol):
            os.remove(yol)

    def cli(self, *args, ajan_id=None, ajan_tipi=None):
        a = [TK.CLI] + list(args)
        if ajan_id:
            a += ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi]
        return TK.kos(a, self.proje)

    def kart(self, *ek):
        r = self.cli("kart", "yeni", "--baslik", "iş", "--basamak", "T2", "--kabul", "çalışır", "--yazma", "src/**", *ek)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def kod_karti(self, tdd=False):
        return self.kart("--sinif", "kod", "--test-komutu", self.komut, "--test-alani", "testler/*.py",
                         *(["--tdd"] if tdd else []))

    def goster(self, g):
        return json.loads(self.cli("kart", "goster", g).stdout)


class KartKilidi(Ortak):
    def test_teslim_kart_isleniyora_gecemez(self):
        g = self.kart()
        self.assertEqual(self.cli("kart", "durum", g, "isleniyor", **ISCI).returncode, 0)
        self.yaz("src/a.py", "x = 1\n")
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "b", "--cikti", "src/a.py", **ISCI)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "t", **DENETCI).returncode, 0)
        r = self.cli("kart", "durum", g, "isleniyor", **ISCI2)
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertIn("kilitli", r.stderr)

    def test_baska_ajanda_islenen_kart_ikinci_ajana_verilmez(self):
        g = self.kart()
        self.assertEqual(self.cli("kart", "durum", g, "isleniyor", **ISCI).returncode, 0)
        r = self.cli("kart", "durum", g, "isleniyor", **ISCI2)
        self.assertEqual(r.returncode, 6, r.stderr)
        # aynı ajan yeniden girebilir
        self.assertEqual(self.cli("kart", "durum", g, "isleniyor", **ISCI).returncode, 0)

    def test_ret_sonrasi_duzeltme_ajani_girebilir(self):
        g = self.kart()
        self.cli("kart", "durum", g, "isleniyor", **ISCI)
        self.yaz("src/a.py", "x = 1\n")
        self.assertEqual(self.cli("kart", "durum", g, "is-bitti", "--ozet", "b", "--cikti", "src/a.py", **ISCI).returncode, 0)
        r = self.cli("kart", "denetim", g, "--karar", "ret", "--neden", "kapsam-eksik", "--gerekce", "eksik", **DENETCI)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.cli("kart", "durum", g, "isleniyor", **ISCI2).returncode, 0)

    def test_isleniyor_ilk_girişte_on_kontrol_tabani_alir(self):
        g = self.kart()
        self.cli("kart", "durum", g, "isleniyor", **ISCI)
        sd = os.path.join(self.proje, ".claude", "orkestra")
        self.assertTrue(os.path.exists(os.path.join(sd, "gorevler", g + ".onkontrol.json")))


class IsBittiKapisi(Ortak):
    def test_kapsam_disi_cikti_is_bittiyi_reddeder(self):
        g = self.kart()
        self.cli("kart", "durum", g, "isleniyor", **ISCI)
        self.yaz("dis/b.py", "y = 2\n")
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "b", "--cikti", "dis/b.py", **ISCI)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("KAYDEDİLMEDİ", r.stderr)
        self.assertIsNone(self.goster(g).get("son_is_zamani"))

    def test_kod_kartinda_kirmizi_kod_is_bittiyi_reddeder_yesil_kabul(self):
        g = self.kod_karti()
        self.cli("kart", "durum", g, "isleniyor", **ISCI)
        self.bayrak(False)
        self.yaz("src/a.py", "x = 1\n")
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "b", "--cikti", "src/a.py", **ISCI)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.bayrak(True)
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "b", "--cikti", "src/a.py", **ISCI)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.goster(g)
        self.assertEqual(k["is_turlari"][-1]["kapi"]["test"], "yesil-gecti")
        # is-bitti'deki yeşil onay kanıtıdır: denetçi testi yeniden koşmadan onay yazabilir
        r = self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "t", **DENETCI)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ana_ajan_is_bitti_yazamaz(self):
        g = self.kart()
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "b", ajan_id="ana", ajan_tipi="ana")
        self.assertNotEqual(r.returncode, 0)


class TddsizKodKarti(Ortak):
    def test_varsayilan_tdd_kapali_ve_test_alani_yazma_alaninda(self):
        g = self.kod_karti()
        k = self.goster(g)
        self.assertFalse(k["tdd"])
        self.assertIn("testler/*.py", k["yazma_alani"])

    def test_tdd_kapali_kartta_kirmizi_yok(self):
        g = self.kod_karti()
        r = self.cli("kart", "test-kos", g, "--asama", "kirmizi", **ISCI)
        self.assertEqual(r.returncode, 2)
        self.assertIn("TDD değil", r.stderr)

    def test_yesil_kilidi_kurar_ve_yeniler(self):
        g = self.kod_karti()
        self.bayrak(True)
        self.assertEqual(self.cli("kart", "test-kos", g, "--asama", "yesil", **ISCI).returncode, 0)
        k1 = self.goster(g)["test_kilidi"]
        self.assertTrue(k1["yesilde"])
        self.yaz("testler/test_a.py", TK.BETIK + "# değişti\n")
        self.assertEqual(self.cli("kart", "test-kos", g, "--asama", "yesil", **ISCI).returncode, 0)
        self.assertNotEqual(self.goster(g)["test_kilidi"]["dosyalar"], k1["dosyalar"])

    def test_tdd_acik_kart_eski_akis(self):
        g = self.kod_karti(tdd=True)
        k = self.goster(g)
        self.assertTrue(k["tdd"])
        self.assertNotIn("testler/*.py", k["yazma_alani"])
        r = self.cli("kart", "test-kos", g, "--asama", "yesil", **ISCI)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("kilit yok", r.stderr)

    def test_test_yazari_is_bittisi_kirmiziyi_kosar(self):
        g = self.kod_karti(tdd=True)
        self.cli("kart", "durum", g, "isleniyor", **YAZAR)
        self.bayrak(True)  # kod yokken testler geçiyor: kırmızı geçmez
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "t", "--cikti", "testler/test_a.py", **YAZAR)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)


class Anomali(unittest.TestCase):
    def satir(self, gorev, surec, ajan, usd, zaman, sure_ms=60000, aid=None, model="claude-sonnet-5-5"):
        return {"kaynak": "hook", "gorev": gorev, "surec": surec, "ajan": ajan, "maliyet_usd": usd, "model": model,
                "agent_id": aid or f"{gorev}-{surec}-{zaman}", "sure_ms": sure_ms,
                "_z": datetime.datetime.fromisoformat(zaman)}

    def test_kurallar(self):
        z = "2026-10-15T09:{:02d}:00+03:00"
        s = [
            self.satir("G-1", "is", "orkestra:isci-t3", 1.5, z.format(20), sure_ms=10 * 60000, aid="a"),
            self.satir("G-1", "duzeltme", "orkestra:isci-t3", 0.3, z.format(15), sure_ms=60000, aid="b"),
            self.satir("G-1", "yukseltme", "orkestra:isci-t4", 0.4, z.format(40), aid="c"),
            self.satir("G-2", "test-kapisi", "orkestra:isci-t1", 0.01, z.format(5)),
            {"kaynak": "tur", "ajan": "ana-ajan", "maliyet_usd": 10.0, "_z": datetime.datetime.fromisoformat(z.format(1))},
        ]
        kartlar = {"G-1": {"gecmis": [{"olay": "teslim", "zaman": z.format(30)}]}}
        a = MA.denetle(s, kartlar)
        kurallar = {x["kural"] for x in a}
        self.assertTrue({"K1", "K3", "K4", "K5", "K6", "K7"} <= kurallar, a)
        k3 = next(x for x in a if x["kural"] == "K3")
        self.assertEqual(k3["kart"], "G-1")

    def test_temiz_defter(self):
        z = "2026-10-15T09:00:00+03:00"
        s = [self.satir("G-1", "is", "orkestra:isci-t2", 0.2, z), self.satir("G-1", "denetim", "orkestra:denetci", 0.1, z)]
        self.assertEqual(MA.denetle(s, {}), [])
        self.assertEqual(MA.metin([]), "Maliyet anomalisi yok.")


class BayatAjanKaydi(unittest.TestCase):
    def test_transkripti_yazilmayan_kayit_asili_sayilmaz(self):
        import ozet
        sd = tempfile.mkdtemp(prefix="ork_asili_")
        ev = tempfile.mkdtemp(prefix="ork_ev_")
        try:
            os.makedirs(os.path.join(sd, "oturumlar"))
            bas = (datetime.datetime.now().astimezone() - datetime.timedelta(hours=3)).isoformat()
            for aid in ("olu", "canli"):
                with open(os.path.join(sd, "oturumlar", f"acik_ajan_{aid}.json"), "w", encoding="utf-8") as f:
                    json.dump({"zaman": bas, "oturum": "s1", "agent_id": aid, "ajan": "orkestra:isci-t2", "gorev": "-"}, f)
                tr = os.path.join(ev, ".claude", "projects", "p", "s1", "subagents", f"agent-{aid}.jsonl")
                os.makedirs(os.path.dirname(tr), exist_ok=True)
                open(tr, "w").close()
                if aid == "olu":
                    eski = datetime.datetime.now().timestamp() - 3 * 3600
                    os.utime(tr, (eski, eski))
            eski_ev = os.environ.get("USERPROFILE"), os.environ.get("HOME")
            os.environ["USERPROFILE"] = os.environ["HOME"] = ev
            try:
                asili = ozet.asili_ajanlar(sd)
            finally:
                for ad, d in zip(("USERPROFILE", "HOME"), eski_ev):
                    if d is None:
                        os.environ.pop(ad, None)
                    else:
                        os.environ[ad] = d
            self.assertEqual([a["agent_id"] for a in asili], ["canli"])
            self.assertFalse(os.path.exists(os.path.join(sd, "oturumlar", "acik_ajan_olu.json")))
        finally:
            shutil.rmtree(sd, ignore_errors=True)
            shutil.rmtree(ev, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
