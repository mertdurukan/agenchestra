"""Terfi kapısı ve Yayın satırı ayrıştırma (onay.py).

`python -m pytest plugins/orkestra/tests/test_terfi.py`
Eklenti deposu geçici dosyaya çevrilir (ORKESTRA_EKLENTI_KURALLARI); gerçek eklenti_kurallari.json'a dokunulmaz.
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import onay  # noqa: E402

GERCEK_DEPO = os.path.normpath(os.path.join(AD, "..", "kurallar", "eklenti_kurallari.json"))


def _ozet(yol):
    try:
        with open(yol, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


class AyristirTest(unittest.TestCase):
    def test_var(self):
        g = ("1. **Kural adayı**\n"
             "   Yayın: kapsam=evrensel; hedef=kural\n"
             "   Eklenti metni: Her işte önce mevcut durum okunur.\n"
             "   devam eden metin\n"
             "   Neden: Hata tekrarlandı.")
        y, ok = onay.yayin_ayristir(g)
        self.assertTrue(ok)
        self.assertEqual(y, {"kapsam": "evrensel", "hedef": "kural",
                             "metin": "Her işte önce mevcut durum okunur. devam eden metin", "neden": "Hata tekrarlandı."})

    def test_yok(self):
        y, ok = onay.yayin_ayristir("1. Madde\n   Açıklama")
        self.assertFalse(ok)
        self.assertEqual(y["kapsam"], "proje")
        self.assertEqual(y["hedef"], "yok")

    def test_bozuk(self):
        for satir in ("Yayın: kapsam=herkes; hedef=kural", "Yayın: hedef=kural", "Yayın: bozuk satır", "Yayın: kapsam=evrensel; hedef=x"):
            y, ok = onay.yayin_ayristir("1. M\n" + satir)
            self.assertFalse(ok, satir)
            self.assertEqual(y["kapsam"], "proje", satir)


class EsitleKayitTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.sd = os.path.join(self.t.name, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "ruya"))

    def tearDown(self):
        self.t.cleanup()

    def _rapor(self, maddeler):
        with open(os.path.join(self.sd, "ruya", "ruya_20261016_1000.md"), "w", encoding="utf-8") as f:
            f.write("# Rapor\n\n## Önerilen değişiklikler\n\n" + maddeler + "\n")

    def test_kayda_yayin_yazilir_ve_baslikta_gorunur(self):
        self._rapor("1. **A kuralı**\n   Yayın: kapsam=evrensel; hedef=kural\n   Eklenti metni: Temiz metin.\n   Neden: Temiz neden.\n"
                    "2. **B maddesi**\n   Yayın: kapsam=bozuk\n"
                    "3. **C maddesi**\n   yalnız açıklama\n")
        onay.esitle(self.sd)
        k = {x["anahtar"].split("#")[1]: x for x in onay.liste(self.sd)}
        self.assertEqual(k["oneri-1"]["yayin"], {"kapsam": "evrensel", "hedef": "kural", "metin": "Temiz metin.", "neden": "Temiz neden."})
        self.assertIn("A kuralı", k["oneri-1"]["baslik"])
        self.assertFalse(k["oneri-1"]["baslik"].startswith("["), "başlığa kapsam öneki eklenmez")
        self.assertEqual(k["oneri-2"]["yayin"]["kapsam"], "proje")
        self.assertEqual(k["oneri-3"]["yayin"]["kapsam"], "proje")
        self.assertFalse(k["oneri-2"]["baslik"].startswith("["))
        self.assertFalse(k["oneri-3"]["baslik"].startswith("["))


class ListeKapsamTest(unittest.TestCase):
    """`orkestra onay liste` satırındaki kapsam sütunu (komutlar/onay.py)."""

    @classmethod
    def setUpClass(cls):
        from komutlar import onay as kom
        cls.kom = kom

    def satir(self, **k):
        kayit = {"id": "O-001", "durum": "bekliyor", "tur": "perspektif", "baslik": "Başlık"}
        kayit.update(k)
        return self.kom._onay_satir(kayit).split()

    def test_bicimli_evrensel(self):
        s = self.satir(yayin={"kapsam": "evrensel", "hedef": "kural", "metin": "", "neden": ""})
        self.assertEqual(s[3], "evrensel")
        self.assertEqual(s[4], "Başlık")

    def test_satirsiz_proje(self):
        self.assertEqual(self.satir()[3], "proje")

    def test_bozuk_proje(self):
        for y in ("metin", {"kapsam": "herkes"}, {}, None):
            self.assertEqual(self.satir(yayin=y)[3], "proje", y)

    def test_perspektif_disi_tire(self):
        for tur in ("kural", "skill", "karar"):
            self.assertEqual(self.satir(tur=tur, yayin={"kapsam": "evrensel"})[3], "-", tur)
            self.assertEqual(self.satir(tur=tur)[3], "-", tur)


class DenetleTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.sd = self.t.name

    def tearDown(self):
        self.t.cleanup()

    def isabet(self, metin, neden=""):
        return onay.terfi_denetle(metin, neden, self.sd)

    def test_temiz(self):
        self.assertEqual(self.isabet("Her işte önce mevcut durum okunur.", "Hata tekrarlandı."), [])

    def test_izinli_onekler(self):
        self.assertEqual(self.isabet("UTF-8, SHA-256, ISO-8601, RFC-2119, MD-5, HTTP-2 kullanılır."), [])

    def test_adr_kimligi_jira_kodu_sayilmaz(self):
        self.assertEqual(self.isabet("Karar ADR-0033 ve ADR-0034'te kayıtlı."), [])

    def test_sir(self):
        for m in ("api_key=abc123xyz", "token: abcdef", "sk-" + "a1" * 12):
            s = self.isabet(m)
            self.assertTrue(any("sır" in x for x in s), m)
            self.assertFalse(any("abc123xyz" in x or "a1a1a1" in x for x in s), "sır değeri isabet satırına yazılmamalı")

    def test_jira_kodu(self):
        s = self.isabet("PE-612 dalında", "")
        self.assertTrue(any("Jira kodu: PE-612" in x for x in s))

    def test_kart_kimligi(self):
        self.assertTrue(any("kart kimliği" in x for x in self.isabet("G-146 reddedildi")))

    def test_windows_yolu(self):
        self.assertTrue(any("Windows yolu" in x for x in self.isabet("bkz C:\\Work\\DemoRoot\\x.md")))
        self.assertTrue(any("Windows yolu" in x for x in self.isabet("bkz C:/Work/DemoRoot")))

    def test_eposta(self):
        self.assertTrue(any("e-posta" in x for x in self.isabet("yaz: ad@ornek.com")))

    def test_neden_alani_da_denetlenir(self):
        self.assertTrue(any(x.startswith("neden:") for x in self.isabet("temiz", "G-123 yüzünden")))

    def test_yasak_terim_dosyasi(self):
        with open(os.path.join(self.sd, "terfi_yasak.json"), "w", encoding="utf-8") as f:
            json.dump({"terimler": ["GizliMusteri"]}, f)
        self.assertTrue(any("yasak terim" in x for x in self.isabet("gizlimusteri için")))
        os.remove(os.path.join(self.sd, "terfi_yasak.json"))
        self.assertEqual(self.isabet("gizlimusteri için"), [])  # dosya yoksa yalnız genel kalıplar


class KapiTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.sd = os.path.join(self.t.name, "proje", ".claude", "orkestra")
        os.makedirs(self.sd)
        self.depo = os.path.join(self.t.name, "eklenti", "kurallar", "eklenti_kurallari.json")
        self.env = mock.patch.dict(os.environ, {"ORKESTRA_EKLENTI_KURALLARI": self.depo})
        self.env.start()
        self.once = _ozet(GERCEK_DEPO)

    def tearDown(self):
        self.assertEqual(_ozet(GERCEK_DEPO), self.once, "gerçek eklenti_kurallari.json değişmemeli")
        self.env.stop()
        self.t.cleanup()

    def depo_kurallari(self):
        if not os.path.exists(self.depo):
            return []
        with open(self.depo, encoding="utf-8") as f:
            return json.load(f)["kurallar"]

    def test_temiz_kural_eklentiye_yazilir(self):
        r = onay.kural_ekle(self.sd, "Her işte önce mevcut durum okunur.", "Hata tekrarlandı.", katman="plugin")
        self.assertEqual([x["id"] for x in self.depo_kurallari()], [r["id"]])

    def test_kirli_kural_eklentiye_yazilmaz(self):
        with self.assertRaises(ValueError) as c:
            onay.kural_ekle(self.sd, "G-146 kartında C:\\Work yolu", "ad@ornek.com", katman="plugin")
        self.assertIn("kart kimliği", str(c.exception))
        self.assertEqual(self.depo_kurallari(), [])

    def test_proje_katmani_degismez(self):
        r = onay.kural_ekle(self.sd, "G-146 kartı C:\\Work yolu", "PE-612")
        self.assertEqual(r["katman"], "proje")

    def test_tasi_kirli_reddedilir_temiz_gecer(self):
        kirli = onay.kural_ekle(self.sd, "G-146 için özel kural", "")
        temiz = onay.kural_ekle(self.sd, "Genel kural metni", "Genel neden")
        with self.assertRaises(ValueError):
            onay.kural_tasi(self.sd, kirli["id"], "plugin")
        self.assertEqual(self.depo_kurallari(), [])
        onay.kural_tasi(self.sd, temiz["id"], "plugin")
        self.assertEqual(len(self.depo_kurallari()), 1)
        # kirli kural proje katmanında kalmıştır
        self.assertIn(kirli["id"], [x["id"] for x in onay.kurallar(self.sd, "proje")])

    def test_duzenle_plugin_kirli_reddedilir_kural_degismez(self):
        r = onay.kural_ekle(self.sd, "Genel kural metni", "Genel neden", katman="plugin")
        with self.assertRaises(ValueError) as c:
            onay.kural_duzenle(self.sd, r["id"], "G-146 kartında özel", None)
        self.assertIn("kart kimliği", str(c.exception))
        with self.assertRaises(ValueError):
            onay.kural_duzenle(self.sd, r["id"], "Genel kural metni", "ad@ornek.com")
        k = self.depo_kurallari()[0]
        self.assertEqual((k["metin"], k["neden"]), ("Genel kural metni", "Genel neden"))

    def test_duzenle_plugin_temiz_gecer(self):
        r = onay.kural_ekle(self.sd, "Genel kural metni", "Genel neden", katman="plugin")
        onay.kural_duzenle(self.sd, r["id"], "Güncel genel metin", "Güncel neden")
        k = self.depo_kurallari()[0]
        self.assertEqual((k["metin"], k["neden"]), ("Güncel genel metin", "Güncel neden"))

    def test_duzenle_proje_katmani_degismez(self):
        r = onay.kural_ekle(self.sd, "Genel kural", "Neden")
        onay.kural_duzenle(self.sd, r["id"], "G-146 kartı C:\\Work yolu", "PE-612")
        self.assertEqual(self.depo_kurallari(), [])


if __name__ == "__main__":
    unittest.main()
