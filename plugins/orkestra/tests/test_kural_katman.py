"""Kural katmanları: proje (sd/kurallar/kurallar.json) ve plugin (eklenti deposu) kuralları.

`py -3.13 -m pytest plugins/orkestra/tests/test_kural_katman.py`
Eklenti deposu her testte geçici bir dosyaya çevrilir (ORKESTRA_EKLENTI_KURALLARI); gerçek depoya dokunulmaz.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
ORKESTRA = os.path.join(SCRIPTS, "orkestra.py")
sys.path.insert(0, SCRIPTS)
import hook  # noqa: E402
import kanit_kapisi  # noqa: E402
import onay  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402
sys.path.insert(0, AD)
import ic_kos  # noqa: E402


def yaz_json(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)


def kural(kid, metin, **ek):
    r = {"id": kid, "metin": metin, "neden": "", "durum": "etkin", "kaynak": "cli", "olusturma": "2026-10-16T10:00:00+03:00",
         "guncelleme": "2026-10-16T10:00:00+03:00", "gecmis": []}
    r.update(ek)
    return r


class Temel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.kok = self.t.name
        self.proje = os.path.join(self.kok, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.md = os.path.join(self.proje, ".claude", "rules", "orkestra_kurallari.md")
        self.eklenti_kok = os.path.join(self.kok, "eklenti")
        self.depo = os.path.join(self.eklenti_kok, "kurallar", "eklenti_kurallari.json")
        self.kurallar_md = os.path.join(self.eklenti_kok, "KURALLAR.md")
        self.env = mock.patch.dict(os.environ, {"ORKESTRA_EKLENTI_KURALLARI": self.depo})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.t.cleanup()

    def md_oku(self):
        with open(self.md, encoding="utf-8") as f:
            return f.read()

    def depo_oku(self):
        with open(self.depo, encoding="utf-8") as f:
            return json.load(f)["kurallar"]

    def proje_depo(self):
        with open(os.path.join(self.sd, "kurallar", "kurallar.json"), encoding="utf-8") as f:
            return json.load(f)

    def cli(self, *args, proje=None):
        proje = proje or self.proje
        env = dict(os.environ, PYTHONUTF8="1", CLAUDE_PROJECT_DIR=proje)
        env.pop("CLAUDE_SESSION_ID", None)
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        return ic_kos.kos([ORKESTRA, *args], cwd=proje, env=env)


class KatmanTest(Temel):
    def test_ekle_plugin_eklenti_deposuna_yazar_projeye_yazmaz(self):
        r = onay.kural_ekle(self.sd, "Her projede geçerli", "neden", katman="plugin")
        self.assertEqual((r["id"], r["katman"]), ("P-001", "plugin"))
        self.assertEqual([x["id"] for x in self.depo_oku()], ["P-001"])
        self.assertFalse(os.path.exists(os.path.join(self.sd, "kurallar", "kurallar.json")))
        self.assertIn("Her projede geçerli (P-001", self.md_oku())

    def test_ekle_varsayilan_proje(self):
        r = onay.kural_ekle(self.sd, "Yalnız bu proje", "")
        self.assertEqual((r["id"], r["katman"]), ("K-001", "proje"))
        self.assertFalse(os.path.exists(self.depo))
        self.assertEqual(self.proje_depo()["kurallar"][0]["katman"], "proje")

    def test_gecersiz_katman_reddedilir(self):
        with self.assertRaises(ValueError):
            onay.kural_ekle(self.sd, "x", "", katman="genel")
        self.assertEqual(onay.kural_ekle(self.sd, "y", "", katman="eklenti")["katman"], "plugin")  # takma ad

    def test_iki_katman_tek_dosyada_basliklarla_proje_sonra(self):
        onay.kural_ekle(self.sd, "Eklenti kuralı", "", katman="plugin")
        onay.kural_ekle(self.sd, "Proje kuralı", "")
        s = self.md_oku()
        self.assertEqual(s.splitlines()[0], "# Orkestra kuralları (panelden yönetilir)")
        self.assertIn("Çakışmada proje kuralı eklenti kuralından önce gelir.", s)
        self.assertLess(s.index("## Eklenti kuralları"), s.index("Eklenti kuralı (P-001"))
        self.assertLess(s.index("Eklenti kuralı (P-001"), s.index("## Proje kuralları"))
        self.assertLess(s.index("## Proje kuralları"), s.index("Proje kuralı (K-001"))

    def test_tek_katmanda_eski_duzen_baslıksız(self):
        onay.kural_ekle(self.sd, "Yalnız proje", "")
        self.assertNotIn("## ", self.md_oku())

    def test_proje_k_numarasi_korunan_eklenti_kimliklerini_atlar(self):
        yaz_json(self.depo, {"kurallar": [kural("K-003", "a", katman="plugin"), kural("K-006", "b", katman="plugin")]})
        self.assertEqual(onay.kural_ekle(self.sd, "yeni", "")["id"], "K-007")
        self.assertEqual(onay.kural_ekle(self.sd, "e", "", katman="plugin")["id"], "P-001")

    def test_liste_katmana_gore_suzulur(self):
        onay.kural_ekle(self.sd, "E", "", katman="plugin")
        onay.kural_ekle(self.sd, "P", "")
        self.assertEqual([r["katman"] for r in onay.kurallar(self.sd)], ["plugin", "proje"])
        self.assertEqual([r["id"] for r in onay.kurallar(self.sd, "proje")], ["K-001"])
        self.assertEqual([r["id"] for r in onay.kurallar(self.sd, "plugin")], ["P-001"])

    def test_oneri_hep_projede(self):
        r = onay.kural_oner(self.sd, "Öneri", "", "oturum-1")
        self.assertEqual((r["id"], r["katman"], r["durum"]), ("K-001", "proje", "oneri"))
        self.assertFalse(os.path.exists(self.depo))


class IdIslemTest(Temel):
    def test_duzenle_kaldir_bagla_kimlikle_katmani_bulur(self):
        onay.kural_ekle(self.sd, "Eklenti", "", katman="plugin")
        onay.kural_duzenle(self.sd, "P-001", "Eklenti v2", "n")
        self.assertEqual(self.depo_oku()[0]["metin"], "Eklenti v2")
        onay.kural_bagla(self.sd, "P-001", kontrol="kanit-satiri")
        self.assertEqual(self.depo_oku()[0]["kontrol"], "kanit-satiri")
        onay.kural_kaldir(self.sd, "P-001", "bitti")
        self.assertEqual(self.depo_oku()[0]["durum"], "kaldirildi")
        self.assertFalse(os.path.exists(self.md))
        with self.assertRaises(ValueError):
            onay.kural_duzenle(self.sd, "P-009", "x")

    def test_tasi_proje_plugin_yeni_kimlik_ve_eski_id(self):
        onay.kural_ekle(self.sd, "Taşınan", "n")
        r = onay.kural_tasi(self.sd, "K-001", "plugin")
        self.assertEqual((r["id"], r["katman"], r["eski_id"]), ("P-001", "plugin", "K-001"))
        self.assertEqual(r["gecmis"][-1]["olay"], "tasindi")
        self.assertEqual(self.proje_depo()["kurallar"], [])
        self.assertEqual([x["id"] for x in self.depo_oku()], ["P-001"])

    def test_tasi_kimligi_koru(self):
        onay.kural_ekle(self.sd, "Taşınan", "")
        r = onay.kural_tasi(self.sd, "K-001", "plugin", kimligi_koru=True)
        self.assertEqual(r["id"], "K-001")
        self.assertNotIn("eski_id", r)
        self.assertEqual(onay.kural_ekle(self.sd, "sonraki", "")["id"], "K-002")  # korunan kimlik yeniden kullanılmaz

    def test_tasi_plugin_proje_ve_ayni_katman_hatasi(self):
        onay.kural_ekle(self.sd, "E", "", katman="plugin")
        with self.assertRaises(ValueError):
            onay.kural_tasi(self.sd, "P-001", "plugin")
        r = onay.kural_tasi(self.sd, "P-001", "proje")
        self.assertEqual((r["id"], r["katman"]), ("K-001", "proje"))
        self.assertEqual(self.depo_oku(), [])

    def test_tasi_hedefte_ayni_kimlik_varsa_reddeder_ve_kural_kaybolmaz(self):
        yaz_json(self.depo, {"kurallar": [kural("K-001", "eklentide", katman="plugin")]})
        yaz_json(os.path.join(self.sd, "kurallar", "kurallar.json"), {"kurallar": [kural("K-001", "projede")]})
        with self.assertRaises(ValueError):
            onay.kural_tasi(self.sd, "K-001", "proje", kimligi_koru=True)
        self.assertEqual(len(self.depo_oku()), 1)
        self.assertEqual(len(self.proje_depo()["kurallar"]), 1)

    def test_tasi_oneri_tasinmaz(self):
        onay.kural_oner(self.sd, "Öneri", "", "cli")
        with self.assertRaises(ValueError):
            onay.kural_tasi(self.sd, "K-001", "plugin")


class KapatTest(Temel):
    def setUp(self):
        super().setUp()
        onay.kural_ekle(self.sd, "Eklenti kuralı", "", katman="plugin")
        onay.kural_ekle(self.sd, "Proje kuralı", "")

    def test_kapat_yalniz_bu_projede_dosyadan_cikarir(self):
        r = onay.kural_kapat(self.sd, "P-001", "bu projede gerekmez")
        self.assertTrue(r["devre_disi"])
        s = self.md_oku()
        self.assertNotIn("Eklenti kuralı (P-001", s)
        self.assertIn("Bu projede kapatılmış eklenti kuralları (geçerli değil): P-001 (bu projede gerekmez).", s)
        self.assertEqual(self.depo_oku()[0]["durum"], "etkin")  # eklenti deposu değişmez
        self.assertEqual([x["id"] for x in onay.etkin_kurallar(self.sd)], ["K-001"])
        self.assertTrue([x for x in onay.kurallar(self.sd) if x["id"] == "P-001"][0]["devre_disi"])

    def test_kapali_bilgi_proje_kurali_yazilinca_korunur(self):
        onay.kural_kapat(self.sd, "P-001")
        onay.kural_ekle(self.sd, "Bir kural daha", "")
        onay.kural_duzenle(self.sd, "K-001", "Proje kuralı v2")
        self.assertIn("P-001", self.proje_depo()["devre_disi"])

    def test_ac_geri_getirir(self):
        onay.kural_kapat(self.sd, "P-001")
        onay.kural_ac(self.sd, "P-001")
        self.assertIn("Eklenti kuralı (P-001", self.md_oku())
        self.assertNotIn("devre_disi", self.proje_depo())
        with self.assertRaises(ValueError):
            onay.kural_ac(self.sd, "P-001")

    def test_proje_kurali_kapatilmaz(self):
        with self.assertRaises(ValueError):
            onay.kural_kapat(self.sd, "K-001")

    def test_kapali_kuralin_kontrolu_calismaz(self):
        onay.kural_bagla(self.sd, "P-001", kontrol="kanit-satiri")
        self.assertIn("kanit-satiri", kanit_kapisi.etkin_kontroller(self.sd))
        onay.kural_kapat(self.sd, "P-001")
        self.assertNotIn("kanit-satiri", kanit_kapisi.etkin_kontroller(self.sd))


class DosyaEsitleTest(Temel):
    def test_baska_projede_eklenti_kurallari_oturumda_gelir(self):
        onay.kural_ekle(self.sd, "Her yerde", "", katman="plugin")
        baska = os.path.join(self.kok, "baska")
        sd2 = os.path.join(baska, ".claude", "orkestra")
        os.makedirs(sd2)
        self.assertTrue(onay.kural_dosyasi_esitle(sd2))
        with open(os.path.join(baska, ".claude", "rules", "orkestra_kurallari.md"), encoding="utf-8") as f:
            self.assertIn("Her yerde (P-001", f.read())
        self.assertFalse(onay.kural_dosyasi_esitle(sd2))  # içerik aynı: yazmaz

    def test_eklenti_kurali_degisince_esitle_yeniler(self):
        onay.kural_ekle(self.sd, "Eski metin", "", katman="plugin")
        yaz_json(self.depo, {"kurallar": [kural("P-001", "Yeni metin", katman="plugin")]})
        self.assertTrue(onay.kural_dosyasi_esitle(self.sd))
        self.assertIn("Yeni metin (P-001", self.md_oku())

    def test_hic_kural_yoksa_dosya_olusmaz(self):
        self.assertFalse(onay.kural_dosyasi_esitle(self.sd))
        self.assertFalse(os.path.exists(self.md))

    def test_session_start_dosyayi_yeniler(self):
        yaz_json(self.depo, {"kurallar": [kural("P-001", "Oturumda gelsin", katman="plugin")]})
        tr = os.path.join(self.kok, "tr.jsonl")
        open(tr, "w").close()
        g = {"session_id": "katman-1234567890", "cwd": self.proje, "transcript_path": tr, "source": "startup"}
        rapor = {"okunmamis_rapor": None, "zamani_geldi": False, "calisiyor": False}
        with mock.patch.object(L, "bayatlik", return_value=None), mock.patch.object(perspektif, "durum", return_value=rapor), \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                hook.session_start(g)
            except SystemExit:
                pass
        self.assertIn("Oturumda gelsin (P-001", self.md_oku())


class KurallarMdBlokTest(Temel):
    def setUp(self):
        super().setUp()
        os.makedirs(self.eklenti_kok)
        with open(self.kurallar_md, "w", encoding="utf-8", newline="") as f:
            f.write("# Orkestra kuralları\r\n\r\n## Ana ajan\r\n- el yazısı kural\r\n")

    def oku(self):
        with open(self.kurallar_md, encoding="utf-8", newline="") as f:
            return f.read()

    def test_blok_eklenir_guncellenir_kalkar_ve_crlf_korunur(self):
        onay.kural_ekle(self.sd, "Birinci", "n1", katman="plugin")
        s = self.oku()
        self.assertIn("<!-- eklenti-kurallari:basla -->", s)
        self.assertIn("- Birinci (P-001", s)
        self.assertEqual(s.count("\r\n"), s.count("\n"))  # CRLF bozulmadı
        self.assertTrue(s.startswith("# Orkestra kuralları\r\n\r\n## Ana ajan\r\n- el yazısı kural\r\n"))
        onay.kural_duzenle(self.sd, "P-001", "Birinci v2")
        s = self.oku()
        self.assertEqual(s.count("<!-- eklenti-kurallari:basla -->"), 1)
        self.assertIn("- Birinci v2 (P-001", s)
        onay.kural_kaldir(self.sd, "P-001", "x")
        s = self.oku()
        self.assertNotIn("eklenti-kurallari", s)
        self.assertEqual(s, "# Orkestra kuralları\r\n\r\n## Ana ajan\r\n- el yazısı kural\r\n")

    def test_proje_kurali_kurallar_md_ye_yazilmaz(self):
        onay.kural_ekle(self.sd, "Yalnız proje", "")
        self.assertNotIn("Yalnız proje", self.oku())

    def test_kurallar_md_yoksa_olusturulmaz(self):
        os.remove(self.kurallar_md)
        onay.kural_ekle(self.sd, "E", "", katman="plugin")
        self.assertFalse(os.path.exists(self.kurallar_md))


class CliKatmanTest(Temel):
    def test_ekle_liste_tasi_kapat_esitle(self):
        r = self.cli("kural", "ekle", "--metin", "Her projede", "--katman", "plugin")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("P-001 etkin (katman: plugin)", r.stdout)
        r = self.cli("kural", "ekle", "--metin", "Yalnız proje")
        self.assertIn("katman: proje", r.stdout)
        self.assertIn("orkestra kural tasi K-001 --katman plugin", r.stdout)  # katmanı seçtiren ipucu
        r = self.cli("kural", "liste")
        self.assertRegex(r.stdout, r"P-001\s+plugin\s+etkin")
        self.assertRegex(r.stdout, r"K-001\s+proje\s+etkin")
        r = self.cli("kural", "liste", "--katman", "plugin", "--json")
        self.assertEqual([x["id"] for x in json.loads(r.stdout)], ["P-001"])
        r = self.cli("kural", "tasi", "K-001", "--katman", "plugin", "--kimligi-koru")
        self.assertIn("K-001 plugin katmanına taşındı", r.stdout)
        r = self.cli("kural", "kapat", "K-001", "--not", "burada gerekmez")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[bu projede kapalı]", self.cli("kural", "liste").stdout)
        self.assertIn("yeniden açıldı", self.cli("kural", "ac", "K-001").stdout)
        self.assertIn("güncel", self.cli("kural", "esitle").stdout)

    def test_hata_mesajlari(self):
        self.assertNotEqual(self.cli("kural", "tasi", "K-009", "--katman", "plugin").returncode, 0)
        self.assertNotEqual(self.cli("kural", "oner", "--metin", "x", "--katman", "plugin").returncode, 0)  # öneri hep projede

    def test_ikinci_projede_eklenti_kurali_listelenir(self):
        self.cli("kural", "ekle", "--metin", "Her projede", "--katman", "plugin")
        baska = os.path.join(self.kok, "baska")
        os.makedirs(os.path.join(baska, ".claude", "orkestra"))
        self.assertRegex(self.cli("kural", "liste", proje=baska).stdout, r"P-001\s+plugin\s+etkin\s+Her projede")


class VarsayilanKonumTest(unittest.TestCase):
    def test_yol_cozumleme(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_EKLENTI_KURALLARI": ""}):
            os.environ.pop("ORKESTRA_EKLENTI_KURALLARI")
            yol = onay.eklenti_kural_yolu()
            self.assertEqual(os.path.normcase(yol), os.path.normcase(os.path.join(L.PLUGIN_ROOT, "kurallar", "eklenti_kurallari.json")))
            onceki = L.PLUGIN_ROOT
            kaynak = tempfile.mkdtemp()
            try:
                os.makedirs(os.path.join(kaynak, "plugins", "orkestra"))
                with mock.patch.object(L, "PLUGIN_ROOT", "/x/.claude/plugins/cache/p/orkestra/abc123"), \
                        mock.patch.object(L, "pazar_kaynagi", return_value=kaynak):
                    self.assertEqual(os.path.normcase(onay.eklenti_kural_yolu()),
                                     os.path.normcase(os.path.join(kaynak, "plugins", "orkestra", "kurallar", "eklenti_kurallari.json")))
                with mock.patch.object(L, "PLUGIN_ROOT", "/x/.claude/plugins/cache/p/orkestra/abc123"), \
                        mock.patch.object(L, "pazar_kaynagi", return_value=None):
                    self.assertTrue(onay.eklenti_kural_yolu().replace("\\", "/").startswith("/x/.claude/plugins/cache/"))
            finally:
                import shutil
                shutil.rmtree(kaynak, ignore_errors=True)
            self.assertEqual(L.PLUGIN_ROOT, onceki)


if __name__ == "__main__":
    unittest.main()
