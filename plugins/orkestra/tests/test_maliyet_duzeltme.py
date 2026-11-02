"""Maliyet defteri düzeltmeleri (M1–M3) ve kural onayında etki kancası (E1).

Kabul kriterleri:
  K1  'tur' satırı okunurken önbellek yazma 1 sa tarifesiyle yeniden fiyatlanır (hook satırlarıyla aynı).
  K2  tur kaydı başlamadan önceki ana-ajan hook token'ı 'hook-artik' satırı olarak korunur; çakışan tur token'ı
      iki kez sayılmaz.
  K3  Alt ajan grubunda hook'un tur'u aşan kısmı yoksa artık satırı eklenmez.
  K4  analitik._formul_usd önbellek yazmayı 1 sa tarifesiyle hesaplar.
  K5  Panelden onaylanan kural onayı taban ve uygulama tarihi kancalarını çağırır.
"""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402
import analitik  # noqa: E402
import onay  # noqa: E402
import etki  # noqa: E402

MODEL = "claude-opus-4-8"


def satir(kaynak, oturum, agent_id, giris, cikis, okuma, yazma, zaman="2026-10-15T10:00:00+03:00"):
    return {"zaman": zaman, "oturum": oturum, "gorev": "-", "surec": "is", "ajan": "x", "agent_id": agent_id,
            "model": MODEL, "giris": giris, "cikis": cikis, "onbellek_okuma": okuma, "onbellek_yazma": yazma,
            "maliyet_usd": 0.0, "kaynak": kaynak}


class MaliyetDuzeltme(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        L._MALIYET_ONBELLEK.clear()

    def yaz(self, rows):
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        L._MALIYET_ONBELLEK.clear()
        return L.maliyet_kayitlari(self.sd)

    def test_k1_tur_1sa_tarife(self):
        out = self.yaz([satir("tur", "s1", None, 0, 0, 0, 1_000_000)])
        f = L.model_fiyati(MODEL)
        self.assertAlmostEqual(out[0]["maliyet_usd"], f["onbellek_yazma_1sa"], places=4)
        self.assertGreater(f["onbellek_yazma_1sa"], f["onbellek_yazma_5dk"])

    def test_k2_ana_ajan_artigi(self):
        out = self.yaz([
            satir("hook", "s1", None, 10, 100, 1000, 500, "2026-10-15T09:00:00+03:00"),
            satir("hook", "s1", None, 20, 200, 2000, 600, "2026-10-15T10:00:00+03:00"),
            satir("tur", "s1", None, 20, 200, 2000, 600),
        ])
        artik = [r for r in out if r["kaynak"] == "hook-artik"]
        self.assertEqual(len(artik), 1)
        self.assertEqual((artik[0]["giris"], artik[0]["cikis"], artik[0]["onbellek_okuma"], artik[0]["onbellek_yazma"]),
                         (30, 300, 3000, 1100) if False else (10, 100, 1000, 500))
        self.assertEqual(len([r for r in out if r["kaynak"] == "tur"]), 1)

    def test_k3_artik_yoksa_satir_yok(self):
        out = self.yaz([
            satir("hook", "s1", "a1", 5, 50, 500, 100),
            satir("tur", "s1", "a1", 5, 50, 500, 100),
        ])
        self.assertEqual([r["kaynak"] for r in out], ["tur"])

    def test_k4_formul_1sa(self):
        f = L.model_fiyati(MODEL)
        self.assertAlmostEqual(analitik._formul_usd({"onbellek_yazma": 1_000_000}, MODEL), f["onbellek_yazma_1sa"], places=4)


class KuralEtkiKancasi(unittest.TestCase):
    def test_k5_kural_onayi_kancalari_cagirir(self):
        sd = os.path.join(tempfile.mkdtemp(), "proje", ".claude", "orkestra")
        os.makedirs(sd)
        onay.kural_oner(sd, "Öneri kuralı", "neden", "test")
        onay.esitle(sd)
        bekleyen = [k for k in onay.liste(sd) if k.get("tur") == "kural" and k.get("durum") == "bekliyor"]
        self.assertTrue(bekleyen)
        with mock.patch.object(etki, "kanca_al") as ka, mock.patch.object(etki, "kanca_uygulandi") as ku:
            onay.karar_ver(sd, bekleyen[0]["id"], "onay")
        self.assertEqual(ka.call_count, 1)
        self.assertEqual(ku.call_count, 1)


# ---------------------------------------------------------------- I-030 P3: geriye dönük iş atfı düzeltmesi
#
# Kabul kriterleri (G-155):
#   K1  'orkestra maliyet duzelt' varsayılan kuru koşu (sayı + USD + doldurulamayan + oturum sayısı; dosya yazmaz);
#       '--uygula' maliyet_duzeltme.jsonl'e yalnız ekler.
#   K2  maliyet_kayitlari düzeltmeyi uygular (is boşsa doldurur, doluysa dokunmaz); önbellek imzası düzeltme
#       dosyasını kapsar; ham maliyet.jsonl byte düzeyinde değişmez.
#   K3  Çoklu işe bağlı oturum düzeltilmez; doldurulamayan satır okumada atif_nedeni='oturum-isiz' taşır.
#   K4  Bu dosya.

def _duz_satir(oturum, zaman, usd, gorev="-", agent_id="a1", is_=None):
    r = {"zaman": zaman, "oturum": oturum, "gorev": gorev, "surec": "is", "ajan": "x", "agent_id": agent_id,
         "model": MODEL, "maliyet_usd": usd, "kaynak": "tur"}
    if is_ is not None:
        r["is"] = is_
    return r


def _anahtar(r):
    return "|".join(str(r.get(a)) for a in ("oturum", "zaman", "agent_id", "kaynak", "model"))


class IsAtifDuzeltme(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        L._MALIYET_ONBELLEK.clear()
        self.ham = os.path.join(self.sd, "maliyet.jsonl")
        self.duz = os.path.join(self.sd, "maliyet_duzeltme.jsonl")

    # -- yardımcılar
    def oturum(self, oid, isler):
        os.makedirs(os.path.join(self.sd, "oturumlar"), exist_ok=True)
        with open(os.path.join(self.sd, "oturumlar", f"{oid}.json"), "w", encoding="utf-8") as f:
            json.dump({"is_gecmis": [{"is": i, "zaman": "2026-10-15T08:00:00+03:00"} for i in isler]}, f)

    def kart(self, gid, is_id):
        L.kart_yaz(self.sd, {"id": gid, "is": is_id})

    def deftere_yaz(self, rows):
        with open(self.ham, "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        L._MALIYET_ONBELLEK.clear()

    def kos(self, uygula=False):
        """CLI işleyicisini (komutlar.maliyet.cmd_maliyet_duzelt) durum dizini sabitlenerek çalıştırır; çıktıyı döner."""
        from komutlar import maliyet as KM
        tampon = io.StringIO()
        with mock.patch.object(L, "durum_dizini", return_value=self.sd), contextlib.redirect_stdout(tampon):
            KM.cmd_maliyet_duzelt(argparse.Namespace(uygula=uygula))
        L._MALIYET_ONBELLEK.clear()
        return tampon.getvalue()

    def duzeltmeler(self):
        return L.jsonl_oku(self.duz)

    def ham_bayt(self):
        with open(self.ham, "rb") as f:
            return f.read()

    def agac(self):
        out = {}
        for kok, _, dosyalar in os.walk(self.sd):
            for d in dosyalar:
                y = os.path.join(kok, d)
                with open(y, "rb") as f:
                    out[os.path.relpath(y, self.sd)] = f.read()
        return out

    def senaryo(self):
        """oturum oA: tek iş (I-101) -> 2 satır, 1,25 + 2,50 USD; oB: çoklu iş -> 1 satır 4,00 USD;
        oC: işsiz, iz yok -> 1 satır 0,75 USD; oD: kart yolu G-900 (I-900) -> 1 satır 3,00 USD;
        oE: zaten işli satır (I-777) -> 5,00 USD."""
        self.oturum("oA", ["I-101", "I-101"])
        self.oturum("oB", ["I-201", "I-202"])
        self.kart("G-900", "I-900")
        self.rows = [
            _duz_satir("oA", "2026-10-15T10:00:00+03:00", 1.25),
            _duz_satir("oA", "2026-10-15T10:05:00+03:00", 2.50),
            _duz_satir("oB", "2026-10-15T11:00:00+03:00", 4.00),
            _duz_satir("oC", "2026-10-15T12:00:00+03:00", 0.75),
            _duz_satir("oD", "2026-10-15T13:00:00+03:00", 3.00, gorev="G-900"),
            _duz_satir("oE", "2026-10-15T14:00:00+03:00", 5.00, is_="I-777"),
        ]
        self.deftere_yaz(self.rows)

    # -- K1
    def test_k1_kuru_kosu_hicbir_dosyaya_yazmaz(self):
        self.senaryo()
        once = self.agac()
        self.kos(uygula=False)
        self.assertEqual(self.agac(), once)
        self.assertFalse(os.path.exists(self.duz))

    def test_k1_kuru_kosu_sayilari_yazar(self):
        self.senaryo()
        cikti = self.kos(uygula=False)
        # düzeltilebilir: oA 2 satır + G-900 1 satır = 3 satır, 6,75 USD, 2 oturum (oA, oD)
        # doldurulamayan: oB 1 satır 4,00 + oC 1 satır 0,75 = 2 satır, 4,75 USD
        duz = cikti.replace(",", ".")
        for beklenen in ("3", "6.75", "2", "4.75"):
            self.assertIn(beklenen, duz, f"kuru koşu çıktısında {beklenen} yok:\n{cikti}")
        self.assertRegex(cikti, r"20\d\d-\d\d-\d\d", "ölçüm saati/tarihi yazılmalı")

    def test_k1_varsayilan_uygula_degildir(self):
        from komutlar import maliyet as KM
        ana = argparse.ArgumentParser()
        KM.kaydet(ana.add_subparsers(dest="komut"))
        a = ana.parse_args(["maliyet", "duzelt"])
        self.assertFalse(a.uygula)
        self.assertTrue(ana.parse_args(["maliyet", "duzelt", "--uygula"]).uygula)

    def test_k1_uygula_yalniz_ekler(self):
        self.senaryo()
        self.kos(uygula=True)
        d = self.duzeltmeler()
        self.assertEqual(len(d), 3)
        for e in d:
            for alan in ("anahtar", "is", "kaynak", "zaman"):
                self.assertTrue(e.get(alan), f"{alan} eksik: {e}")
            self.assertIn(e["kaynak"], ("kart", "oturum"))
        eslesme = {e["anahtar"]: (e["is"], e["kaynak"]) for e in d}
        self.assertEqual(eslesme[_anahtar(self.rows[0])], ("I-101", "oturum"))
        self.assertEqual(eslesme[_anahtar(self.rows[1])], ("I-101", "oturum"))
        self.assertEqual(eslesme[_anahtar(self.rows[4])], ("I-900", "kart"))
        ilk = open(self.duz, "rb").read()
        self.kos(uygula=True)
        self.assertEqual(open(self.duz, "rb").read(), ilk)

    def test_k1_tekrar_uygula_cogaltmaz(self):
        self.senaryo()
        self.kos(uygula=True)
        self.kos(uygula=True)
        self.kos(uygula=True)
        self.assertEqual(len(self.duzeltmeler()), 3)

    def test_k1_mevcut_duzeltme_korunur_yeni_satir_eklenir(self):
        self.senaryo()
        self.kos(uygula=True)
        once = open(self.duz, "rb").read()
        yeni = _duz_satir("oF", "2026-10-15T15:00:00+03:00", 1.00)
        self.oturum("oF", ["I-300"])
        self.deftere_yaz(self.rows + [yeni])
        self.kos(uygula=True)
        self.assertTrue(open(self.duz, "rb").read().startswith(once))
        self.assertEqual(len(self.duzeltmeler()), 4)

    # -- K2
    def test_k2_okuma_bos_isi_doldurur(self):
        self.senaryo()
        self.kos(uygula=True)
        out = {(r["oturum"], r["zaman"]): r for r in L.maliyet_kayitlari(self.sd)}
        self.assertEqual(out[("oA", "2026-10-15T10:00:00+03:00")]["is"], "I-101")
        self.assertEqual(out[("oA", "2026-10-15T10:05:00+03:00")]["is"], "I-101")
        self.assertEqual(out[("oD", "2026-10-15T13:00:00+03:00")]["is"], "I-900")

    def test_k2_dolu_is_degismez(self):
        self.senaryo()
        sahte = {"anahtar": _anahtar(self.rows[5]), "is": "I-999", "kaynak": "oturum", "zaman": "2026-10-16T09:00:00+03:00"}
        with open(self.duz, "w", encoding="utf-8") as f:
            f.write(json.dumps(sahte) + "\n")
        L._MALIYET_ONBELLEK.clear()
        out = {r["oturum"]: r for r in L.maliyet_kayitlari(self.sd)}
        self.assertEqual(out["oE"]["is"], "I-777")

    def test_k2_kart_oturumdan_once_gelir(self):
        self.oturum("oX", ["I-2"])
        self.kart("G-901", "I-1")
        self.deftere_yaz([_duz_satir("oX", "2026-10-15T10:00:00+03:00", 1.0, gorev="G-901")])
        self.kos(uygula=True)
        self.assertEqual([(e["is"], e["kaynak"]) for e in self.duzeltmeler()], [("I-1", "kart")])

    def test_k2_onbellek_imzasi_duzeltme_dosyasini_kapsar(self):
        self.senaryo()
        once = L.maliyet_kayitlari(self.sd)  # önbelleği doldurur (düzeltme yok)
        self.assertTrue(all(not r.get("is") for r in once if r["oturum"] == "oA"))
        r0 = self.rows[0]
        with open(self.duz, "a", encoding="utf-8") as f:  # ham dosya aynı; önbellek SIFIRLANMAZ
            f.write(json.dumps({"anahtar": _anahtar(r0), "is": "I-101", "kaynak": "oturum",
                                "zaman": "2026-10-16T09:00:00+03:00"}) + "\n")
        sonra = [r for r in L.maliyet_kayitlari(self.sd) if r["oturum"] == "oA" and r["zaman"] == r0["zaman"]]
        self.assertEqual(sonra[0].get("is"), "I-101")

    def test_k2_ham_dosya_bayt_duzeyinde_degismez(self):
        self.senaryo()
        once = self.ham_bayt()
        self.kos(uygula=False)
        self.kos(uygula=True)
        L.maliyet_kayitlari(self.sd)
        self.assertEqual(self.ham_bayt(), once)

    def test_k2_toplam_usd_degismez(self):
        self.senaryo()
        oncesi = sum(r["maliyet_usd"] for r in L.maliyet_kayitlari(self.sd))
        self.kos(uygula=True)
        sonrasi = L.maliyet_kayitlari(self.sd)
        self.assertEqual(len(sonrasi), len(self.rows))
        self.assertAlmostEqual(sum(r["maliyet_usd"] for r in sonrasi), oncesi, places=9)
        self.assertAlmostEqual(oncesi, 16.5, places=9)

    def test_k2_bozuk_duzeltme_satiri_okumayi_bozmaz(self):
        self.senaryo()
        with open(self.duz, "w", encoding="utf-8") as f:
            f.write("{bozuk\n" + json.dumps({"anahtar": "yok|yok|yok|yok|yok", "is": "I-1", "kaynak": "kart",
                                             "zaman": "z"}) + "\n")
        L._MALIYET_ONBELLEK.clear()
        self.assertEqual(len(L.maliyet_kayitlari(self.sd)), len(self.rows))

    def test_k2_duzeltme_dosyasi_yoksa_eski_davranis(self):
        self.senaryo()
        out = L.maliyet_kayitlari(self.sd)
        self.assertEqual(len(out), len(self.rows))
        self.assertEqual(next(r for r in out if r["oturum"] == "oE")["is"], "I-777")

    # -- K3
    def test_k3_coklu_is_duzeltilmez(self):
        self.senaryo()
        self.kos(uygula=True)
        anahtarlar = {e["anahtar"] for e in self.duzeltmeler()}
        self.assertNotIn(_anahtar(self.rows[2]), anahtarlar)  # oB: I-201 + I-202
        self.assertNotIn(_anahtar(self.rows[3]), anahtarlar)  # oC: iz yok
        out = {r["oturum"]: r for r in L.maliyet_kayitlari(self.sd)}
        self.assertFalse(out["oB"].get("is"))

    def test_k3_coklu_is_zaman_bazli_cozulur(self):
        """Çok işli oturumda satır, kendi zamanındaki bağlanmayla çözülür; ilk bağlanmadan önceki satır çözülmez."""
        os.makedirs(os.path.join(self.sd, "oturumlar"), exist_ok=True)
        with open(os.path.join(self.sd, "oturumlar", "oZ.json"), "w", encoding="utf-8") as f:
            json.dump({"is_gecmis": [{"is": "I-301", "zaman": "2026-10-15T08:00:00+03:00"},
                                     {"is": "I-302", "zaman": "2026-10-15T09:00:00+03:00"}]}, f)
        self.deftere_yaz([_duz_satir("oZ", "2026-10-15T07:00:00+03:00", 1.0),
                          _duz_satir("oZ", "2026-10-15T08:30:00+03:00", 2.0),
                          _duz_satir("oZ", "2026-10-15T09:30:00+03:00", 3.0)])
        self.kos(uygula=True)
        out = {r["maliyet_usd"]: r.get("is") for r in L.maliyet_kayitlari(self.sd)}
        self.assertFalse(out[1.0])
        self.assertEqual(out[2.0], "I-301")
        self.assertEqual(out[3.0], "I-302")

    def test_k3_doldurulamayan_oturum_isiz_etiketi(self):
        self.senaryo()
        self.kos(uygula=True)
        out = {r["oturum"]: r for r in L.maliyet_kayitlari(self.sd)}
        self.assertEqual(out["oB"].get("atif_nedeni"), "oturum-isiz")
        self.assertEqual(out["oC"].get("atif_nedeni"), "oturum-isiz")
        for o in ("oA", "oD", "oE"):
            self.assertNotEqual(out[o].get("atif_nedeni"), "oturum-isiz", o)

    def test_k3_etiket_dosyaya_yazilmaz(self):
        self.senaryo()
        self.kos(uygula=True)
        L.maliyet_kayitlari(self.sd)
        self.assertNotIn(b"atif_nedeni", self.ham_bayt())
        self.assertNotIn(b"atif_nedeni", open(self.duz, "rb").read())

    def test_k3_oturum_json_yoksa_dokunulmaz(self):
        self.deftere_yaz([_duz_satir("oY", "2026-10-15T10:00:00+03:00", 1.0)])
        self.kos(uygula=True)
        self.assertEqual(self.duzeltmeler(), [])
        self.assertEqual(L.maliyet_kayitlari(self.sd)[0].get("atif_nedeni"), "oturum-isiz")

    def test_k3_bos_defter(self):
        self.deftere_yaz([])
        self.assertTrue(self.kos(uygula=False).strip())
        self.kos(uygula=True)
        self.assertEqual(self.duzeltmeler(), [])

    def test_k3_defter_hic_yoksa_hata_vermez(self):
        self.kos(uygula=False)
        self.kos(uygula=True)
        self.assertFalse(os.path.exists(self.ham))


if __name__ == "__main__":
    unittest.main()
