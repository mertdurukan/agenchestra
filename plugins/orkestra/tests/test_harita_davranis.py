"""harita-kur davranış testi (ADR-0118, I-296, P4): etiketli isteklerle eşanlamlı eşleme isabeti.
Eşik: >=100 etiketli istek, isabet >= 0.80, Wilson %95 alt sınır >= 0.70.
Sınır: istekler elle yazılmış sentetik kümedir (ek/çekim varyantları dahil); gerçek kullanıcı isteğindeki isabet ayrıca ölçülmemiştir."""
import math
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import harita_istek as I  # noqa: E402

KARTLAR = {
    "skill": ("skill, yetenek, eklenti komutu", "arayüz aç/kapa listesi (**/panel.py)"),
    "panel": ("panel, web arayüzü, dashboard", "sayfa şablonu (assets/panel.html)"),
    "kural": ("kural, politika, kısıt", "kural dosyası (kurallar/kurallar.json)"),
    "hafiza": ("hafıza, bellek, memory", "hafıza dizini (hafiza/INDEX.md)"),
    "maliyet": ("maliyet, token, harcama", "maliyet defteri (defter/maliyet.jsonl)"),
    "adr": ("adr, mimari karar, karar kaydı", "adr klasörü (adr/)"),
    "hook": ("hook, kanca, olay tetikleyici", "hook tanımı (hooks/hooks.json)"),
    "todo": ("todo, yapılacak, görev listesi", "todo dosyası (todo.md)"),
    "arsiv": ("arşiv, yedek, saklama", "arşiv dizini (_arsiv/)"),
    "kimlik": ("kimlik, anahtar, credential", "kimlik klasörü (credentials/)"),
}
ISTEKLER = {  # konu -> varyantlı istekler (çekim ekleri ve cümle bağlamı dahil)
    "skill": ["yeni bir skill ekle", "skill'i güncelle", "yeni yetenek yazalım", "eklenti komutu ekleyelim", "skilleri listele",
              "bir skill daha lazım", "yeteneği kaldır", "skill adını değiştir", "yeni skill'in açıklamasını yaz", "yetenekler çalışmıyor",
              "eklenti komutunu düzelt", "skill taslağı çıkar"],
    "panel": ["panelde yeni sayfa aç", "paneli yenile", "web arayüzünde buton ekle", "dashboard'a kart koy", "paneli hızlandır",
              "arayüzde renk değiştir", "web arayüzü bozuk", "panelin üst şeridini düzelt", "dashboardu sadeleştir", "panel açılmıyor",
              "web arayüzüne filtre ekle", "paneldeki tabloyu sırala"],
    "kural": ["yeni kural ekle", "kuralı güncelle", "politikayı değiştir", "kısıtı gevşet", "kurallar çakışıyor",
              "kural metnini kısalt", "politika ekleyelim", "kuralları listele", "bir kısıt koy", "kuralın kapsamını daralt",
              "eski kuralı sil", "politikaları gözden geçir"],
    "hafiza": ["hafızaya not ekle", "hafızayı temizle", "belleği güncelle", "memory dosyasını düzelt", "hafıza dizinini yeniden yaz",
               "hafızada eski kayıt var", "belleğe kaydet", "hafıza bakımı yap", "memoryyi tara", "hafızadaki kopyaları birleştir",
               "belleği yeniden düzenle", "hafıza kaydı sil"],
    "maliyet": ["maliyeti ölç", "token harcamasını göster", "harcamayı azalt", "maliyet raporu çıkar", "tokenlar çok gidiyor",
                "maliyet defterini güncelle", "harcamaları listele", "token kullanımını düşür", "maliyeti işe göre ayır",
                "maliyet grafiği ekle", "harcama limiti koy", "tokenleri say"],
    "adr": ["adr yaz", "mimari kararı kaydet", "karar kaydı aç", "adrleri listele", "mimari karar ekle",
            "eski adrnin durumunu değiştir", "karar kaydını güncelle", "adr numarası ver", "mimari kararları gözden geçir",
            "yeni adr aç", "karar kaydı sil", "adr şablonunu düzelt"],
    "hook": ["hook ekle", "kancayı düzelt", "olay tetikleyici yaz", "hookları kapat", "hook çalışmıyor",
             "yeni hook tanımla", "kanca sırasını değiştir", "hook çıktısını kısalt", "olay tetikleyiciyi sil",
             "hooku test et", "kancalar çakışıyor", "hookun süresini uzat"],
    "todo": ["todoya madde ekle", "yapılacakları listele", "görev listesini güncelle", "todoyu temizle", "yapılacak işleri sırala",
             "todo maddesini bitir", "görev listesine kanıt ekle", "tododa eski madde var", "yapılacakları yeniden yaz",
             "todo dosyasını düzelt", "görev listesini kısalt", "todolar karışmış"],
    "arsiv": ["arşive taşı", "yedeği al", "arşivi temizle", "saklama süresini değiştir", "arşivden geri getir",
              "eski dosyaları arşivle", "yedekleri listele", "arşiv dizinini düzenle", "yedeği doğrula",
              "arşive gitmeyecek dosyaları belirle", "saklamayı kapat", "arşivleri say"],
    "kimlik": ["kimlik ekle", "anahtarı güncelle", "credential kaydı aç", "kimlikleri listele", "anahtarlar nerede duruyor",
               "kimlik klasörünü kontrol et", "anahtarı yenile", "credentialı sil", "kimlik adını değiştir",
               "anahtarlara bak", "kimlik kaydını doğrula", "credentiallar eksik"],
}
ILGISIZ = ["hava durumu nasıl", "bana bir fıkra anlat", "yarın toplantı var mı", "kahve sipariş et", "akşam yemeği önerisi ver",
           "futbol maçı kaç kaç bitti", "uçak bileti bak", "film öner", "müzik çal", "tatil planı yap"]


def wilson_alt(basari: int, n: int, z: float = 1.96) -> float:
    p = basari / n
    pay = p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return pay / (1 + z * z / n)


class Davranis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kok = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.kok, "kartlar"))
        for konu, (es, yuzey) in KARTLAR.items():
            with open(os.path.join(cls.kok, "kartlar", konu + ".md"), "w", encoding="utf-8") as f:
                f.write(f"# {konu}\n\n## Amaç\n- {konu}\n\n## Eşanlamlılar\n- {es}\n\n## Yüzeyler\n- {yuzey}\n\n## Değişmezler\n- yok\n")
        cls.kartlar = I.kartlari_oku(cls.kok)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.kok, ignore_errors=True)

    def test_etiketli_istek_sayisi_yeterli(self):
        self.assertGreaterEqual(sum(len(v) for v in ISTEKLER.values()), 100)

    def test_esanlamli_eslesme_isabeti_ve_guven_alt_siniri(self):
        toplam = basari = 0
        kacan = []
        for konu, liste in ISTEKLER.items():
            for istek in liste:
                toplam += 1
                if konu in [k["konu"] for k in I.esle(istek, self.kartlar)]:
                    basari += 1
                else:
                    kacan.append((konu, istek))
        oran, alt = basari / toplam, wilson_alt(basari, toplam)
        print(f"\nisabet {basari}/{toplam} = {oran:.3f}; Wilson %95 alt sınır = {alt:.3f}; kaçan: {kacan}")
        self.assertGreaterEqual(oran, 0.80)
        self.assertGreaterEqual(alt, 0.70)

    def test_ilgisiz_istek_eslesmez(self):
        yanlis = [i for i in ILGISIZ if I.esle(i, self.kartlar)]
        self.assertEqual(yanlis, [])


if __name__ == "__main__":
    unittest.main()
