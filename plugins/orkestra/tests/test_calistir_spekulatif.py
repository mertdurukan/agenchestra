"""workflows/calistir.js spekülatif başlatma (H2c) testleri.

Bağımlı, tdd olmayan, yazma alanı (geçişli) bağımlılıklarıyla kesişmeyen ve döngüde olmayan kartın işçisi
bağımlılığın işçi kapısı (is-bitti) geçer geçmez başlar; denetçisi ise bağımlılıklar 'onaylandi' olmadan çağrılmaz.
Bağımlılık kapıdan sonra ret/düzeltme geçirdiyse işçi turu bir kez 'yeniden' koşar.

Betik, test_calistir_paralel.py'deki sahte agent/parallel çalışma zamanıyla node'da koşturulur (zaman damgası:
her çağrının `bas`/`son` sıra numarası). node yoksa gerekçeli skip edilir.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from test_calistir_paralel import KOSUM_JS as PARALEL_KOSUM_JS, kod_karti, duz_kart

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BETIK = os.path.join(KOK, "workflows", "calistir.js")
NODE = os.environ.get("ORKESTRA_NODE") or shutil.which("node")
NODE_YOK_GEREKCE = "node bulunamadı (PATH'te yok, ORKESTRA_NODE boş): spekülatif başlatma senaryoları koşturulamadı."

_ESKI_ARGS = "{ gorevler: sen.gorevler }"
assert _ESKI_ARGS in PARALEL_KOSUM_JS
KOSUM_JS = PARALEL_KOSUM_JS.replace(_ESKI_ARGS, "{ gorevler: sen.gorevler, kart_ajan_tavani: sen.kart_ajan_tavani }")

RET = {"karar": "ret", "neden": "kapsam-eksik", "bulgular": ["kriter 1 eksik"], "duzeltme_talimati": "kriter 1 tamamla"}
ONAY = {"karar": "onay", "bulgular": []}
# Farklı ön kontrol hataları (aynı özet arka arkaya gelirse kart 'ortam' olur).
HATA_X = {"gecti": False, "ihlaller": [{"tur": "kapsam", "ayrinti": "src/x.py"}]}
HATA_Y = {"gecti": False, "ihlaller": [{"tur": "sir", "ayrinti": "anahtar sızdı"}]}


def kart(id_, alan, bag=(), **ek):
    return duz_kart(id_, yazma_alani=[alan], bagimliliklar=list(bag), **ek)


@unittest.skipUnless(NODE, NODE_YOK_GEREKCE)
class SpekulatifTaban(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_spek_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8") as f:
            f.write(KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kos(self, gorevler, **senaryo):
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(dict(senaryo, gorevler=gorevler), f, ensure_ascii=False)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
        p = subprocess.run([NODE, self.kosum, BETIK, yol], capture_output=True, env=env, timeout=90)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        c = json.loads(p.stdout.decode("utf-8"))
        self.loglar = c["loglar"]
        return {x["id"]: x for x in c["sonuc"]["sonuclar"]}, c["cagrilar"]

    @staticmethod
    def isciler(c, id_):
        return [x for x in c if x["id"] == id_ and x["phase"] == "İş"]

    @staticmethod
    def denetimler(c, id_):
        return [x for x in c if x["id"] == id_ and x["agentType"] == "orkestra:denetci"]

    def spek_logu(self, id_):
        return any(l.startswith(id_ + ": spekülatif başlatma") for l in self.loglar)


class K1KapiylaBaslar(SpekulatifTaban):
    def test_b_iscisi_a_kapisindan_sonra_a_denetimi_bitmeden_baslar(self):
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"])],
                        gecikme={"denetim": {"G-A": 200}})
        self.assertEqual((s["G-A"]["durum"], s["G-B"]["durum"]), ("onaylandi", "onaylandi"))
        a_isci = self.isciler(c, "G-A")[0]
        a_den = self.denetimler(c, "G-A")[0]
        b_isci = self.isciler(c, "G-B")[0]
        self.assertGreater(b_isci["bas"], a_isci["son"])   # A'nın kapısı geçtikten sonra
        self.assertLess(b_isci["bas"], a_den["son"])       # A'nın denetimi bitmeden
        self.assertTrue(self.spek_logu("G-B"), self.loglar)

    def test_bagimsiz_kart_spekulasyon_logu_yok(self):
        s, _ = self.kos([kart("G-A", "src/a.py"), kart("G-C", "src/c.py")])
        self.assertFalse(any("spekülatif" in l for l in self.loglar))
        self.assertEqual([x["durum"] for x in s.values()], ["onaylandi"] * 2)


class K2DenetimOnayiBekler(SpekulatifTaban):
    def test_b_denetcisi_a_onaylanmadan_cagrilmaz(self):
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"])],
                        gecikme={"denetim": {"G-A": 200}})
        a_den_son = max(x["son"] for x in self.denetimler(c, "G-A"))
        b_den = self.denetimler(c, "G-B")
        self.assertEqual(len(b_den), 1)
        self.assertGreater(b_den[0]["bas"], a_den_son)
        self.assertEqual(s["G-B"]["durum"], "onaylandi")

    def test_a_denetimde_reddedilirse_b_atlandi_denetci_hic_yok(self):
        # A T4'te: kapı geçer (B'nin işçisi başlar), iki denetim reti son basamakta reddedildi'ye götürür.
        a = kart("G-A", "src/a.py", basamak="T4")
        s, c = self.kos([a, kart("G-B", "src/b.py", ["G-A"])],
                        kartlar={"G-A": {"denetim": [RET] * 10}}, gecikme={"denetim": {"G-A": 50}})
        self.assertEqual(s["G-A"]["durum"], "reddedildi")
        self.assertEqual(s["G-B"]["durum"], "atlandi")
        self.assertIn("G-A", s["G-B"]["neden"])
        self.assertEqual(len(self.isciler(c, "G-B")), 1)   # spekülatif işçi koştu
        self.assertEqual(self.denetimler(c, "G-B"), [])    # denetçi hiç çağrılmadı

    def test_a_kapisi_hic_gecmezse_b_isci_acilmaz_atlandi(self):
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"])],
                        kartlar={"G-A": {"onkontrol": [False] * 20}})
        self.assertNotEqual(s["G-A"]["durum"], "onaylandi")  # aynı kapı hatası: 'ortam'
        self.assertEqual(s["G-B"]["durum"], "atlandi")
        self.assertIn("G-A", s["G-B"]["neden"])
        self.assertEqual([x for x in c if x["id"] == "G-B"], [])


class K3YenidenKosu(SpekulatifTaban):
    def test_a_ret_sonra_onay_b_bir_kez_yeniden_kosar_sayaca_yazilir(self):
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"])],
                        kartlar={"G-A": {"denetim": [RET, ONAY]}})
        self.assertEqual((s["G-A"]["durum"], s["G-B"]["durum"]), ("onaylandi", "onaylandi"))
        b_is = self.isciler(c, "G-B")
        self.assertEqual(len(b_is), 2)
        self.assertTrue(b_is[0]["ilk"].endswith("#SUREC:is"))
        self.assertTrue(b_is[1]["ilk"].endswith("#SUREC:yeniden"))
        self.assertIn("BAĞIMLILIK DEĞİŞTİ", b_is[1]["istem"])
        a_den_son = max(x["son"] for x in self.denetimler(c, "G-A"))
        self.assertGreater(b_is[1]["bas"], a_den_son)
        self.assertEqual(len([g for g in s["G-B"]["gecmis"] if g["surec"] == "yeniden" and g["karar"] == "-"]), 1)
        # B için 3 ajan (iş + yeniden + denetim); 'Ajan:' log satırı tüm çağrılarla tutar.
        self.assertEqual(len([x for x in c if x["id"] == "G-B"]), 3)
        self.assertIn(f"Ajan: {len(c)} ", next(l for l in self.loglar if l.startswith("Ajan:")))

    def test_yeniden_kosu_tavan_icinde_onay(self):
        # Tavan 4. A: iş, ret, düzeltme, onay = 4. B: iş (kapı geçmez), düzeltme, yeniden, denetim = 4 → onay.
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"])],
                        kartlar={"G-A": {"denetim": [RET, ONAY]}, "G-B": {"onkontrol": [False, True, True]}},
                        kart_ajan_tavani=4)
        self.assertEqual(s["G-A"]["durum"], "onaylandi")
        self.assertEqual(s["G-B"]["durum"], "onaylandi")
        self.assertEqual(len([x for x in c if x["id"] == "G-B"]), 4)

    def test_yeniden_kosu_kart_ajan_tavanina_dahil(self):
        # Tavan 4. B: iş, düzeltme, yükseltme (kapı geçer), yeniden = 4 → denetim tavanı aşar.
        # Yeniden koşu sayılmasaydı B 3 ajanla denetime girer ve onaylanırdı.
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"])],
                        kartlar={"G-A": {"denetim": [RET, ONAY]}, "G-B": {"onkontrol": [HATA_X, HATA_Y, True, True]}},
                        kart_ajan_tavani=4)
        self.assertEqual(s["G-A"]["durum"], "onaylandi")
        self.assertEqual(s["G-B"]["durum"], "tavan")
        self.assertTrue(self.isciler(c, "G-B")[-1]["ilk"].endswith("#SUREC:yeniden"))
        self.assertEqual(self.denetimler(c, "G-B"), [])

    def test_a_ilk_turda_onaylanirsa_yeniden_kosu_yok(self):
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"])])
        self.assertEqual(len(self.isciler(c, "G-B")), 1)
        self.assertNotIn("yeniden", [g["surec"] for g in s["G-B"]["gecmis"]])
        self.assertEqual(s["G-B"]["durum"], "onaylandi")

    def test_a_kapidan_once_on_kontrol_hatasi_yeniden_kosturmaz(self):
        # A'nın kapı hatası B başlamadan önce: B düzeltilmiş çıktının kapısıyla başladı → yeniden koşu yok.
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"])],
                        kartlar={"G-A": {"onkontrol": [False, True]}})
        a_is = self.isciler(c, "G-A")
        b_is = self.isciler(c, "G-B")
        self.assertEqual(len(b_is), 1)
        self.assertGreater(b_is[0]["bas"], a_is[1]["son"])
        self.assertEqual(s["G-B"]["durum"], "onaylandi")


class K4EskiYol(SpekulatifTaban):
    def test_yazma_alani_kesisen_b_onayi_bekler(self):
        s, c = self.kos([kart("G-A", "src/ortak.py"), kart("G-B", "src/ortak.py", ["G-A"])],
                        gecikme={"denetim": {"G-A": 150}})
        self.assertEqual((s["G-A"]["durum"], s["G-B"]["durum"]), ("onaylandi", "onaylandi"))
        a_den_son = max(x["son"] for x in self.denetimler(c, "G-A"))
        self.assertGreater(min(x["bas"] for x in c if x["id"] == "G-B"), a_den_son)
        self.assertFalse(self.spek_logu("G-B"))

    def test_gecisli_bagimlilikla_kesisen_alan_de_onayi_bekler(self):
        s, c = self.kos([kart("G-A", "src/ortak/**"), kart("G-B", "src/b.py", ["G-A"]),
                         kart("G-C", "src/ortak/c.py", ["G-B"])], gecikme={"denetim": {"G-A": 150}})
        self.assertFalse(self.spek_logu("G-C"))
        self.assertTrue(self.spek_logu("G-B"))
        b_den_son = max(x["son"] for x in self.denetimler(c, "G-B"))
        self.assertGreater(min(x["bas"] for x in c if x["id"] == "G-C"), b_den_son)

    def test_tdd_karti_eski_erken_test_yolu(self):
        a = duz_kart("G-A", yazma_alani=["src/a.py"])
        b = kod_karti("G-B", bagimliliklar=["G-A"])
        s, c = self.kos([a, b], gecikme={"denetim": {"G-A": 150}})
        self.assertEqual((s["G-A"]["durum"], s["G-B"]["durum"]), ("onaylandi", "onaylandi"))
        a_den_son = max(x["son"] for x in self.denetimler(c, "G-A"))
        yazar = [x for x in c if x["id"] == "G-B" and x["agentType"] == "orkestra:test-yazari"][0]
        self.assertLess(yazar["bas"], a_den_son)                        # test yazarı erken
        self.assertGreater(self.isciler(c, "G-B")[0]["bas"], a_den_son)  # işçi onaydan sonra
        self.assertFalse(self.spek_logu("G-B"))

    def test_dongudeki_kart_spekulasyon_yok(self):
        a = kart("G-A", "src/a.py", ["G-B"])
        b = kart("G-B", "src/b.py", ["G-A"])
        s, c = self.kos([a, b])  # asılı kalırsa subprocess timeout'u yakalar
        self.assertNotIn("onaylandi", [x["durum"] for x in s.values()])
        self.assertEqual([x for x in c if x["phase"] == "İş"], [])
        self.assertFalse(any("spekülatif" in l for l in self.loglar))


class K5UcluZincir(SpekulatifTaban):
    def test_c_b_kapisiyla_baslar_denetimi_b_ve_a_onayindan_sonra(self):
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"]), kart("G-C", "src/c.py", ["G-B"])],
                        gecikme={"denetim": {"G-A": 300, "G-B": 100}})
        self.assertEqual([s[i]["durum"] for i in ("G-A", "G-B", "G-C")], ["onaylandi"] * 3)
        b_is = self.isciler(c, "G-B")[0]
        c_is = self.isciler(c, "G-C")[0]
        a_den_son = max(x["son"] for x in self.denetimler(c, "G-A"))
        b_den_son = max(x["son"] for x in self.denetimler(c, "G-B"))
        self.assertGreater(c_is["bas"], b_is["son"])   # B'nin kapısıyla
        self.assertLess(c_is["bas"], a_den_son)        # A onaylanmadan bile
        c_den = self.denetimler(c, "G-C")[0]
        self.assertGreater(c_den["bas"], b_den_son)
        self.assertGreater(c_den["bas"], a_den_son)
        self.assertEqual(len(self.isciler(c, "G-C")), 1)

    def test_a_duzeltilirse_b_ve_c_yeniden_kosar(self):
        s, c = self.kos([kart("G-A", "src/a.py"), kart("G-B", "src/b.py", ["G-A"]), kart("G-C", "src/c.py", ["G-B"])],
                        kartlar={"G-A": {"denetim": [RET, ONAY]}})
        self.assertEqual([s[i]["durum"] for i in ("G-A", "G-B", "G-C")], ["onaylandi"] * 3)
        self.assertTrue(self.isciler(c, "G-B")[-1]["ilk"].endswith("#SUREC:yeniden"))
        self.assertTrue(self.isciler(c, "G-C")[-1]["ilk"].endswith("#SUREC:yeniden"))
        self.assertEqual(len(self.isciler(c, "G-C")), 2)


if __name__ == "__main__":
    unittest.main()
