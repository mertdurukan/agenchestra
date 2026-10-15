"""G-039: zaman.jsonl (T-06) ve işin oturumlar.md satırı (T-07).

`py -3.13 -m pytest plugins/orkestra/tests/test_zaman_oturum.py -q -p no:cacheprovider`

- Stop: zaman.jsonl'e tur='ana' satırı (sure_ms = turun ilk->son transkript zamanı, is = oturumun işi).
- SubagentStop: tur='alt' satırı (agent_id, ajan, gorev, sure_ms, is).
- SessionEnd: oturum işe bağlıysa işin klasöründeki oturumlar.md SONUNA tek satır; yoksa/işsizse yazmaz, dosya oluşturmaz,
  mevcut içeriği korur, bozuk kayıtta çökmez ve eksik alanı '-' yazar.
Not (mevcut kod taraması): main ve bu ağaçta oturumlar.md'yi SessionEnd'de yazan bir yol yoktur (yalnız orkestra.py okur,
is_kaydi şablonu başlığı oluşturur); bu yüzden kriter 3 kırmızıdır.
Hepsi geçici projede koşar; niyet kaydı geçici dizine yönlenir.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import is_kaydi  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402

OTURUM = "11112222-aaaa-bbbb-cccc-333344445555"
KISA = OTURUM[:8]
AID = "ajan-zaman-1"
BASLIK = "# Oturumlar — Deneme işi\n\n"


def _jsonl(yol, satirlar):
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        for s in satirlar:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _kullanici(metin, ts):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": metin}}


def _asistan(ts, mid="m1"):
    return {"type": "assistant", "timestamp": ts,
            "message": {"id": mid, "model": "claude-haiku-5-5", "content": [{"type": "text", "text": "tamam"}],
                        "usage": {"input_tokens": 10, "output_tokens": 5}}}


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_zaman_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        for a in ("oturumlar", "gorevler"):
            os.makedirs(os.path.join(self.sd, a))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        self.atr = os.path.join(self.proje, "agent.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        yol = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self.niyet_yolu = yol
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", yol),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(yol)),
                   mock.patch.object(niyet, "_gecici", return_value=False),
                   mock.patch.object(perspektif, "durum", return_value={"zamani_geldi": False, "calisiyor": False})]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def kos(self, fn, girdi=None):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr}
        g.update(girdi or {})
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            fn(g)

    def oturum_yaz(self, **alanlar):
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            json.dump(alanlar, f)

    def zaman(self):
        return L.jsonl_oku(os.path.join(self.sd, "zaman.jsonl"))

    def is_ac(self, alt="is1"):
        k = is_kaydi.is_ac(self.sd, "Deneme işi", os.path.join(self.proje, alt))
        self.oturum_yaz(**{"is": k["id"]})
        return k["id"], os.path.join(self.proje, alt, "oturumlar.md")


class ZamanAna(_Ortak):
    def test_stop_ana_tur_satiri(self):
        _jsonl(self.tr, [_kullanici("merhaba", "2026-10-14T10:00:00Z"), _asistan("2026-10-14T10:00:07Z")])
        self.oturum_yaz(**{"is": "I-004"})
        self.kos(hook.stop)
        s = [r for r in self.zaman() if r.get("tur") == "ana"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["sure_ms"], 7000)
        self.assertEqual(s[0]["oturum"], OTURUM)
        self.assertEqual(s[0]["is"], "I-004")
        self.assertTrue(s[0].get("zaman"))

    def test_stop_isiz_oturumda_is_bos(self):
        _jsonl(self.tr, [_kullanici("merhaba", "2026-10-14T10:00:00Z"), _asistan("2026-10-14T10:00:03Z")])
        self.kos(hook.stop)
        s = [r for r in self.zaman() if r.get("tur") == "ana"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["sure_ms"], 3000)
        self.assertIsNone(s[0].get("is"))

    def test_iki_stop_iki_satir_ikinci_tur_yeni_surede(self):
        _jsonl(self.tr, [_kullanici("bir", "2026-10-14T10:00:00Z"), _asistan("2026-10-14T10:00:04Z", "m1")])
        self.kos(hook.stop)
        with open(self.tr, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(_kullanici("iki", "2026-10-14T10:05:00Z")) + "\n")
            f.write(json.dumps(_asistan("2026-10-14T10:05:09Z", "m2")) + "\n")
        self.kos(hook.stop)
        sureler = [r["sure_ms"] for r in self.zaman() if r.get("tur") == "ana"]
        self.assertEqual(sureler, [4000, 9000])

    def test_bozuk_transkript_stop_cokmez(self):
        with open(self.tr, "w", encoding="utf-8") as f:
            f.write("{bozuk\n\x00\n")
        self.kos(hook.stop)  # SystemExit dışında istisna testi düşürür


class ZamanAlt(_Ortak):
    def test_subagent_stop_alt_satiri(self):
        _jsonl(self.atr, [_kullanici("#GOREV:G-007 #SUREC:is\nişi yap", "2026-10-14T10:00:00Z"), _asistan("2026-10-14T10:02:00Z")])
        self.oturum_yaz(**{"is": "I-004"})
        self.kos(hook.subagent_stop, {"agent_id": AID, "agent_type": "orkestra:isci-t2", "agent_transcript_path": self.atr})
        s = [r for r in self.zaman() if r.get("tur") == "alt"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["agent_id"], AID)
        self.assertEqual(s[0]["ajan"], "orkestra:isci-t2")
        self.assertEqual(s[0]["gorev"], "G-007")
        self.assertEqual(s[0]["sure_ms"], 120000)
        self.assertEqual(s[0]["oturum"], OTURUM)
        self.assertEqual(s[0]["is"], "I-004")

    def test_eksik_alt_transkript_cokmez_ve_satir_yazar(self):
        self.kos(hook.subagent_stop, {"agent_id": AID, "agent_type": "Explore",
                                      "agent_transcript_path": os.path.join(self.proje, "yok.jsonl")})
        s = [r for r in self.zaman() if r.get("tur") == "alt"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["agent_id"], AID)
        self.assertIsNone(s[0]["sure_ms"])


class OturumSatiri(_Ortak):
    def maliyet(self, satirlar):
        for r in satirlar:
            L.jsonl_ekle(os.path.join(self.sd, "maliyet.jsonl"), r)

    def zaman_yaz(self, ana_ms=(60000, 60000), alt_ms=(300000,)):
        for ms in ana_ms:
            L.jsonl_ekle(os.path.join(self.sd, "zaman.jsonl"), {"zaman": L.simdi(), "oturum": OTURUM, "tur": "ana", "sure_ms": ms})
        for i, ms in enumerate(alt_ms):
            L.jsonl_ekle(os.path.join(self.sd, "zaman.jsonl"),
                         {"zaman": L.simdi(), "oturum": OTURUM, "tur": "alt", "agent_id": f"a{i}", "sure_ms": ms})
        # başka oturum süzülmeli
        L.jsonl_ekle(os.path.join(self.sd, "zaman.jsonl"), {"zaman": L.simdi(), "oturum": "baska", "tur": "ana", "sure_ms": 999999999})

    def maliyet_yaz(self):
        t = {"zaman": "2026-10-14T10:00:00+03:00", "gorev": "-", "surec": "is", "model": "claude-haiku-5-5",
             "onbellek_okuma": 0, "onbellek_yazma": 0, "kaynak": "hook"}
        self.maliyet([
            dict(t, oturum=OTURUM, agent_id=None, giris=100, cikis=50, maliyet_usd=0.4),
            # aynı ajan iki kez (birikimli) -> yalnız son kalır
            dict(t, oturum=OTURUM, agent_id="x1", zaman="2026-10-14T10:01:00+03:00", giris=1000, cikis=1000, maliyet_usd=9.0),
            dict(t, oturum=OTURUM, agent_id="x1", zaman="2026-10-14T10:02:00+03:00", giris=10, cikis=0, maliyet_usd=0.02),
            dict(t, oturum="baska", agent_id=None, giris=5000, cikis=5000, maliyet_usd=7.0),
        ])
        # beklenen oturum toplamı: 150 + 10 = 160 token, 0.42 $

    def niyet_yaz(self, ne="Ölçüm kancası ekle", sonuc=None):
        niyet.olay(OTURUM, self.proje, "niyet", ne=ne, neden="test")
        if sonuc:
            niyet.olay(OTURUM, self.proje, "sonuc", sonuc=sonuc)

    def bitir(self):
        self.kos(hook.session_end)

    def test_isi_bagli_oturum_tam_bir_satir_ekler(self):
        i, md = self.is_ac()
        self.zaman_yaz()
        self.maliyet_yaz()
        self.niyet_yaz(sonuc="kanca yazıldı, testler yeşil")
        onceki = open(md, encoding="utf-8").read()
        self.assertEqual(onceki, BASLIK)
        self.bitir()
        yeni = open(md, encoding="utf-8", newline="").read()
        self.assertTrue(yeni.startswith(onceki), "mevcut içerik korunmalı")
        ek = yeni[len(onceki):]
        self.assertTrue(ek.endswith("\n") and ek.count("\n") == 1, f"tam bir satır beklenir: {ek!r}")
        self.assertNotIn("\r", yeni)
        satir = ek.strip()
        self.assertTrue(satir.startswith("- "))
        self.assertRegex(satir, r"^- \d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")
        self.assertIn(f"oturum {KISA}", satir)
        self.assertNotIn(OTURUM, satir)  # kısa id
        self.assertRegex(satir, r"Claude süresi 2\b")    # 60000+60000 ms = 2 dk
        self.assertRegex(satir, r"alt ajan süresi 5\b")  # 300000 ms = 5 dk
        self.assertRegex(satir, r"· 160 token")
        self.assertRegex(satir, r"· \$0\.42\b")
        self.assertIn("ne: Ölçüm kancası ekle", satir)
        self.assertIn("sonuç/nerede kalındı: kanca yazıldı, testler yeşil", satir)

    def test_sonuc_yoksa_son_niyet_yazilir(self):
        i, md = self.is_ac()
        self.zaman_yaz()
        self.maliyet_yaz()
        self.niyet_yaz(ne="Yarım kalan iş")
        self.bitir()
        satir = open(md, encoding="utf-8").read().splitlines()[-1]
        self.assertIn("ne: Yarım kalan iş", satir)
        self.assertIn("Yarım kalan iş", satir.split("sonuç/nerede kalındı:")[1])

    def test_mevcut_satirlardan_sonra_eklenir_onlari_bozmaz(self):
        i, md = self.is_ac()
        with open(md, "a", encoding="utf-8", newline="\n") as f:
            f.write("- eski satır\n")
        self.zaman_yaz()
        self.maliyet_yaz()
        self.niyet_yaz()
        self.bitir()
        satirlar = open(md, encoding="utf-8").read().splitlines()
        self.assertEqual(satirlar[:3], ["# Oturumlar — Deneme işi", "", "- eski satır"])
        self.assertEqual(len(satirlar), 4)

    def test_eksik_alanlar_tire_yazar_ve_cokmez(self):
        i, md = self.is_ac()  # zaman/maliyet/niyet kaydı yok
        self.bitir()
        yeni = open(md, encoding="utf-8").read()
        satir = yeni[len(BASLIK):].strip()
        self.assertEqual(len(satir.splitlines()), 1, satir)
        self.assertIn(f"oturum {KISA}", satir)
        self.assertRegex(satir, r"Claude süresi -( |$)")
        self.assertRegex(satir, r"alt ajan süresi -( |$)")
        self.assertRegex(satir, r"ne: -( |$)")
        self.assertRegex(satir, r"sonuç/nerede kalındı: -$")

    def test_bozuk_zaman_ve_maliyet_satirlari_cokmez(self):
        i, md = self.is_ac()
        with open(os.path.join(self.sd, "zaman.jsonl"), "w", encoding="utf-8") as f:
            f.write("{bozuk\n" + json.dumps({"oturum": OTURUM, "tur": "ana", "sure_ms": None}) + "\n"
                    + json.dumps({"oturum": OTURUM, "tur": "ana", "sure_ms": "abc"}) + "\n"
                    + json.dumps({"oturum": OTURUM, "tur": "ana", "sure_ms": 180000}) + "\n")
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
            f.write("{bozuk\n" + json.dumps({"oturum": OTURUM, "agent_id": None, "giris": None, "cikis": "x"}) + "\n")
        self.bitir()
        satir = open(md, encoding="utf-8").read()[len(BASLIK):].strip()
        self.assertEqual(len(satir.splitlines()), 1)
        self.assertRegex(satir, r"Claude süresi 3\b")  # geçerli satır sayılır, bozuklar atlanır

    def test_is_baglanmamis_oturum_dosya_yazmaz(self):
        is_kaydi.is_ac(self.sd, "Deneme işi", os.path.join(self.proje, "is1"))
        md = os.path.join(self.proje, "is1", "oturumlar.md")
        self.oturum_yaz(ofset=5)
        self.zaman_yaz()
        self.maliyet_yaz()
        self.niyet_yaz()
        self.bitir()
        self.assertEqual(open(md, encoding="utf-8").read(), BASLIK)
        self.assertTrue(os.path.exists(os.path.join(self.sd, "zaman.jsonl")))  # test önkoşulu: veri vardı

    def test_oturum_dosyasi_hic_yokken_yazmaz_ve_cokmez(self):
        is_kaydi.is_ac(self.sd, "Deneme işi", os.path.join(self.proje, "is1"))
        md = os.path.join(self.proje, "is1", "oturumlar.md")
        self.bitir()
        self.assertEqual(open(md, encoding="utf-8").read(), BASLIK)

    def test_oturumlar_md_yoksa_olusturulmaz(self):
        i, md = self.is_ac()
        os.remove(md)
        self.zaman_yaz()
        self.maliyet_yaz()
        self.niyet_yaz()
        self.bitir()
        self.assertFalse(os.path.exists(md))

    def test_bilinmeyen_is_kimligi_cokmez(self):
        self.oturum_yaz(**{"is": "I-999"})
        self.bitir()
        self.assertFalse([f for f in os.listdir(self.proje) if f.endswith(".md")])

    def test_bozuk_oturum_dosyasi_cokmez(self):
        i, md = self.is_ac()
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.bitir()
        self.assertEqual(open(md, encoding="utf-8").read(), BASLIK)

    def test_yazma_hatasi_kancayi_cokertmez(self):
        i, md = self.is_ac()
        self.zaman_yaz()
        with mock.patch.object(L, "sona_ekle", side_effect=PermissionError("kilitli")):
            self.bitir()  # SystemExit dışında istisna testi düşürür

    def test_perspektif_oturumu_yazmaz(self):
        i, md = self.is_ac()
        self.zaman_yaz()
        with mock.patch.dict(os.environ, {"ORKESTRA_PERSPEKTIF": "1"}):
            self.bitir()
        self.assertEqual(open(md, encoding="utf-8").read(), BASLIK)


if __name__ == "__main__":
    unittest.main()
