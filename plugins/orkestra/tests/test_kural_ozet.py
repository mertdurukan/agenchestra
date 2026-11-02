"""Kural özeti: her oturumda yüklenen kural dosyası kısa kalır (I-363). Tam metin JSON ve KURALLAR.md'de durur."""
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import onay  # noqa: E402

TOKEN = re.compile(r"ORKESTRA_[A-Z_]+")
MD_ENCOK_BAYT = 20000  # eklenti kuralları + yükleme satırı; proje kuralları dışında


KAYNAK = os.path.join(AD, "..", "kurallar", "eklenti_kurallari.json")


def setUpModule():
    global _env
    _env = mock.patch.dict(os.environ, {"ORKESTRA_EKLENTI_KURALLARI": KAYNAK})
    _env.start()


def tearDownModule():
    _env.stop()


def ozet_ihlalleri(liste):
    """Yüklenen etkin kurallarda eksik, uzun ya da belirteci kaybeden özetleri döner."""
    out = []
    for r in liste:
        if r.get("durum") != "etkin" or r.get("yukle") == "hook":
            continue
        o = r.get("ozet") or ""
        if not o:
            out.append((r["id"], "eksik"))
        if len(o) > onay.OZET_ENCOK:
            out.append((r["id"], "uzun"))
        out += [(r["id"], t) for t in set(TOKEN.findall(r["metin"])) if t not in o]
    return out


def etkin_yuklenen():
    return [r for r in onay._eklenti_oku() if r.get("durum") == "etkin" and r.get("yukle") != "hook"]


class KuralOzet(unittest.TestCase):
    def test_ozetler_kisa_eksiksiz_ve_belirtec_koruyor(self):
        self.assertEqual(ozet_ihlalleri(onay._eklenti_oku()), [])

    def test_uretilen_md_ozeti_yazar_tam_metni_degil(self):
        with tempfile.TemporaryDirectory() as sd:
            md = onay._kural_dosya_metni(sd)
        r = etkin_yuklenen()[0]
        self.assertIn(r["ozet"].split(".")[0], md)
        self.assertNotIn(r["metin"], md)
        self.assertIn(f"({r['id']}, ", md, "kural_farki sonekini (ID, tarih) korumalı")

    def test_ozetsiz_kural_tam_metinle_yazilir(self):
        kural = {"id": "T-001", "metin": "tam metin", "durum": "etkin", "olusturma": "2026-11-02"}
        with mock.patch.object(onay, "_eklenti_oku", return_value=[kural]), tempfile.TemporaryDirectory() as sd:
            md = onay._kural_dosya_metni(sd)
        self.assertIn("- tam metin (T-001, 2026-11-02)", md)

    def test_ihlal_vakalari_yakalanir(self):
        taban = {"id": "T-002", "metin": "m ORKESTRA_X=0 kapatır", "durum": "etkin"}
        self.assertEqual(ozet_ihlalleri([dict(taban, ozet="x" * (onay.OZET_ENCOK + 1))])[0], ("T-002", "uzun"))
        self.assertIn(("T-002", "eksik"), ozet_ihlalleri([taban]))
        self.assertIn(("T-002", "ORKESTRA_X"), ozet_ihlalleri([dict(taban, ozet="kısa")]))

    def test_uretilen_md_bayt_siniri(self):
        with tempfile.TemporaryDirectory() as sd:
            md = onay._kural_dosya_metni(sd)
        self.assertLessEqual(len(md.encode("utf-8")), MD_ENCOK_BAYT)


if __name__ == "__main__":
    unittest.main()
