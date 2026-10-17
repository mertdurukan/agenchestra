"""Panel hedef kartları (I-047): aynı hedefe hizmet eden alanlar tek kartta toplanır, hiçbir alan kaybolmaz.

Kriterler:
  K1  Her hedef (H1–H12) için bir hedef kartı tanımı vardır: betikte `hedef: 'H<n>'`.
  K2  Birleşmeden önce gösterilen her JSON ölçü alanı birleşmeden sonra da panel betiklerinde geçer
      (yeri değişebilir, alan kaybolamaz).
  K3  Birleşmeden önce gösterilen her ölçü etiketi sayfa betiklerinde bulunur.
"""
import glob
import os
import re
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(AD), "assets")

HEDEFLER = [f"H{n}" for n in range(1, 13)]

# Hedef panosundaki beş ölçü ve hedefsiz ek ölçüler (analitik.json alanları)
OLCU_ALANLARI = [
    "ana_ajan_payi", "isci_cagrisi_kart", "onayli_kart_usd", "ret_orani", "teknik_not_kapsama",
    "ana_kirilim", "onayli_kart_toplam_usd", "isci_dagilim", "onayli_usd_dagilim",
    "ilk_gecis_onay", "onbellek_isabet", "sinif_basina",
]

# Birleşmeden önce ayrı bölüm ya da satır olarak görünen etiketler
ETIKETLER = [
    "Önlenebilir israf", "Ret nedenleri", "Onaylı iş başına maliyet", "Birim maliyet",
    "Ajan × iş türü", "Kota", "Etkin kurallar", "Kural dosyaları", "Geçmiş",
    "Hafıza okuma sınırı", "Son perspektif", "teknik not yok",
]


def _betikler():
    metin = ""
    for yol in sorted(glob.glob(os.path.join(ASSETS, "*.js")) + glob.glob(os.path.join(ASSETS, "*.html"))):
        with open(yol, encoding="utf-8") as f:
            metin += f.read() + "\n"
    return metin


class AlanKapsami(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metin = _betikler()

    def test_k1_her_hedefin_karti_var(self):
        yok = [h for h in HEDEFLER if not re.search(r"hedef:\s*['\"]%s['\"]" % h, self.metin)]
        self.assertEqual(yok, [], "hedef kartı tanımsız")

    def test_k2_olcu_alanlari_korunur(self):
        yok = [a for a in OLCU_ALANLARI if a not in self.metin]
        self.assertEqual(yok, [], "panel betiklerinde artık geçmeyen JSON ölçü alanları")

    def test_k3_olcu_etiketleri_korunur(self):
        yok = [e for e in ETIKETLER if e not in self.metin]
        self.assertEqual(yok, [], "sayfalarda artık geçmeyen ölçü etiketleri")


if __name__ == "__main__":
    unittest.main()
