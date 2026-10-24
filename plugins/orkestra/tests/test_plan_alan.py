"""`orkestra plan alan` (I-224 P4, kök neden R1): P maddesi zincir alanları iş belgelerinden türer.

Fikstür, I-224 iş klasörünün (129-20261024-orkestra-denetimleri-kok-neden-analizi) küçültülmüş kopyasıdır: mevcut durum
§6 G1–G10 satırları, sözleşme S1–S7 satırları ve plan.md'nin P1–P4 blokları birebir; gövde metinleri kısaltıldı.
Gerçek klasör makinede varsa ayrıca onun kopyası üzerinde koşulur.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_SCRIPTS = os.path.join(_KOK, "scripts")
sys.path.insert(0, _SCRIPTS)
import is_kaydi as K  # noqa: E402
import is_sirasi as S  # noqa: E402
from komutlar import plan_alan as PA  # noqa: E402

GERCEK = r"C:\Mert\McD\.claude\worktrees\orkestra-denetim-k-k-neden-4992ea\129-20261024-orkestra-denetimleri-kok-neden-analizi"

IS_JSON = {"id": "I-224", "sira": "mevcut-durum-plan-todo", "sozlesme": True, "kalite": True, "gap": True,
           "uretim": True, "paralel": True, "dogrulama": "plan-iddia"}

MEVCUT = """# Orkestra denetimleri: mevcut durum

## Özet

Denetim retleri üretim noktasında önlenmiyor.

**Ölçüm saati:** 24.10.2026 16:30

## 1. İstek ya da veri hangi yoldan geçiyor

Hook, kapı ve kural katmanı.

## 2. Bugünkü davranış ve çalışan korumalar

R1–R9 ret sınıfları.

## 3. Etki haritası

- `is_kaydi.py`, `komutlar/`

## 4. Git durumu

Temiz.

## 5. Bilinmeyenler

Alt ajan payı.

## 6. Gap analizi

- **G1:** ret kaydı kök nedeni, aracı, dosyayı ve ajanı taşır → mevcut (MD §2): sabit genel kök neden, bağlam yok → ölçüm yapılamıyor, diğer müdahalelerin etkisi okunamaz.
- **G2:** şablonlar kendi kapılarından geçer → mevcut (MD §2): iki plan şablonu 4'er K-005 ihlali alıyor, ADR slotu yok → yeni plan daha ilk yazımda ret alır.
- **G3:** kural metni doğru, tek kaynaklı → mevcut (MD §2): P-035 bozuk, yüklü md eski, Özet–paragraf çakışıyor olabilir → ajan bozuk ya da eksik kuralla çalışır.
- **G4:** zincir alanları (G, P, S, Kabul, saat) CLI'dan türer → mevcut (MD §2): 3–4 yerde elle yazılıyor → tutarsızlık ve ret.
- **G5:** plan hataları ilk yazımda eksiksiz görünür → mevcut (MD §2): P alanı kapıları todo ya da onayda çıkıyor → aynı hata birkaç adım sonra, parça parça.
- **G6:** ajan durum makinesindeki yerini bilir → mevcut (MD §2): 48 ret, durum bağlamı yok, alt ajan payı bilinmiyor → sıra ve onay retleri.
- **G7:** kapı yanlış pozitif ve dolanma üretmez → mevcut (MD §2): P-016 scratchpad reddi ve dolanma, oran ölçülmüyor → güven kaybı ve kural dolanması.
- **G8:** kart kriteri açılırken ölçülebilirlik sınanır → mevcut (MD §2): yalnız boş değil kontrolü → ölçülemez kriter denetçi reddinde ortaya çıkıyor.
- **G9:** biçim ihlali yazım anında önlenir → mevcut (MD §2): 74 ret, mekanik düzeltme %2,7 → anlamsal kısaltma ret sonrası yapılıyor.
- **G10:** yapıya inmeyen davranış için etki ölçülür → mevcut (MD §2): kimlik, bütçe, konu dışı, seçim, kapanış sonradan yakalanıyor → düzeltmenin etkisi bilinmiyor.
"""

SOZLESME = """# Sözleşme

## Özet

Ret sebepleri üretim noktasında ortadan kalkar.

## Problem

Denetimler sonradan yakalıyor.

## Başarı kriterleri

- **S1:** Analiz raporu her ret sınıfı için kök neden, kanıt ve önleme basamağı (L0–L6) verir.
- **S2:** Plan her gap'i (G1–G10) bir plan maddesine bağlar ya da gerekçeyle kapsam dışı bırakır.
- **S3:** Her plan maddesi ölçülebilir kabul ölçütü taşır.
- **S4:** Her plan maddesi üretim noktasını ve neden yalnız sonradan yakalamanın yetmediğini yazar.
- **S5:** Plan, plan yazarından ayrı bir denetçiden best in class ve üretim noktası denetimini geçer.
- **S6:** Prototip ve ölçüm sonuçları olumsuz olanlar dahil raporda yer alır.
- **S7:** Onaydan önce hiçbir kod, ayar ya da kural değişikliği yapılmaz.

## Kapsam dışı

Kapı gevşetme.

## Kısıtlar

Salt okuma.
"""


def _p(no, baslik, gap, iddia, once, yazma, uretim):
    return f"""### P{no} {baslik}

**Ne:** {baslik} işi yapılır.

**Dayanak:** MD §2 R{no}

**Dokunulan yer:** MD §3 `komutlar/`

**Kabul:** test `tests/test_p{no}.py` geçer.

**Geri alma:** `git revert <commit>`.

**Önce:** {once}

**Yazma alanı:** {yazma}

**Gap:** {gap}

**İddialar:** {iddia}

**Sözleşme:** S3, S4

**Mevcut varlık:** yok — p{no} için ayrı mekanizma aranan

**Alternatifler:**

- Seçilen: kaynakta düzeltmek. Neden: hata orada doğuyor.
- Elenen: sonradan yakalamak. Neden elendi: aynı ret tekrar doğar.

**Üretim noktası:** {uretim}
"""


PLAN = ("""# Orkestra denetimleri: plan

## Özet

On bir madde, on gap.

**Sıra:**

[mevcut_durum_20261024.md](mevcut_durum_20261024.md) → bu plan → `todo.md`.

**ADR:** gerekmez — bu iş karar önerir, karar kullanıcı onayından sonra verilir.

**LLM çıktısı:** yok — değişiklikler hook, kapı, şablon ve CLI içindir.

## 1. Hedef

Ret sebepleri üretildikleri noktada ortadan kalkar.

## 2. Mevcut durumdan çıkan sonuçlar (iddialar)

""" + "".join(f"- ✅ **C{n}** iddia {n}. Dayanak: MD §2.\n" for n in range(1, 12)) + """
## 3. Kararlar

- **K1:** Önleme merdiveni ilk sorudur. Dayanak: MD §2

## 4. Plan maddeleri

"""
        + _p(1, "Ret kaydına bağlam ekle", "G1", "C1", "yok", "`plugins/orkestra/scripts/hata_kayit.py`",
             "Düzeltme: hook ret yolu (`hata_kayit.kaydet`) — ret anında bilinen bağlam kayda yazılır, sonradan tahmin edilmez.")
        + "\n" + _p(2, "Plan şablonlarını onar", "G2", "C2, C11", "yok", "`plugins/orkestra/sablonlar/plan_sirali.md`",
                    "Düzeltme: şablon (`sablonlar/plan_sirali.md`) — iskelet kendi kapısından sıfır ihlalle doğar, ilk yazımda ret yok.")
        + "\n" + _p(3, "Kural kusurlarını düzelt", "G3", "C3", "yok", "`plugins/orkestra/scripts/ork_lib.py`",
                    "Düzeltme: betik (`ork_lib.py` maskeleyicisi) — değişken adı kalıpları sır sayılmaz, yalnız değer kalıpları maskelenir.")
        + "\n" + _p(4, "Yazım anında tüm eksikleri göster", "G5, G6, G7, G8, G9, G10", "C5", "P2 — Çıktı: şablonun nihai alan sırası",
                    "`plugins/orkestra/scripts/is_sirasi.py`",
                    "Düzeltme: betik (`is_sirasi.plan_onkosulu`) — yazım anında bütün kapı eksikleri tek iletide sıralanır ve düzeltilir.")
        + """
## Gap kapsama

- **G4** Kapsam dışı: bu fikstürde P alan iskeletiyle eklenecek madde

## Best in class denetimi

- **Kök neden:** ✔ tamam
- **Üretim noktası:** ✔ tamam

**Denetçi:** af2fdb801d9d47f2f

## 5. Riskler

Yok.
""")


def _fikstur(kok, gercek=False):
    if gercek:
        for ad in ("is.json", "mevcut_durum_20261024.md", "sozlesme_20261024.md", "plan.md"):
            shutil.copy(os.path.join(GERCEK, ad), kok)
        return kok
    with open(os.path.join(kok, "is.json"), "w", encoding="utf-8") as f:
        json.dump(IS_JSON, f)
    for ad, metin in (("mevcut_durum_20261024.md", MEVCUT), ("sozlesme_20261024.md", SOZLESME), ("plan.md", PLAN)):
        with open(os.path.join(kok, ad), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
    return kok


def _eksikler(kok):
    return S.plan_eksikleri(kok) + S.sozlesme_baglanti_eksikleri(kok)


ZINCIR_SOZCUK = ("Gap", "G4", "Sözleşme", "S3", "S4", "Dayanak", "MD §", "İddialar", "Önce", "Yazma alanı", "dalga", "Dalga")
ELLE = {"Ne", "Dokunulan yer", "Kabul", "Geri alma", "Mevcut varlık", "Alternatifler", "Üretim noktası"}


class PlanAlanTesti(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="plan_alan_")
        self.addCleanup(shutil.rmtree, self.kok, True)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("ORKESTRA_")}
        _fikstur(self.kok)

    def _iskelet(self, **kw):
        varsayilan = dict(gap="G4", soz="S3,S4", iddia="C5", onceki="P2", yazma="plugins/orkestra/scripts/komutlar/plan_alan.py")
        varsayilan.update(kw)
        return PA.iskelet(self.kok, **varsayilan)

    def _cli(self, *arg):
        env = dict(self.env, PYTHONUTF8="1")
        return subprocess.run([sys.executable, os.path.join(_SCRIPTS, "orkestra.py"), "plan", "alan", self.kok, *arg],
                              capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.kok)

    # K1
    def test_k1_zincir_tutarli_ve_alanlar_ayri(self):
        s = self._iskelet(dayanak_ek="R1")
        self.assertEqual(s["tutarsizlik"], [])
        self.assertEqual(s["no"], 5)
        self.assertIn("**Gap:** G4", s["blok"])
        self.assertIn("**Sözleşme:** S3, S4", s["blok"])
        self.assertIn("**Dayanak:** MD §2 R1", s["blok"])  # G4 satırı "(MD §2)" anar
        self.assertIn("**İddialar:** C5", s["blok"])
        self.assertIn("**Önce:** P2 — Çıktı: <doldur>", s["blok"])
        self.assertIn("**Yazma alanı:** `plugins/orkestra/scripts/komutlar/plan_alan.py`", s["blok"])
        self.assertRegex(s["blok"], r"<!-- orkestra plan alan · \d\d\.\d\d\.\d{4} \d\d:\d\d -->")
        self.assertEqual(set(s["turetilen"]) & ELLE, set())
        self.assertTrue({"Gap", "Sözleşme", "Dayanak", "İddialar", "Önce", "Yazma alanı"} <= set(s["turetilen"]))
        self.assertTrue(ELLE <= set(s["elle"]))
        for alan in ELLE:
            self.assertIn(f"**{alan}:** <doldur>", s["blok"])

    def test_k1_cli_ciktisi_turetilen_ve_elle_ayri_satir(self):
        r = self._cli("--gap", "G4", "--soz", "S3,S4", "--iddia", "C5", "--onceki", "P2", "--yazma", "a.py,b.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        satirlar = r.stdout.splitlines()
        tur = next(x for x in satirlar if x.startswith("türetilen: "))
        elle = next(x for x in satirlar if x.startswith("elle kalan: "))
        self.assertIn("Gap", tur)
        self.assertNotIn("Kabul", tur)
        self.assertIn("Kabul", elle)
        self.assertNotIn("Sözleşme", elle)
        self.assertIn("zincir tutarsızlığı: 0", satirlar)

    def test_k1_alan_sirasi_sablondan(self):
        s = self._iskelet()
        sira = [a for a in K.plan_alan_sirasi(self.kok) if a != "Kapatır"]
        konum = [s["blok"].index(f"**{a}:**") for a in sira if f"**{a}:**" in s["blok"]]
        self.assertEqual(konum, sorted(konum))
        self.assertGreaterEqual(len(konum), 10)

    @unittest.skipUnless(os.path.isdir(GERCEK), "gerçek I-224 klasörü bu makinede yok")
    def test_k1_gercek_is_kopyasi(self):
        kok = tempfile.mkdtemp(prefix="plan_alan_gercek_")
        self.addCleanup(shutil.rmtree, kok, True)
        _fikstur(kok, gercek=True)
        s = PA.iskelet(kok, gap="G4", soz="S3,S4", iddia="C5", onceki="P2", yazma="x.py")
        self.assertEqual(s["tutarsizlik"], [])
        self.assertEqual(s["no"], 12)

    # K2
    def test_k2_olmayan_g_hata(self):
        with self.assertRaisesRegex(ValueError, r"G44 mevcut durum §6 içinde yok"):
            self._iskelet(gap="G44")

    def test_k2_olmayan_s_hata(self):
        with self.assertRaisesRegex(ValueError, r"S9 sözleşme"):
            self._iskelet(soz="S3,S9")

    def test_k2_olmayan_c_ve_p_hata(self):
        with self.assertRaisesRegex(ValueError, r"C99"):
            self._iskelet(iddia="C99")
        with self.assertRaisesRegex(ValueError, r"P42"):
            self._iskelet(onceki="P42")

    def test_k2_zorunlu_zincir_eksik_hata(self):
        with self.assertRaisesRegex(ValueError, r"--gap zorunlu"):
            self._iskelet(gap=None)
        with self.assertRaisesRegex(ValueError, r"--soz zorunlu"):
            self._iskelet(soz=None)

    def test_k2_cli_cikis_2_ve_dosya_degismez(self):
        once = open(os.path.join(self.kok, "plan.md"), encoding="utf-8").read()
        r = self._cli("--gap", "G44", "--soz", "S9", "--yaz")
        self.assertEqual(r.returncode, 2)
        self.assertIn("G44", r.stderr)
        self.assertIn("S9", r.stderr)
        self.assertEqual(open(os.path.join(self.kok, "plan.md"), encoding="utf-8").read(), once)

    # K3
    def test_k3_iskelet_zincir_kapilarina_takilmaz_yalniz_doldur(self):
        once = set(_eksikler(self.kok))
        soz_once = set(S.sozlesme_baglanti_eksikleri(self.kok))
        r = self._cli("--gap", "G4", "--soz", "S3,S4", "--iddia", "C5", "--onceki", "P2",
                      "--yazma", "plugins/orkestra/scripts/komutlar/plan_alan.py", "--yaz")
        self.assertEqual(r.returncode, 0, r.stderr)
        sonra = _eksikler(self.kok)
        yeni = [e for e in sonra if e not in once]
        # zincir kapıları: P-017 gap kapsama, sözleşme bağı, MD § dayanağı, paralellik (Önce / Yazma alanı)
        self.assertEqual(S.gap_kapsama_eksikleri(self.kok), [])
        # sözleşme bağı: P5 için eksik yok, fikstürün kendi S1/S2/S5–S7 eksikleri değişmez (yeni ret 0)
        self.assertEqual(set(S.sozlesme_baglanti_eksikleri(self.kok)), soz_once)
        self.assertEqual(S.paralellik_eksikleri(self.kok), [])
        for e in yeni:
            self.assertTrue(e.startswith("P5:"), e)
            alan = e.split("`**", 1)[1].split(":**", 1)[0] if "`**" in e else ""
            self.assertIn(alan, ELLE, f"zincir dışı alanda olmalı: {e}")
            self.assertFalse(any(z in e for z in ("Gap", "G4", "Sözleşme", "Dayanak", "MD §", "Önce", "Yazma alanı")), e)
        self.assertTrue(any("Üretim noktası" in e for e in yeni), yeni)  # <doldur> alanı yakalanır

    def test_k3_plan_dogrulama_iddia_bagi_tamam(self):
        import plan_dogrulama as PD
        self._cli("--gap", "G4", "--soz", "S3,S4", "--iddia", "C5", "--onceki", "P2", "--yazma", "x.py", "--yaz")
        sonuc = PD.degerlendir(os.path.join(self.kok, "plan.md"), [], False)
        self.assertFalse([e for e in sonuc["eksik"] if e.startswith("P5")], sonuc["eksik"])

    # K4
    def test_k4_yazmadan_dosya_aynen_kalir(self):
        yol = os.path.join(self.kok, "plan.md")
        once = open(yol, "rb").read()
        r = self._cli("--gap", "G4", "--soz", "S3,S4", "--iddia", "C5", "--onceki", "")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("**Önce:** yok", r.stdout)
        self.assertEqual(open(yol, "rb").read(), once)

    def test_k4_elle_plan_yeni_kirilma_yok_ve_bloklar_aynen(self):
        yol = os.path.join(self.kok, "plan.md")
        bloklar_once = S._p_bloklari(open(yol, encoding="utf-8").read())
        once = set(_eksikler(self.kok))
        K.plan_madde_ekle(self.kok, 5, self._iskelet()["blok"])
        metin = open(yol, encoding="utf-8").read()
        bloklar_sonra = S._p_bloklari(metin)
        for n, b in bloklar_once.items():
            self.assertEqual(bloklar_sonra[n].rstrip(), b.rstrip())
        self.assertTrue(once <= set(_eksikler(self.kok)))
        self.assertLess(metin.index("### P5"), metin.index("## Gap kapsama"))
        with self.assertRaisesRegex(ValueError, "P5 plan.md'de zaten var"):
            K.plan_madde_ekle(self.kok, 5, "### P5 x\n")

    def test_k4_elle_plan_zincir_denetimi_temiz(self):
        metin = open(os.path.join(self.kok, "plan.md"), encoding="utf-8").read()
        for n, blok in S._p_bloklari(metin).items():
            self.assertEqual(PA.zincir_tutarsizliklari(self.kok, blok), [], f"P{n}")


if __name__ == "__main__":
    unittest.main()
