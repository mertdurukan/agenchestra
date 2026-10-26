"""I-159 P6: `orkestra maliyet taban` — kalem dökümü, eşik tablosu, iş başına $ (salt okuma; sentetik transkript)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import maliyet_taban as MT  # noqa: E402
import ork_lib as L  # noqa: E402


def yaz(yol, kayitlar):
    with open(yol, "w", encoding="utf-8") as f:
        for k in kayitlar:
            f.write(json.dumps(k) + "\n")


def cagri(mid, okuma, yazma=0, girdi=1, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"id": mid, "model": "claude-opus-5-5",
                        "usage": {"input_tokens": girdi, "output_tokens": 10, "cache_read_input_tokens": okuma,
                                  "cache_creation_input_tokens": yazma}}}


class Taban(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_kalem_dokumu_ve_ilk_cagri(self):
        f = os.path.join(self.d, "a.jsonl")
        yaz(f, [{"attachment": {"type": "instructions", "files": [{"content": "k" * 100}, {"content": "z" * 20}]}},
                {"attachment": {"type": "skill_listing", "content": "s" * 50}},
                {"type": "user", "message": {"content": "merhaba"}},
                cagri("m1", 1000, 500)])
        kalem, ilk = MT.oturum_taban(f)
        self.assertEqual((kalem["kural dosyaları"], kalem["skill listesi"], kalem["ilk kullanıcı mesajı"]), (120, 50, 7))
        self.assertEqual(ilk, 1000 + 500 + 1)

    def test_taban_bolumu_medyan_ve_kalibre_isareti(self):
        for i, ilk in enumerate((100, 300, 200)):
            yaz(os.path.join(self.d, f"{i}.jsonl"), [{"attachment": {"type": "instructions", "files": [{"content": "k" * 1000}]}},
                                                      cagri(f"m{i}", ilk)])
        r = MT.taban_bolumu(self.d, 1)
        self.assertEqual((r["oturum"], r["ilk_medyan"]), (3, 201))
        kural = next(k for k in r["kalemler"] if k["kalem"] == "kural dosyaları")
        self.assertTrue(kural["kalibre"])
        self.assertEqual(kural["token"], int(1000 * 0.447))
        self.assertFalse(next(k for k in r["kalemler"] if k["kalem"] == "skill listesi")["kalibre"])

    def test_esik_bolumu_tekilleştirir_yan_zinciri_atlar(self):
        yaz(os.path.join(self.d, "a.jsonl"), [cagri("m1", 120_000), cagri("m1", 120_000), cagri("m2", 160_000),
                                              cagri("m3", 210_000), cagri("y", 400_000, sidechain=True)])
        r = MT.esik_bolumu(self.d, 1)
        self.assertEqual(r["cagri"], 3)
        sat = {x["esik"]: x for x in r["esikler"]}
        self.assertEqual([sat[e]["cagri"] for e in (100_000, 150_000, 200_000)], [3, 2, 1])
        okuma = L.model_fiyati("claude-opus-5-5")["onbellek_okuma"]
        self.assertAlmostEqual(sat[200_000]["devir_kazanc_ust_sinir"], (210_001 - 200_000) * okuma / 1e6, places=6)
        self.assertEqual(sat[200_000]["oturum"], 1)

    def test_sonra_yalniz_sonradan_baslayan_oturumlari_alir(self):
        import datetime as D
        for ad, z in (("eski", "2026-10-20T10:00:00+00:00"), ("yeni", "2026-10-22T10:00:00+00:00")):
            yaz(os.path.join(self.d, ad + ".jsonl"), [{"type": "user", "timestamp": z, "message": {"content": "x"}}, cagri(ad, 1000)])
        kesim = D.datetime(2026, 10, 21, tzinfo=D.timezone.utc)
        self.assertEqual(MT.taban_bolumu(self.d, 9999)["oturum"], 2)
        self.assertEqual(MT.taban_bolumu(self.d, 9999, kesim)["oturum"], 1)
        self.assertEqual(MT.esik_bolumu(self.d, 9999, sonra=kesim)["cagri"], 1)

    def test_bos_dizin(self):
        self.assertEqual(MT.taban_bolumu(self.d, 1), {"oturum": 0})
        self.assertEqual(MT.esik_bolumu(self.d, 1), {"cagri": 0})

    def test_oran_dosyasi_yoksa_varsayilan(self):
        with mock.patch.object(MT, "_ORAN_YOLU", os.path.join(self.d, "yok.json")):
            self.assertEqual(MT.oranlar(), MT._ORAN_VARSAYILAN)


def kullanici(metin):
    return {"type": "user", "message": {"content": metin}}


def arac_sonucu():
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "content": "x"}]}}


def cagri_arac(mid, n_arac, okuma=1000, cikis=10):
    return {"type": "assistant", "message": {"id": mid, "model": "claude-sonnet-5-5",
                                              "content": [{"type": "tool_use", "id": f"{mid}-{i}", "name": "Bash"} for i in range(n_arac)],
                                              "usage": {"input_tokens": 1, "output_tokens": cikis, "cache_read_input_tokens": okuma}}}


class Istek(unittest.TestCase):
    """I-222 P1/P2: istek dağılımı, sıkıştırma sayacı ve önek $ (sentetik transkript)."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def _dosya(self, ad, kayitlar):
        yol = os.path.join(self.d, ad + ".jsonl")
        yaz(yol, kayitlar)
        return yol

    def test_istek_sinirlari_ve_sistem_mesajlari(self):
        yol = self._dosya("a", [kullanici("yap"), cagri_arac("m1", 2), arac_sonucu(), cagri_arac("m2", 1),
                                kullanici("<task-notification>x"), cagri_arac("m3", 0),       # bildirim yeni istek değil
                                kullanici("[Request interrupted by user]"),                    # kesinti notu yeni istek değil
                                kullanici("ikinci"), cagri_arac("m4", 60)])
        r = MT.istekler(yol, L.fiyat_tablosu())
        self.assertEqual([(i[1], i[2]) for i in r["istekler"]], [(3, 3), (60, 1)])

    def test_ayni_mesajin_bloklari_tek_cagri_araclar_toplanir_cikis_en_buyuk(self):
        yol = self._dosya("a", [kullanici("yap"), cagri_arac("m1", 1, cikis=5), cagri_arac("m1", 2, cikis=500)])
        i = MT.istekler(yol, L.fiyat_tablosu())["istekler"][0]
        self.assertEqual((i[1], i[2]), (3, 1))
        self.assertAlmostEqual(i[0], L.kullanim_maliyeti("claude-sonnet-5-5", {"input_tokens": 1, "output_tokens": 500, "cache_read_input_tokens": 1000}), places=9)

    def test_yan_zincir_sayilmaz_ve_sikistirma_sayilir(self):
        yan = cagri_arac("y", 5)
        yan["isSidechain"] = True
        yol = self._dosya("a", [kullanici("yap"), cagri_arac("m1", 1), yan, {"type": "system", "subtype": "compact_boundary"},
                                {"type": "user", "isCompactSummary": True, "message": {"content": "özet"}}, cagri_arac("m2", 1)])
        r = MT.istekler(yol, L.fiyat_tablosu())
        self.assertEqual((len(r["istekler"]), r["istekler"][0][2], r["sikistirma"]), (1, 2, 1))

    def test_istek_bolumu_agir_istek_payi_ve_sikistirma_oturumu(self):
        self._dosya("a", [kullanici("a")] + [cagri_arac(f"a{i}", 1) for i in range(50)] + [{"type": "system", "subtype": "compact_boundary"}])
        self._dosya("b", [kullanici("b"), cagri_arac("b1", 1)])
        r = MT.istek_bolumu(self.d, 1)
        self.assertEqual((r["istek"], r["agir50"]["adet"], r["kucuk"]["adet"], r["sikistirma"], r["sikistirma_oturum"]), (2, 1, 1, 1, 1))
        self.assertAlmostEqual(r["agir50"]["pay"] + r["kucuk"]["pay"], 1.0, places=9)
        self.assertEqual(r["en_pahali"][0]["arac"], 50)
        self.assertEqual(MT.istek_bolumu(tempfile.mkdtemp(), 1), {"istek": 0, "sikistirma": 0, "sikistirma_oturum": 0})

    def test_sikistirma_gunluk_sayar(self):
        sd = tempfile.mkdtemp()
        with open(os.path.join(sd, "gunluk.jsonl"), "w", encoding="utf-8") as f:
            for r in ({"zaman": "2026-10-20T10:00:00", "tur": "sikistirma"}, {"zaman": "2026-10-23T10:00:00", "tur": "sikistirma"},
                      {"zaman": "2026-10-23T11:00:00", "tur": "ayar"}):
                f.write(json.dumps(r) + "\n")
        self.assertEqual(MT.sikistirma_gunluk(sd, "2026-10-22"), 1)
        self.assertEqual(MT.sikistirma_gunluk(tempfile.mkdtemp(), "2026-10-22"), 0)

    def test_onek_maliyeti_okuma_artı_yazma(self):
        f = L.model_fiyati("claude-sonnet-5-5")
        taban, esik = {"oturum": 3}, {"cagri": 10, "okuma_fiyat_toplam": 10 * f["onbellek_okuma"]}
        o = MT.onek_maliyeti(taban, esik, {"sikistirma": 2, "baskin_model": "claude-sonnet-5-5"})
        self.assertAlmostEqual(o["okuma"], 10 * f["onbellek_okuma"] / 1000, places=9)
        self.assertAlmostEqual(o["yazma"], 5 * f["onbellek_yazma_1sa"] / 1000, places=9)
        self.assertEqual(o["yazma_adedi"], 5)
        self.assertIsNone(MT.onek_maliyeti({"oturum": 0}, esik, {}))

    def test_metin_yeni_bolumleri_yazar(self):
        self._dosya("a", [kullanici("a"), cagri_arac("a1", 1, okuma=120_000)])
        sd = tempfile.mkdtemp()
        with mock.patch.object(L, "maliyet_kayitlari", return_value=[]):
            t = MT.metin(MT.hesapla(sd, self.d, 1, "2026-10-01"))
        for parca in ("## İstek dağılımı", "50+ araç çağrılı istek", "Sıkıştırma (compact)", "Önekte her 1000 token", "pencere $ (merkez)"):
            self.assertIn(parca, t)


class DevirTanimi(unittest.TestCase):
    """I-222 P3: eşik üstü okuma fazlası (brüt) ile ADR-0034 net devir kazancı ayrı hesaplanır; uyarı etkisi önceden sabit kuralla karar verir."""

    def _c(self, baglam):
        return (baglam, 0.0, 0.2, 20.0, 8.0)  # okuma, çıkış, 1 saatlik yazma $/M (opus)

    def test_devir_net_elle_hesap(self):
        uzun = [self._c(250_000)] * 101  # ilk çağrı devir noktası, sonraki 100 çağrı küçülür
        kisa = [self._c(50_000)] * 5
        adet, net = MT.devir_net([uzun, kisa], 200_000, 30_000, 10_000)
        brut = 100 * (250_000 - 30_000) * 0.2 / 1e6
        maliyet = (10_000 * 20 + 40_000 * 8) / 1e6
        self.assertEqual(adet, 1)
        self.assertAlmostEqual(net, brut - maliyet, places=9)

    def test_devir_net_az_sonraki_cagri_negatif(self):
        adet, net = MT.devir_net([[self._c(250_000)] * 3], 200_000, 30_000, 10_000)
        self.assertEqual(adet, 1)
        self.assertLess(net, 0)

    def test_esik_tablosu_iki_tanimi_ayri_sutunda_gosterir(self):
        d = tempfile.mkdtemp()
        yaz(os.path.join(d, "a.jsonl"), [cagri(f"m{i}", 250_000) for i in range(20)])
        r = MT.esik_bolumu(d, 1, yeni_taban=30_000)
        self.assertIn("devir_net", r["esikler"][-1])
        self.assertIn("devir_kazanc_ust_sinir", r["esikler"][-1])
        self.assertNotIn("devir_net", MT.esik_bolumu(d, 1)["esikler"][-1])

    def _gunler(self, d, kesim_gunu, once, sonra, once_asan, sonra_asan):
        """Her gün 10 çağrılı bir transkript; `*_asan` gün başına aşan çağrı sayısı dizisi (döngüyle tekrarlanır)."""
        import datetime
        gunler = [(kesim_gunu - datetime.timedelta(days=i + 1), once_asan[i % len(once_asan)]) for i in range(once)]
        gunler += [(kesim_gunu + datetime.timedelta(days=i + 1), sonra_asan[i % len(sonra_asan)]) for i in range(sonra)]
        for g, asan in gunler:
            satirlar = []
            for k in range(10):
                c = cagri(f"{g}-{k}", 250_000 if k < asan else 50_000)
                c["timestamp"] = f"{g.isoformat()}T12:00:00Z"
                satirlar.append(c)
            yaz(os.path.join(d, f"{g}.jsonl"), satirlar)

    def _etki(self, once, sonra, once_asan, sonra_asan):
        import datetime
        d = tempfile.mkdtemp()
        kesim_gunu = datetime.date(2026, 10, 10)
        self._gunler(d, kesim_gunu, once, sonra, once_asan, sonra_asan)
        kesim = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=datetime.timezone.utc)
        return MT.uyari_etkisi(d, kesim, gun=60, min_cagri=5, bugun=datetime.date(2026, 10, 30))

    def test_uyari_etkisi_var(self):
        r = self._etki(8, 8, [5, 4], [1, 2])
        self.assertEqual(r["karar"], "etki var")
        self.assertGreaterEqual(r["fark"], 0.05)

    def test_uyari_etkisi_gorulmedi(self):
        r = self._etki(8, 8, [3, 4], [3, 4])
        self.assertEqual(r["karar"], "etki görülmedi")

    def test_uyari_etkisi_yetersiz_veri_ve_tohum_sabit(self):
        r = self._etki(8, 3, [5, 4], [1, 2])
        self.assertEqual(r["karar"], "yetersiz veri")
        self.assertEqual(self._etki(8, 3, [5, 4], [1, 2])["yanlar"]["once"], r["yanlar"]["once"])

    def test_uyari_etkisi_az_cagrili_gun_elenir_ve_bugun_kesim_gunu_sayilmaz(self):
        import datetime
        d = tempfile.mkdtemp()
        self._gunler(d, datetime.date(2026, 10, 10), 7, 7, [4], [1])
        yaz(os.path.join(d, "kisa.jsonl"), [dict(cagri("k1", 250_000), timestamp="2026-09-25T12:00:00Z")])
        kesim = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=datetime.timezone.utc)
        r = MT.uyari_etkisi(d, kesim, gun=60, min_cagri=5, bugun=datetime.date(2026, 10, 30))
        self.assertEqual((r["yanlar"]["once"]["gun"], r["yanlar"]["once"]["elenen_gun"]), (7, 1))  # 25.09: tek çağrı, elenir
        self.assertEqual(r["yanlar"]["sonra"]["gun"], 7)
        r2 = MT.uyari_etkisi(d, kesim, gun=60, min_cagri=5, bugun=datetime.date(2026, 10, 14))
        self.assertEqual(r2["yanlar"]["sonra"]["gun"], 3)  # bugün (14.10) kısmi gün: dışarıda

    def test_metin_uyari_bolumu_yazar(self):
        import datetime
        d = tempfile.mkdtemp()
        yaz(os.path.join(d, "a.jsonl"), [dict(cagri("m1", 250_000), timestamp="2026-10-01T12:00:00Z")])
        sd = tempfile.mkdtemp()
        with mock.patch.object(L, "maliyet_kayitlari", return_value=[]):
            t = MT.metin(MT.hesapla(sd, d, 1, "2026-10-01", uyari_kesim=datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc)))
        for parca in ("## Devir uyarısı etkisi", "yetersiz veri", "net devir kazancı $", "eşik üstü okuma fazlası $"):
            self.assertIn(parca, t)


class Hiz(unittest.TestCase):
    """I-222 P8: tur süresi kırılımı (zaman.jsonl; sentetik)."""

    def _sd(self, satirlar):
        sd = tempfile.mkdtemp()
        yaz(os.path.join(sd, "zaman.jsonl"), satirlar)
        return sd

    def test_kirilim_arac_bekleme_ve_kalan(self):
        z = "2026-10-20T10:00:00+03:00"
        sd = self._sd([
            {"zaman": z, "tur": "ana", "sure_ms": 100_000, "istek_id": "a"},
            {"zaman": z, "tur": "ana", "sure_ms": 40_000, "istek_id": "b"},
            {"zaman": z, "tur": "ana", "sure_ms": 999_000},  # istek_id yok: kırılıma girmez
            {"zaman": z, "tur": "arac", "arac": "Bash", "istek_id": "a", "sure_ms": 30_000},
            {"zaman": z, "tur": "arac", "arac": "AskUserQuestion", "istek_id": "a", "sure_ms": 10_000},
            {"zaman": z, "tur": "arac", "arac": "Bash", "istek_id": "b", "sure_ms": 60_000},  # tur 40 sn: 40 sn'ye kırpılır
            {"zaman": z, "tur": "alt", "sure_ms": 7_200_000},
            {"zaman": "2026-10-01T10:00:00+03:00", "tur": "ana", "sure_ms": 5_000, "istek_id": "eski"},  # pencere dışı
        ])
        h = MT.hiz_bolumu(sd, "2026-10-17")
        self.assertEqual((h["tur"], h["istek_id_yok"], h["kirpilan"]), (2, 1, 1))
        self.assertAlmostEqual(h["toplam_sn"], 140)
        self.assertAlmostEqual(h["arac_sn"], 30 + 10 + 40)
        self.assertAlmostEqual(h["bekleme_sn"], 10)
        self.assertAlmostEqual(h["kalan_sn"], 60)
        self.assertAlmostEqual(h["arac_sn"] + h["kalan_sn"], h["toplam_sn"])
        self.assertEqual(h["alt_sn"], 7200)
        self.assertEqual(h["araclar"][0][0], "Bash")

    def test_dosya_yoksa_ya_da_tur_yoksa_none(self):
        self.assertIsNone(MT.hiz_bolumu(tempfile.mkdtemp(), "2026-10-17"))
        self.assertIsNone(MT.hiz_bolumu(self._sd([{"zaman": "2026-10-20", "tur": "ana", "sure_ms": 5}]), "2026-10-17"))


class IsBasina(unittest.TestCase):
    def test_kapanan_is_ve_teslim_kart(self):
        sd = tempfile.mkdtemp()
        isk = os.path.join(sd, "is1")
        os.makedirs(isk)
        json.dump({"id": "I-1", "gecmis": [{"olay": "durum:kapandi", "zaman": "2026-10-20T10:00:00"}]}, open(os.path.join(isk, "is.json"), "w"))
        json.dump({"isler": {"I-1": {"durum": "kapandi", "klasor": isk}, "I-2": {"durum": "acik", "klasor": isk}}}, open(os.path.join(sd, "isler.json"), "w"))
        os.makedirs(os.path.join(sd, "gorevler"))
        json.dump({"id": "G-1", "durum": "teslim", "gecmis": [{"olay": "teslim", "zaman": "2026-10-21T10:00:00"}],
                   "denetimler": [{"karar": "ret"}, {"karar": "onay"}]}, open(os.path.join(sd, "gorevler", "G-1.json"), "w"))
        json.dump({"id": "G-2", "durum": "teslim", "gecmis": [{"olay": "teslim", "zaman": "2026-10-21T11:00:00"}],
                   "denetimler": [{"karar": "onay"}]}, open(os.path.join(sd, "gorevler", "G-2.json"), "w"))
        defter = [{"zaman": "2026-10-20T09:00:00", "is": "I-1", "gorev": "-", "maliyet_usd": 6.0},
                  {"zaman": "2026-10-21T09:00:00", "is": "I-1", "gorev": "G-1", "maliyet_usd": 3.0},
                  {"zaman": "2026-10-21T09:30:00", "gorev": "G-2", "maliyet_usd": 1.0},
                  {"zaman": "2026-10-10T09:00:00", "is": "I-1", "gorev": "-", "maliyet_usd": 50.0}]
        with mock.patch.object(L, "maliyet_kayitlari", return_value=defter):
            r = MT.is_basina_bolumu(sd, "2026-10-16")
        self.assertEqual((r["kapanan_is"], r["a_usd"]), (1, 9.0))   # pencere dışı 50$ sayılmaz
        self.assertEqual((r["teslim_kart"], r["b_usd"], r["ret_orani"]), (2, 2.0, 0.5))

    def test_isler_yoksa_cokmez(self):
        sd = tempfile.mkdtemp()
        with mock.patch.object(L, "maliyet_kayitlari", return_value=[]):
            r = MT.is_basina_bolumu(sd, "2026-10-16")
        self.assertEqual((r["kapanan_is"], r["a_usd"], r["teslim_kart"], r["b_usd"]), (0, None, 0, None))


if __name__ == "__main__":
    unittest.main()
