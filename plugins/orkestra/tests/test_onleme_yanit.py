"""ADR-0120 (G4, P-045): öneri kapısı yanıt denetimi (scripts/onleme_yanit.py, hook.py _onleme_yanit). Gölge: yalnız ölçer.
`python -m pytest -q plugins/orkestra/tests/test_onleme_yanit.py`
Derlem yapaydır (mekanizma testi): POZITIF = sonradan yakalayan/alışkanlık önerisi merdivensiz, NEGATIF = öneri yok ya da
merdiven akıl yürütmesi var. Gerçek yanıtlarla doğruluk ölçümü P-028 geçiş kararının işidir (ayarda gecis_esigi).
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
import onleme_yanit as O  # noqa: E402

POZITIF = [
    "Kök neden şu. Düzeltme için bir hatırlatma ekleyelim.",
    "Çözüm: Stop hook ekle ve tur sonunda yakala.",
    "Bu hatayı sonradan yakalayan bir kontrol yeterli olur.",
    "Hook'a bir uyarı ekle, kullanıcı görsün.",
    "Bir denetçi ekleyelim, çıktıyı kontrol etsin.",
    "Bundan sonra daha dikkatli davranmak gerekir, alışkanlık olarak her seferinde bakalım.",
    "Tur sonu denetimi ekleyelim.",
    "Bir kontrol ekle ve sonuçları günlüğe yaz.",
    "Bundan sonra bu komuta dikkat edeceğim.",
    "Doğrulama ekleyelim, hata çıkarsa yakalar.",
    "Hatırlatma koy, ajan okur.",
    "UYARI EKLE yeter bence.",
    "Sorun tekrarlanıyor. Alışkanlık haline getirelim.",
    "Çıktıyı sonradan denetleyen bir betik yazalım.",
    "Hatırlatıcı yaz ve kurala işle.",
    "Şunu öneririm: tur sonu denetleyici ekle.",
]
NEGATIF = [
    "Düzeltme PreToolUse sınırında: komut yazılmadan reddedilir.",
    "Önleme merdiveninin en üst basamağı seçildi, hatırlatma ekleme gerekmedi.",
    "Mevcut kapı (genis_tarama) gölgedeydi; kipi reddet yapıyoruz.",
    "Üretim noktası: kural metni. Uyarı eklemek yetmez.",
    "Kaynakta çözülmedi çünkü kapı yok; bu yüzden sonradan yakalayan kontrol ekleyelim.",
    "Hook'u okudum, mevcut mekanizma bunu zaten kapsıyor.",
    "Testler geçti, 25 başarılı.",
    "Dosyayı güncelledim ve commit ettim.",
    "Sorun kök nedeni: yol yanlış yazılmış.",
    "Evet, doğru; ayarda kapalı.",
    "Merdivene göre bu sınıf PreToolUse ile engellenir, hatırlatma ekle demeyeceğim.",
    "Plan onaylandı, uygulamaya geçiyorum.",
    "Rapor hazır, bağlantı aşağıda.",
    "Bu bir bilgi sorusu; yanıt: iki sunucu var.",
    "Kontrol sonucu temiz, ek işlem yok.",
    "Mevcut hook yeterli, yeni mekanizma eklenmedi.",
]


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_onleme_")
        self.sd = os.path.join(self.tmp, ".claude", "orkestra")
        os.makedirs(self.sd)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ORKESTRA_ONLEME_YANIT", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]


class Derlem(_Ortak):
    def test_ayar_golge_ve_esik(self):
        a = O.ayar_oku(self.sd)
        self.assertEqual(O.mod(a), "golge")
        self.assertEqual(a["gecis_esigi"], {"tetik": 30, "yanlis_pozitif": 0})

    def test_derlem_boyutu(self):
        self.assertGreaterEqual(len(POZITIF) + len(NEGATIF), 30)

    def test_pozitifler_yakalanir(self):
        kacan = [m for m in POZITIF if not O.degerlendir(m, self.sd)]
        self.assertEqual(kacan, [])

    def test_negatifler_gecer(self):
        fazla = [m for m in NEGATIF if O.degerlendir(m, self.sd)]
        self.assertEqual(fazla, [])

    def test_alinti_oneri_cumlesi(self):
        b = O.degerlendir("Kök neden şu. Düzeltme için bir hatırlatma ekleyelim. Sonra bakarız.", self.sd)
        self.assertEqual(b["alinti"], "Düzeltme için bir hatırlatma ekleyelim.")


class Kapatma(_Ortak):
    def test_env_kapatir(self):
        os.environ["ORKESTRA_ONLEME_YANIT"] = "0"
        self.assertEqual(O.degerlendir(POZITIF[0], self.sd), {})

    def test_proje_ayari_ezer(self):
        with open(os.path.join(self.sd, O.PROJE_DOSYA), "w", encoding="utf-8") as f:
            json.dump({"mod": "kapali"}, f)
        self.assertEqual(O.degerlendir(POZITIF[0], self.sd), {})

    def test_bozuk_girdi_guvenli(self):
        self.assertEqual(O.degerlendir(None, self.sd), {})
        self.assertEqual(O.degerlendir("   ", self.sd), {})


class HookBaglantisi(_Ortak):
    def _stop_kaydi(self, metin):
        import hook
        with mock.patch.object(hook.L, "durum_dizini", lambda cwd=None, olustur=False: self.sd):
            hook._onleme_yanit(self.sd, "o1", {"last_assistant_message": metin})
        return [k for k in self.gunluk() if k.get("kural") == O.KURAL]

    def test_pozitif_kayit_dusurur(self):
        k = self._stop_kaydi(POZITIF[0])
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["tur"], "kural_ihlal")
        self.assertEqual(k[0]["mod"], "golge")

    def test_negatif_kayit_dusurmez(self):
        self.assertEqual(self._stop_kaydi(NEGATIF[0]), [])

    def test_kapali_kayit_dusurmez(self):
        os.environ["ORKESTRA_ONLEME_YANIT"] = "0"
        self.assertEqual(self._stop_kaydi(POZITIF[0]), [])


if __name__ == "__main__":
    unittest.main()
