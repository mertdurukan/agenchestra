"""G-076: scripts/kural_aday.py (kural adayı, maliyet anomalisi, bütçe tavanı) - salt okuma.

Sözleşme:
  kural_adaylari(kartlar, esik=3) -> [{sinif, neden, sayi, ornek_kartlar(<=5), oneri_kriter(str,dolu), oneri_on_kontrol}]
    sinif_normal: 'kod-duzenleme'->'kod', None/'-'->'belirsiz'. Sayı = karar=='ret' denetim sayısı (neden kodu;
    bilinmeyen/None -> 'siniflanmamis'). sayi>=esik döner; sayıya göre azalan.
  anomaliler(kartlar, kayitlar, k=3.0, min_grup=4) -> [{id, sinif, basamak, usd, medyan, esik, ret_sayisi}]
    kart USD = kayitlar'da gorev==id maliyet_usd toplamı; grup=(sinif_normal, kart['basamak']); MAD=medyan(|x-medyan|)
    (ölçeklenmemiş); usd > medyan + k*MAD (MAD=0 ise usd > medyan*2); n<min_grup grup atlanır.
  butce_tavani(kartlar, kayitlar, min_grup=4) -> [{sinif, basamak, n, tavan_usd}], tavan = 2 * p90, p90 = nearest-rank
    (kpi.py ile aynı: sıralı listede ceil(0.9*n). eleman); n<min_grup grup dönmez.
  CLI: kural_aday.py rapor [--esik N] [--json] [--sd DIR]; --json -> {kural_adaylari, anomaliler, butce_tavani}.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
MODUL = os.path.join(SCRIPTS, "kural_aday.py")
sys.path.insert(0, SCRIPTS)

try:
    import kural_aday as KA
except ImportError:  # kırmızı aşama: modül yok
    KA = None


def kart(i, sinif="kod", basamak="T2", rets=(), durum="onaylandi"):
    return {"id": f"G-{i:03d}", "sinif": sinif, "basamak": basamak, "baslangic_basamak": basamak, "durum": durum,
            "denetimler": [{"zaman": "2026-03-10T10:00:00+03:00", "sira": n + 1, "karar": "ret", "neden": r,
                            "basamak": basamak} for n, r in enumerate(rets)]}


def mal(gid, usd, **ek):
    r = {"gorev": gid, "maliyet_usd": usd, "zaman": "2026-03-10T10:00:00+03:00", "kaynak": "tur",
         "oturum": "o1", "agent_id": f"a-{gid}"}
    r.update(ek)
    return r


def grup(baslangic, usdler, sinif="kod", basamak="T2"):
    kartlar = [kart(baslangic + i, sinif, basamak) for i in range(len(usdler))]
    return kartlar, [mal(k["id"], u) for k, u in zip(kartlar, usdler)]


def hazir():
    assert KA is not None, "scripts/kural_aday.py yok"
    return KA


class KuralAdaylari(unittest.TestCase):
    def test_esik_alti_donmez_esik_ve_ustu_doner_azalan(self):
        kartlar = [kart(1, rets=["bicim", "bicim"]), kart(2, rets=["bicim", "kanit-yok"]),
                   kart(3, rets=["bicim", "kanit-yok"]), kart(4, rets=["bicim"]),
                   kart(5, rets=["kanit-yok", "kapsam-eksik"]), kart(6, rets=["kapsam-eksik"])]
        s = hazir().kural_adaylari(kartlar, esik=3)
        self.assertEqual([(a["neden"], a["sayi"]) for a in s], [("bicim", 5), ("kanit-yok", 3)])
        self.assertTrue(all(a["sinif"] == "kod" for a in s))

    def test_varsayilan_esik_3(self):
        kartlar = [kart(i, rets=["bicim"]) for i in range(1, 3)]
        self.assertEqual(hazir().kural_adaylari(kartlar), [])
        kartlar.append(kart(3, rets=["bicim"]))
        self.assertEqual(len(hazir().kural_adaylari(kartlar)), 1)

    def test_esik_parametresi(self):
        kartlar = [kart(1, rets=["bicim", "bicim"])]
        self.assertEqual(hazir().kural_adaylari(kartlar, esik=3), [])
        self.assertEqual(hazir().kural_adaylari(kartlar, esik=2)[0]["sayi"], 2)

    def test_sinif_normallestirme(self):
        kartlar = [kart(1, "kod-duzenleme", rets=["bicim"]), kart(2, "kod", rets=["bicim"]),
                   kart(3, "kod", rets=["bicim"]),
                   kart(4, None, rets=["kanit-yok"]), kart(5, "-", rets=["kanit-yok"]),
                   kart(6, "belirsiz", rets=["kanit-yok"])]
        s = {(a["sinif"], a["neden"]): a["sayi"] for a in hazir().kural_adaylari(kartlar)}
        self.assertEqual(s, {("kod", "bicim"): 3, ("belirsiz", "kanit-yok"): 3})

    def test_sinif_ayri_sayilir(self):
        kartlar = [kart(1, "kod", rets=["bicim", "bicim"]), kart(2, "belge", rets=["bicim", "bicim"])]
        self.assertEqual(hazir().kural_adaylari(kartlar, esik=3), [])

    def test_ornek_kartlar_en_cok_5_tekil(self):
        kartlar = [kart(i, rets=["bicim"]) for i in range(1, 9)]
        a = hazir().kural_adaylari(kartlar)[0]
        self.assertEqual(a["sayi"], 8)
        self.assertEqual(len(a["ornek_kartlar"]), 5)
        self.assertEqual(len(set(a["ornek_kartlar"])), 5)
        self.assertTrue(set(a["ornek_kartlar"]) <= {f"G-{i:03d}" for i in range(1, 9)})

    def test_ayni_kartta_tekrar_ret_sayiya_girer_ornek_tekil(self):
        a = hazir().kural_adaylari([kart(1, rets=["bicim"] * 3)])
        self.assertEqual(a[0]["sayi"], 3)
        self.assertEqual(a[0]["ornek_kartlar"], ["G-001"])

    def test_oneri_kriter_dolu_ve_on_kontrol_alani_var(self):
        nedenler = ["kapsam-eksik", "bicim", "sayi-tutarsiz", "kanit-yok", "talimat-ihlali", "kriter-belirsiz",
                    "yetenek-yetersiz"]
        kartlar = [kart(i, rets=nedenler) for i in range(1, 4)]
        s = hazir().kural_adaylari(kartlar)
        self.assertEqual(sorted(a["neden"] for a in s), sorted(nedenler))
        for a in s:
            self.assertIsInstance(a["oneri_kriter"], str)
            self.assertTrue(a["oneri_kriter"].strip(), a["neden"])
            self.assertIn("oneri_on_kontrol", a)
            self.assertTrue(a["oneri_on_kontrol"] is None or (isinstance(a["oneri_on_kontrol"], str)
                                                              and a["oneri_on_kontrol"].strip()))
        self.assertEqual(len({a["oneri_kriter"] for a in s}), len(nedenler))  # şablon nedene özgü

    def test_bilinmeyen_ve_bos_neden_siniflanmamis(self):
        kartlar = [kart(1, rets=["uydurma"]), kart(2, rets=[None]), kart(3, rets=["x-y"])]
        s = hazir().kural_adaylari(kartlar)
        self.assertEqual([(a["neden"], a["sayi"]) for a in s], [("siniflanmamis", 3)])
        self.assertTrue(s[0]["oneri_kriter"].strip())

    def test_onay_kararlari_ve_bos_girdi(self):
        k = kart(1)
        k["denetimler"] = [{"karar": "onay", "neden": "bicim"}] * 5
        self.assertEqual(hazir().kural_adaylari([k]), [])
        self.assertEqual(hazir().kural_adaylari([]), [])
        self.assertEqual(hazir().kural_adaylari([{"id": "G-002"}]), [])  # denetimler/sinif alanı yok


class Anomaliler(unittest.TestCase):
    def test_medyan_arti_3_mad(self):
        kartlar, kay = grup(1, [1.0, 2.0, 3.0, 4.0, 100.0])  # medyan 3, MAD 1, eşik 6
        s = hazir().anomaliler(kartlar, kay)
        self.assertEqual([a["id"] for a in s], ["G-005"])
        a = s[0]
        self.assertAlmostEqual(a["usd"], 100.0)
        self.assertAlmostEqual(a["medyan"], 3.0)
        self.assertAlmostEqual(a["esik"], 6.0)
        self.assertEqual((a["sinif"], a["basamak"], a["ret_sayisi"]), ("kod", "T2", 0))

    def test_esitlik_anomali_degil(self):
        kartlar, kay = grup(1, [1.0, 2.0, 3.0, 4.0, 6.0])  # eşik 6.0; 6.0 anomali değil
        self.assertEqual(hazir().anomaliler(kartlar, kay), [])

    def test_k_parametresi(self):
        kartlar, kay = grup(1, [1.0, 2.0, 3.0, 4.0, 6.0])
        s = hazir().anomaliler(kartlar, kay, k=2.0)  # eşik 5
        self.assertEqual([a["id"] for a in s], ["G-005"])
        self.assertAlmostEqual(s[0]["esik"], 5.0)

    def test_cift_n_medyan_ortalama(self):
        # sıralı 1,2,3,4,5,50 -> medyan 3.5; sapmalar .5,.5,1.5,1.5,2.5,46.5 -> MAD 1.5
        kartlar, kay = grup(1, [1.0, 2.0, 4.0, 5.0, 50.0, 3.0])
        s = hazir().anomaliler(kartlar, kay)
        self.assertEqual([a["id"] for a in s], ["G-005"])
        self.assertAlmostEqual(s[0]["medyan"], 3.5)
        self.assertAlmostEqual(s[0]["esik"], 3.5 + 3 * 1.5)

    def test_mad_sifir_dali_medyan_x2(self):
        kartlar, kay = grup(1, [2.0, 2.0, 2.0, 2.0, 3.9, 5.0])  # medyan 2, MAD 0, eşik 4.0
        s = hazir().anomaliler(kartlar, kay)
        self.assertEqual([a["id"] for a in s], ["G-006"])
        self.assertAlmostEqual(s[0]["esik"], 4.0)
        self.assertAlmostEqual(s[0]["medyan"], 2.0)

    def test_mad_sifir_esitlik_anomali_degil(self):
        kartlar, kay = grup(1, [2.0, 2.0, 2.0, 2.0, 4.0])  # eşik 4.0, 4.0 > 4.0 değil
        self.assertEqual(hazir().anomaliler(kartlar, kay), [])

    def test_min_grup_alti_atlanir(self):
        kartlar, kay = grup(1, [1.0, 1.0, 500.0])
        self.assertEqual(hazir().anomaliler(kartlar, kay), [])  # n=3 < 4
        kartlar, kay = grup(1, [1.0, 1.0, 1.0, 500.0])  # n=4: MAD 0, eşik 2
        self.assertEqual([a["id"] for a in hazir().anomaliler(kartlar, kay)], ["G-004"])

    def test_min_grup_parametresi(self):
        kartlar, kay = grup(1, [1.0, 1.0, 500.0])
        self.assertEqual([a["id"] for a in hazir().anomaliler(kartlar, kay, min_grup=3)], ["G-003"])

    def test_gruplar_sinif_ve_son_basamaga_gore_ayri(self):
        k1, m1 = grup(1, [1.0, 1.0, 1.0, 1.0], "kod", "T2")
        k2, m2 = grup(10, [100.0, 100.0, 100.0, 100.0], "kod", "T3")
        k3, m3 = grup(20, [100.0, 100.0, 100.0, 100.0], "belge", "T2")
        self.assertEqual(hazir().anomaliler(k1 + k2 + k3, m1 + m2 + m3), [])
        k4 = kart(30, "kod", "T2")  # 100 USD'lik kart T2/kod grubunda anomali, T3 grubunda olmazdı
        s = hazir().anomaliler(k1 + k2 + k3 + [k4], m1 + m2 + m3 + [mal("G-030", 100.0)])
        self.assertEqual([a["id"] for a in s], ["G-030"])

    def test_kod_duzenleme_koda_katilir(self):
        kartlar, kay = grup(1, [1.0, 1.0, 1.0])
        k = kart(4, "kod-duzenleme")
        s = hazir().anomaliler(kartlar + [k], kay + [mal("G-004", 9.0)])
        self.assertEqual([(a["id"], a["sinif"]) for a in s], [("G-004", "kod")])

    def test_son_basamak_kullanilir(self):
        kartlar, kay = grup(1, [1.0, 1.0, 1.0, 1.0], basamak="T3")
        for k in kartlar:
            k["baslangic_basamak"] = "T2"
        k5 = kart(5, "kod", "T3")
        k5["baslangic_basamak"] = "T2"
        s = hazir().anomaliler(kartlar + [k5], kay + [mal("G-005", 9.0)])
        self.assertEqual([(a["id"], a["basamak"]) for a in s], [("G-005", "T3")])

    def test_ret_sayisi_ve_kart_basina_toplam(self):
        kartlar, kay = grup(1, [1.0, 1.0, 1.0, 1.0])
        kartlar[3]["denetimler"] = [{"karar": "ret", "neden": "bicim"}, {"karar": "onay"}, {"karar": "ret"}]
        kay += [mal("G-004", 4.0, agent_id="b"), mal("G-004", 5.0, agent_id="c")]  # G-004 toplam 10
        s = hazir().anomaliler(kartlar, kay)
        self.assertEqual(len(s), 1)
        self.assertAlmostEqual(s[0]["usd"], 10.0)
        self.assertEqual(s[0]["ret_sayisi"], 2)

    def test_maliyetsiz_kart_sifir_ve_ana_ajan_satiri_kartlara_dagilmaz(self):
        kartlar, kay = grup(1, [1.0, 1.0, 1.0, 1.0])
        kartlar.append(kart(5))  # maliyet kaydı yok -> 0 USD, anomali değil
        kay += [mal("-", 99.0), mal(None, 99.0), mal("G-999", 99.0)]
        self.assertEqual(hazir().anomaliler(kartlar, kay), [])

    def test_bos_girdi(self):
        self.assertEqual(hazir().anomaliler([], []), [])


class ButceTavani(unittest.TestCase):
    def test_p90_x2_nearest_rank(self):
        kartlar, kay = grup(1, [float(i) for i in range(1, 11)])  # n=10 -> 9. eleman = 9 -> 18
        s = hazir().butce_tavani(kartlar, kay)
        self.assertEqual(len(s), 1)
        self.assertEqual((s[0]["sinif"], s[0]["basamak"], s[0]["n"]), ("kod", "T2", 10))
        self.assertAlmostEqual(s[0]["tavan_usd"], 18.0)

    def test_p90_kucuk_n(self):
        kartlar, kay = grup(1, [1.0, 2.0, 3.0, 10.0])  # n=4 -> ceil(3.6)=4. eleman = 10 -> 20
        self.assertAlmostEqual(hazir().butce_tavani(kartlar, kay)[0]["tavan_usd"], 20.0)

    def test_girdi_sirasi_onemsiz(self):
        kartlar, kay = grup(1, [10.0, 3.0, 1.0, 2.0])
        self.assertAlmostEqual(hazir().butce_tavani(kartlar, kay)[0]["tavan_usd"], 20.0)

    def test_min_grup_alti_donmez_ve_gruplar_ayri(self):
        k1, m1 = grup(1, [1.0, 2.0, 3.0, 4.0], "kod", "T2")
        k2, m2 = grup(10, [5.0, 6.0, 7.0], "kod", "T3")  # n=3 -> yok
        k3, m3 = grup(20, [1.0, 1.0, 1.0, 1.0], "kod-duzenleme", "T3")
        s = hazir().butce_tavani(k1 + k2 + k3, m1 + m2 + m3)
        d = {(a["sinif"], a["basamak"]): (a["n"], a["tavan_usd"]) for a in s}
        self.assertEqual(sorted(d), [("kod", "T2"), ("kod", "T3")])
        self.assertEqual(d[("kod", "T2")], (4, 8.0))
        self.assertEqual(d[("kod", "T3")], (4, 2.0))
        self.assertEqual(len(hazir().butce_tavani(k2, m2)), 0)
        self.assertEqual(len(hazir().butce_tavani(k2, m2, min_grup=3)), 1)

    def test_yalniz_bilgi_girdiyi_degistirmez(self):
        kartlar, kay = grup(1, [1.0, 2.0, 3.0, 4.0])
        k0, m0 = copy.deepcopy(kartlar), copy.deepcopy(kay)
        hazir().butce_tavani(kartlar, kay)
        hazir().anomaliler(kartlar, kay)
        hazir().kural_adaylari(kartlar)
        self.assertEqual((kartlar, kay), (k0, m0))

    def test_bos(self):
        self.assertEqual(hazir().butce_tavani([], []), [])


def sd_kur(kartlar, satirlar):
    sd = tempfile.mkdtemp()
    os.makedirs(os.path.join(sd, "gorevler"))
    for k in kartlar:
        with open(os.path.join(sd, "gorevler", k["id"] + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(k, f)
    if satirlar is not None:
        with open(os.path.join(sd, "maliyet.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            for r in satirlar:
                f.write(json.dumps(r) + "\n")
    return sd


def cli(*arg):
    return subprocess.run([sys.executable, MODUL, "rapor", *arg], capture_output=True, text=True, encoding="utf-8")


def anlik(sd):
    out = {}
    for kok, _, dosyalar in os.walk(sd):
        for d in dosyalar:
            y = os.path.join(kok, d)
            with open(y, "rb") as f:
                out[y] = f.read()
    return out


class Cli(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODUL), "scripts/kural_aday.py yok")

    def test_json_gecerli_sifir_cikis_ve_uc_bolum(self):
        kartlar, kay = grup(1, [1.0, 2.0, 3.0, 4.0, 100.0])
        for k in kartlar:
            k["denetimler"] = [{"karar": "ret", "neden": "bicim"}]
        p = cli("--json", "--sd", sd_kur(kartlar, kay))
        self.assertEqual(p.returncode, 0, p.stderr)
        j = json.loads(p.stdout)
        self.assertTrue(set(j) >= {"kural_adaylari", "anomaliler", "butce_tavani"})
        self.assertEqual([(a["neden"], a["sayi"]) for a in j["kural_adaylari"]], [("bicim", 5)])
        self.assertEqual([a["id"] for a in j["anomaliler"]], ["G-005"])
        self.assertAlmostEqual(j["butce_tavani"][0]["tavan_usd"], 200.0)  # n=5, ceil(4.5)=5. eleman 100

    def test_esik_bayragi(self):
        kartlar, _ = grup(1, [1.0, 1.0])
        for k in kartlar:
            k["denetimler"] = [{"karar": "ret", "neden": "bicim"}]
        sd = sd_kur(kartlar, [])
        self.assertEqual(json.loads(cli("--json", "--sd", sd).stdout)["kural_adaylari"], [])
        j = json.loads(cli("--json", "--esik", "2", "--sd", sd).stdout)
        self.assertEqual([a["sayi"] for a in j["kural_adaylari"]], [2])

    def test_cift_satir_cift_sayim_yok(self):
        """hook + tur çift satırı: yalnız L.maliyet_kayitlari tekilleştirmesi (tur kazanır, hook atılır)."""
        kartlar, kay = grup(1, [1.0, 1.0, 1.0, 1.0])
        kartlar.append(kart(5))
        satirlar = kay + [mal("G-005", 2.0, kaynak="tur", agent_id="x5"),
                          mal("G-005", 2.5, kaynak="hook", agent_id="x5")]  # hook atılmalı -> G-005 = 2.0
        j = json.loads(cli("--json", "--sd", sd_kur(kartlar, satirlar)).stdout)
        # çift sayımla G-005 4.5 olur ve anomali çıkardı; doğrusu 2.0 (eşik 2.0, 2.0 > 2.0 değil)
        self.assertEqual(j["anomaliler"], [])
        # USD [1,1,1,1,2] -> p90 5. eleman = 2 -> tavan 4.0 (çift sayımla 9.0)
        self.assertAlmostEqual(j["butce_tavani"][0]["tavan_usd"], 4.0)

    def test_hook_birikimli_son_satir(self):
        kartlar, kay = grup(1, [1.0, 1.0, 1.0, 1.0])
        kartlar.append(kart(5))
        satirlar = kay + [mal("G-005", 1.0, kaynak="hook", agent_id="y", zaman="2026-03-10T10:00:00+03:00"),
                          mal("G-005", 3.0, kaynak="hook", agent_id="y", zaman="2026-03-10T11:00:00+03:00")]
        j = json.loads(cli("--json", "--sd", sd_kur(kartlar, satirlar)).stdout)
        self.assertEqual([a["id"] for a in j["anomaliler"]], ["G-005"])
        self.assertAlmostEqual(j["anomaliler"][0]["usd"], 3.0)  # 1+3=4 değil

    def test_hicbir_dosya_yazmaz(self):
        kartlar, kay = grup(1, [1.0, 2.0, 3.0, 4.0, 100.0])
        sd = sd_kur(kartlar, kay)
        once = anlik(sd)
        self.assertEqual(cli("--sd", sd).returncode, 0)
        self.assertEqual(cli("--json", "--sd", sd).returncode, 0)
        self.assertEqual(anlik(sd), once)

    def test_duz_cikti_uc_bolum_ve_40_satir_sinir(self):
        siniflar = ["kod", "belge", "arastirma", "veri", "ceviri", "plan"]
        nedenler = ["kapsam-eksik", "bicim", "sayi-tutarsiz", "kanit-yok", "talimat-ihlali", "kriter-belirsiz",
                    "yetenek-yetersiz"]
        kartlar, satirlar, n = [], [], 0
        for s in siniflar:
            for b in ("T1", "T2", "T3", "T4"):
                for _ in range(4):
                    n += 1
                    k = kart(n, s, b, rets=nedenler)
                    kartlar.append(k)
                    satirlar.append(mal(k["id"], float(n)))
        sd = sd_kur(kartlar, satirlar)
        p = cli("--esik", "3", "--sd", sd)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertLessEqual(len(p.stdout.splitlines()), 40)
        metin = p.stdout.lower()
        for b in ("kural adayları", "anomaliler", "bütçe tavanı"):
            self.assertIn(b, metin)
        # kesme yalnız düz çıktıda: JSON tüm adayları taşır (6 sınıf x 7 neden)
        self.assertEqual(len(json.loads(cli("--json", "--sd", sd).stdout)["kural_adaylari"]), 42)

    def test_bos_durum_klasoru(self):
        sd = tempfile.mkdtemp()
        p = cli("--json", "--sd", sd)
        self.assertEqual(p.returncode, 0, p.stderr)
        j = json.loads(p.stdout)
        self.assertEqual((j["kural_adaylari"], j["anomaliler"], j["butce_tavani"]), ([], [], []))
        self.assertEqual(cli("--sd", sd).returncode, 0)

    def test_bozuk_kart_dosyasi_cokertmez(self):
        kartlar, kay = grup(1, [1.0, 1.0, 1.0, 1.0])
        sd = sd_kur(kartlar, kay)
        with open(os.path.join(sd, "gorevler", "G-900.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertEqual(cli("--json", "--sd", sd).returncode, 0)


class Kaynak(unittest.TestCase):
    def test_modul_maliyeti_yalniz_ork_lib_uzerinden_okur(self):
        self.assertTrue(os.path.isfile(MODUL), "scripts/kural_aday.py yok")
        with open(MODUL, "rb") as f:
            src = f.read().decode("utf-8")
        self.assertIn("maliyet_kayitlari", src)
        self.assertNotIn("maliyet.jsonl", src)
        self.assertNotIn("jsonl_oku", src)

    def test_lf_ve_bom_yok(self):
        for yol in (MODUL, os.path.join(AD, "test_kural_aday.py")):
            self.assertTrue(os.path.isfile(yol), yol)
            with open(yol, "rb") as f:
                ham = f.read()
            self.assertFalse(ham.startswith(b"\xef\xbb\xbf"), yol)
            self.assertNotIn(b"\r", ham, yol)


if __name__ == "__main__":
    unittest.main()
