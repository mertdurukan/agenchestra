"""Tarama 18 (16.10): devam ettirilen ajanın zaman ve kart token kaydı çifte toplanmaz."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ork_lib as L  # noqa: E402
import test_cekirdek as TC  # noqa: E402


class ZamanTekilleme(unittest.TestCase):
    def test_ayni_ajanin_kumulatif_satirlari_tek_sayilir(self):
        import tempfile
        sd = tempfile.mkdtemp()
        satirlar = [
            {"tur": "alt", "oturum": "s1", "agent_id": "a1", "sure_ms": 60_000},
            {"tur": "alt", "oturum": "s1", "agent_id": "a1", "sure_ms": 90_000},    # devam sonrası kümülatif
            {"tur": "alt", "oturum": "s1", "agent_id": "a2", "sure_ms": 30_000},
            {"tur": "alt", "oturum": "s1", "agent_id": "?", "sure_ms": None},
            {"tur": "alt", "oturum": "s1", "agent_id": "?", "sure_ms": None},      # kimliksiz: dokunulmaz
            {"tur": "ana", "oturum": "s1", "sure_ms": 5_000},
            {"tur": "ana", "oturum": "s1", "sure_ms": 7_000},
        ]
        with open(os.path.join(sd, "zaman.jsonl"), "w", encoding="utf-8") as f:
            for r in satirlar:
                f.write(json.dumps(r) + "\n")
        sonuc = L.zaman_kayitlari(sd)
        self.assertEqual(len(sonuc), 6)
        self.assertEqual(sum(r["sure_ms"] or 0 for r in sonuc if r["tur"] == "alt"), 120_000)   # 90 + 30
        self.assertEqual(sum(r["sure_ms"] for r in sonuc if r["tur"] == "ana"), 12_000)          # ana turlar toplanır


class DevamEdenAjan(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    hook = TC.Cekirdek.hook
    kart = TC.Cekirdek.kart
    alt_ajan_transkripti = TC.Cekirdek.alt_ajan_transkripti

    def test_ikinci_durak_karta_yalniz_farki_ekler(self):
        g = self.kart()
        tr = self.alt_ajan_transkripti("w9", g, "is")
        girdi = {"agent_id": "w9", "agent_type": "orkestra:isci-t1", "agent_transcript_path": tr}
        self.hook("SubagentStop", girdi)
        k1 = json.load(open(os.path.join(self.sd, "gorevler", g + ".json"), encoding="utf-8"))
        self.hook("SubagentStop", girdi)   # aynı (kümülatif) transkript: fark sıfır
        k2 = json.load(open(os.path.join(self.sd, "gorevler", g + ".json"), encoding="utf-8"))
        self.assertGreater(k1["token"]["giris"], 0)
        self.assertEqual(k2["token"], k1["token"])
        self.assertEqual(k2["token_ajan"]["w9"]["giris"], k1["token"]["giris"])
        self.assertEqual(len([e for e in k2["gecmis"] if e.get("olay") == "ajan-bitti"]), 2)   # olay yine yazılır


class HookArtikModelBazli(unittest.TestCase):
    def test_karisik_modelde_bir_modelin_fazlasi_ote_modelin_eksigini_kapatmaz(self):
        def satir(model, giris, kaynak):
            return {"oturum": "s1", "agent_id": None, "gorev": "-", "model": model, "giris": giris, "cikis": 0,
                    "onbellek_okuma": 0, "onbellek_yazma": 0, "kaynak": kaynak, "zaman": "2026-10-16T08:00:00+03:00",
                    "maliyet_usd": 0.0}
        rows = [satir("claude-opus-5-5", 1_000_000, "hook"), satir("claude-haiku-5-5", 100_000, "hook"),
                satir("claude-opus-5-5", 400_000, "tur"), satir("claude-haiku-5-5", 300_000, "tur")]
        art = L._hook_artigi(rows, {("s1", None)})
        self.assertEqual([(a["model"], a["giris"]) for a in art], [("claude-opus-5-5", 600_000)])   # haiku fazlası opus'tan düşmez


class MaliyetZamanSuzgeci(unittest.TestCase):
    def test_z_ve_yerel_damga_ayni_esikle_karsilastirilir(self):
        import datetime
        import tempfile
        from komutlar import maliyet as M
        sd = tempfile.mkdtemp()
        simdi = datetime.datetime.now().astimezone()
        taze_z = (simdi - datetime.timedelta(hours=1)).astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        eski_z = (simdi - datetime.timedelta(days=3)).astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        with open(os.path.join(sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
            for z in (taze_z, eski_z):
                f.write(json.dumps({"zaman": z, "oturum": "s1", "gorev": "-", "agent_id": None, "maliyet_usd": 1.0, "kaynak": "gecmis"}) + "\n")
        self.assertEqual(len(M._maliyet_kayitlari(sd, 1)), 1)


class DurumMakinesi(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    W = dict(ajan_id="w1", ajan_tipi="orkestra:isci-t1")
    D = dict(ajan_id="d1", ajan_tipi="orkestra:denetci")

    def _kart(self, g):
        return json.load(open(os.path.join(self.sd, "gorevler", g + ".json"), encoding="utf-8"))

    def _bitir(self, g):
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "eklendi", "--cikti", "docs/a.md", **self.W)
        self.assertEqual(r.returncode, 0, r.stderr)

    def _onayla(self, g):
        self._bitir(g)
        r = self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "k1 kanıtlı", **self.D)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_sinif_kucuk_harfe_cevrilir(self):
        g = self.kart("--sinif", "Belge")
        self.assertEqual(self._kart(g)["sinif"], "belge")

    def test_ikinci_denetim_yeni_is_bitti_ister(self):
        g = self.kart()
        self._bitir(g)
        r = self.cli("kart", "denetim", g, "--karar", "ret", "--neden", "kapsam-eksik", "--gerekce", "k1 kanıtsız", **self.D)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "x", ajan_id="d2", ajan_tipi="orkestra:denetci")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("yeni işçi çıktısı yok", r.stderr)
        self._bitir(g)   # işçi yeniden bitirince karar yazılır
        r = self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "k1 kanıtlı", ajan_id="d2", ajan_tipi="orkestra:denetci")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_onayli_kartta_yukseltme_ve_is_bitti_reddedilir(self):
        g = self.kart()
        self._onayla(g)
        r = self.cli("kart", "yukselt", g, "--basamak", "T3", "--neden", "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self._kart(g)["basamak"], "T1")
        self.assertEqual(self.cli("kart", "teslim", g).returncode, 0)
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "tekrar", **self.W)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(L.kart_durumu_hesapla(self._kart(g)), "teslim")
        r = self.cli("kart", "denetim", g, "--karar", "ret", "--neden", "kapsam-eksik", "--gerekce", "x", ajan_id="d3", ajan_tipi="orkestra:denetci")
        self.assertNotEqual(r.returncode, 0)

    def _plan(self, liste):
        plan = os.path.join(self.proje, "plan.json")
        json.dump(liste, open(plan, "w", encoding="utf-8"))
        return self.cli("kart", "toplu", "--json-dosya", plan)

    @staticmethod
    def _d(ref, **ek):
        return dict({"ref": ref, "soru": "Kısa test sorusu?", "baslik": ref.upper(), "sinif": "belge", "basamak": "T1",
                     "kabul_kriterleri": ["x"]}, **ek)

    def test_toplu_ileri_basvuru_cozulur(self):
        r = self._plan([self._d("b", bagimliliklar=["a"]), self._d("a")])   # b, listede sonra gelen a'ya bağlı
        self.assertEqual(r.returncode, 0, r.stderr)
        olusan = {o["baslik"]: o for o in json.loads(r.stdout)}
        self.assertEqual(olusan["B"]["bagimliliklar"], [olusan["A"]["id"]])

    def test_toplu_bilinmeyen_bagimlilik_ve_dongu_yarim_kart_birakmaz(self):
        for liste, parca in (([self._d("a", bagimliliklar=["yok"])], "yok"),
                             ([self._d("a", bagimliliklar=["b"]), self._d("b", bagimliliklar=["a"])], "döngü")):
            r = self._plan(liste)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(parca, r.stderr)
        self.assertEqual([f for f in os.listdir(os.path.join(self.sd, "gorevler")) if f.startswith("G-")], [])


class IsKaydiYedek(unittest.TestCase):
    def test_var_olan_is_json_ezilmeden_once_yedeklenir(self):
        import glob
        import tempfile
        import is_kaydi as IK
        sd = tempfile.mkdtemp()
        klasor = os.path.join(tempfile.mkdtemp(), "is1")
        os.makedirs(klasor)
        eski = os.path.join(klasor, "is.json")
        with open(eski, "w", encoding="utf-8") as f:
            f.write('{"id": "I-099", "baslik": "eski"}')
        yeni = IK.is_ac(sd, "Yeni iş", klasor)
        yedekler = glob.glob(eski + ".eski-*")
        self.assertEqual(len(yedekler), 1)
        self.assertIn("I-099", open(yedekler[0], encoding="utf-8").read())
        self.assertEqual(json.load(open(eski, encoding="utf-8"))["id"], yeni["id"])


if __name__ == "__main__":
    unittest.main()
