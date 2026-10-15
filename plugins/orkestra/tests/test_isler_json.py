"""İş şeridi 3a (G-033): todo 'alt' maddeleri, is_adi, panel GET /isler.json ve /isler sayfası."""
import http.client
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import ork_lib as L  # noqa: E402
import is_kaydi as IK  # noqa: E402
import panel  # noqa: E402

KOVALAR = ("yapildi", "simdi", "sirada", "planda_kart_yok", "iptal")
TODO = """# Yapılacaklar

## Altyapı
- [ ] **Ana** madde G4
  - **ilk** alt `kod` → çıktı: x
  - ikinci alt
    - derin alt
- [ ] alt satırsız madde
- [x] biten madde
  - biten alt
"""


class IsAdi(unittest.TestCase):
    # kriter 4
    def test_jira_kodlu(self):
        self.assertEqual(IK.is_adi("001-20261013-PE-636-langfuse-erken-uyari"), "PE-636 langfuse erken uyari")

    def test_jirasiz(self):
        self.assertEqual(IK.is_adi("003-20261013-orkestra-acik-maddeler"), "orkestra acik maddeler")

    def test_oneksiz_aynen(self):
        self.assertEqual(IK.is_adi("Orkestra açık maddeler (x.md)"), "Orkestra açık maddeler (x.md)")

    def test_bos(self):
        self.assertEqual(IK.is_adi(""), "")


class TodoAlt(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = self.t.name

    def tearDown(self):
        self.t.cleanup()

    def yaz(self, metin):
        with open(os.path.join(self.d, "todo.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    # kriter 3
    def test_alt_listesi_temiz_ve_duz(self):
        self.yaz(TODO)
        m = IK.todo_maddeleri(self.d)
        self.assertEqual(m[0]["alt"], ["ilk alt kod", "ikinci alt", "derin alt"])
        self.assertEqual(m[1]["alt"], [])
        self.assertEqual(m[2]["alt"], ["biten alt"])

    def test_alt_en_cok_8_ve_100_karakter(self):
        self.yaz("- [ ] ana\n" + "".join(f"  - alt {i}\n" for i in range(12)))
        alt = IK.todo_maddeleri(self.d)[0]["alt"]
        self.assertEqual(len(alt), 8)
        self.assertEqual(alt[0], "alt 0")
        self.yaz("- [ ] ana\n  - " + "b" * 300 + "\n")
        t = IK.todo_maddeleri(self.d)[0]["alt"][0]
        self.assertLessEqual(len(t), 100)
        self.assertTrue(t.endswith("…"))

    def test_alt_sonraki_maddeye_tasmaz(self):
        self.yaz("- [ ] bir\n- [ ] iki\n  - iki-alt\n")
        m = IK.todo_maddeleri(self.d)
        self.assertEqual([x["alt"] for x in m], [[], ["iki-alt"]])

    def test_mevcut_anahtarlar_korunur(self):
        self.yaz(TODO)
        m = IK.todo_maddeleri(self.d)[0]
        for a in ("durum", "metin", "adimlar", "bolum"):
            self.assertIn(a, m)
        self.assertEqual(m["metin"], "Ana madde G4")
        self.assertEqual(IK.todo_ozet(self.d)["biten"], 1)


class PanelIsler(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        yok = os.path.join(self.t.name, "orkestrasiz")
        os.makedirs(yok)
        self.yok = {"id": "alan-y", "ad": "o", "yol": yok, "orkestra": False, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [self.yok, self.alan])
        self.yama.start()
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.yama.stop()
        self.t.cleanup()

    def kart(self, gid, **alan):
        k = {"id": gid, "baslik": f"kart {gid}", "basamak": "T1", "durum": "planlandi", "bagimliliklar": []}
        k.update(alan)
        d = os.path.join(self.sd, "gorevler")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{gid}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(k, f, ensure_ascii=False)

    def maliyet(self, *satirlar):
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            for i, (gorev, usd) in enumerate(satirlar):
                f.write(json.dumps({"gorev": gorev, "maliyet_usd": usd, "oturum": f"o{i}", "agent_id": "",
                                    "zaman": "2026-10-14T10:00:00Z"}) + "\n")

    def is_ac(self, ad, todo=None):
        klasor = os.path.join(self.proje, "RNV", ad)
        k = IK.is_ac(self.sd, ad, klasor)
        if todo is not None:
            with open(os.path.join(klasor, "todo.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(todo)
        return k["id"]

    def get(self, yol):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", yol)
        r = c.getresponse()
        b = r.read()
        c.close()
        return r.status, b

    def getj(self, yol):
        k, b = self.get(yol)
        self.assertEqual(k, 200)
        return json.loads(b)

    def kur_iki_is(self):
        self.a = self.is_ac("001-20261013-PE-636-acik-is", TODO)
        self.b = self.is_ac("002-20261013-kapali-is", "- [x] bitti\n")
        self.kart("G-001", **{"is": self.a, "adim": "G4", "durum": "isleniyor",
                              "guncelleme": "2026-10-14T09:00:00Z", "bagimliliklar": ["G-002"]})
        self.kart("G-002", **{"is": self.a, "adim": "G5", "durum": "teslim", "teslim_ozeti": "bitti özet",
                              "guncelleme": "2026-10-14T12:00:00Z"})
        self.kart("G-003", **{"is": self.b, "durum": "teslim", "guncelleme": "2026-10-13T08:00:00Z"})
        IK.is_durum(self.sd, self.b, "kapandi")
        self.maliyet(("G-001", 0.1234), ("G-001", 0.2), ("G-002", 0.05), ("G-003", 9.0), ("G-099", 5.0), ("-", 3.0))

    # kriter 1
    def test_sozlesme_anahtarlari_ve_siralama(self):
        self.kur_iki_is()
        o = self.getj("/isler.json?alan=alan-x")
        self.assertTrue(o["acik"])
        self.assertEqual(o["alan"], {"id": "alan-x", "ad": "proje", "yol": self.proje})
        self.assertIn("uretim", o)
        self.assertEqual(set(o["kartsiz"]), {"sayi", "acik"})
        self.assertEqual([i["id"] for i in o["isler"]], [self.a, self.b])
        self.assertEqual([i["durum"] for i in o["isler"]], ["acik", "kapandi"])
        i = o["isler"][0]
        for a in ("id", "baslik", "ad", "durum", "klasor", "ilerleme", "usd", "son", "kovalar"):
            self.assertIn(a, i)
        self.assertEqual(i["baslik"], "001-20261013-PE-636-acik-is")
        self.assertEqual(i["ad"], "PE-636 acik is")
        self.assertEqual(i["ilerleme"], {"biten": 1, "toplam": 3})
        self.assertEqual(set(i["kovalar"]), set(KOVALAR))

    def test_kovalar_is_serit_ile_ayni_ve_kart_ogeleri_zengin(self):
        self.kur_iki_is()
        o = self.getj("/isler.json?alan=alan-x")
        i = o["isler"][0]
        seridi = IK.is_serit(self.sd, self.a)
        for kova in KOVALAR:
            es = i["kovalar"][kova]
            beklenen = seridi[kova]
            self.assertEqual(len(es), len(beklenen), kova)
            for e, b in zip(es, beklenen):
                for anahtar, deger in b.items():
                    self.assertEqual(e[anahtar], deger, (kova, anahtar))
                if e["tur"] == "kart":
                    self.assertEqual(e["basamak"], "T1")
                    self.assertIn("usd", e)
                else:
                    self.assertIn("alt", e)
        kartlar = [e for k in KOVALAR for e in i["kovalar"][k] if e["tur"] == "kart"]
        self.assertEqual({e["kart"] for e in kartlar}, {"G-001", "G-002"})
        usd = {e["kart"]: e["usd"] for e in kartlar}
        self.assertAlmostEqual(usd["G-001"], 0.3234, places=4)
        self.assertAlmostEqual(usd["G-002"], 0.05, places=4)

    # kriter 2
    def test_is_usd_yalniz_kendi_kartlari(self):
        self.kur_iki_is()
        o = self.getj("/isler.json?alan=alan-x")
        self.assertAlmostEqual(o["isler"][0]["usd"], 0.3734, places=4)
        self.assertAlmostEqual(o["isler"][1]["usd"], 9.0, places=4)

    def test_son_en_yeni_kart_guncellemesi_ya_da_olusturma(self):
        self.kur_iki_is()
        c = self.is_ac("003-20261013-kartsiz-is")
        o = self.getj("/isler.json?alan=alan-x")
        s = {i["id"]: i for i in o["isler"]}
        self.assertEqual(s[self.a]["son"], "2026-10-14T12:00:00Z")
        self.assertEqual(s[self.b]["son"], "2026-10-13T08:00:00Z")
        self.assertEqual(s[c]["son"], IK.is_al(self.sd, c)["olusturma"])
        self.assertEqual(s[c]["usd"], 0)

    # kriter 3
    def test_madde_ogesinde_alt(self):
        self.kur_iki_is()
        i = self.getj("/isler.json?alan=alan-x")["isler"][0]
        maddeler = [e for k in KOVALAR for e in i["kovalar"][k] if e["tur"] == "madde"]
        ana = next(e for e in maddeler if e["metin"].startswith("Ana madde"))
        self.assertEqual(ana["alt"], ["ilk alt kod", "ikinci alt", "derin alt"])
        bos = next(e for e in maddeler if e["metin"] == "alt satırsız madde")
        self.assertEqual(bos["alt"], [])

    # kriter 5
    def test_kartsiz_kartlar(self):
        self.kur_iki_is()
        self.kart("G-010", durum="planlandi", basamak="T2")
        self.kart("G-011", durum="teslim")
        self.kart("G-012", durum="iptal")
        self.maliyet(("G-010", 0.5))
        o = self.getj("/isler.json?alan=alan-x")
        ks = o["kartsiz"]
        self.assertEqual(ks["sayi"], 3)
        self.assertEqual([k["kart"] for k in ks["acik"]], ["G-010"])
        k = ks["acik"][0]
        self.assertEqual(set(k), {"kart", "baslik", "durum", "basamak", "usd"})
        self.assertEqual(k["basamak"], "T2")
        self.assertAlmostEqual(k["usd"], 0.5, places=4)

    def test_kartsiz_yok(self):
        self.kur_iki_is()
        o = self.getj("/isler.json?alan=alan-x")
        self.assertEqual(o["kartsiz"], {"sayi": 0, "acik": []})

    def test_bos_alan(self):
        o = self.getj("/isler.json?alan=alan-x")
        self.assertTrue(o["acik"])
        self.assertEqual(o["isler"], [])
        self.assertEqual(o["kartsiz"], {"sayi": 0, "acik": []})

    # hata dayanıklılığı
    def test_bozuk_is_bos_kovali_hata_ile_doner(self):
        self.kur_iki_is()
        gercek = IK.todo_maddeleri

        def bozuk(klasor):
            if os.path.basename(klasor).startswith("001"):
                raise OSError("okunamadi")
            return gercek(klasor)

        with mock.patch.object(IK, "todo_maddeleri", bozuk):
            k, b = self.get("/isler.json?alan=alan-x")
        self.assertEqual(k, 200)
        o = json.loads(b)
        self.assertTrue(o["acik"])
        s = {i["id"]: i for i in o["isler"]}
        self.assertTrue(s[self.a].get("hata"))
        for kova in KOVALAR:
            self.assertEqual(s[self.a]["kovalar"][kova], [])
        self.assertNotIn("hata", s[self.b])

    # kriter 6
    def test_orkestrasiz_alan(self):
        o = self.getj("/isler.json?alan=alan-y")
        self.assertFalse(o["acik"])
        self.assertIn("hata", o)

    def test_sayfa_hazirlaniyor(self):
        with mock.patch.object(panel, "ASSETS", os.path.join(self.t.name, "yok_assets")):
            for yol in ("/isler", "/isler.html"):
                k, b = self.get(yol)
                self.assertEqual(k, 200, yol)
                self.assertIn("hazırlanıyor".encode("utf-8"), b)

    # kriter 7
    def test_sayfalar_kaydi_ve_surum(self):
        self.assertEqual(panel.SAYFALAR.get("/isler"), "isler.html")
        self.assertEqual(panel.SAYFALAR.get("/isler.html"), "isler.html")
        self.assertEqual(panel.SURUM, "9")

    def test_onbellek_2sn(self):
        self.kur_iki_is()
        ilk = self.getj("/isler.json?alan=alan-x")
        self.is_ac("009-20261014-sonradan")
        ikinci = self.getj("/isler.json?alan=alan-x")
        self.assertEqual(len(ilk["isler"]), 2)
        self.assertEqual(len(ikinci["isler"]), 2)


if __name__ == "__main__":
    unittest.main()
