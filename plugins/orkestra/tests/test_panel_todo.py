"""panel.py Yapılacaklar uçları (GET/POST /api/todo) ve arayüz (G-084).

Sunucu süreç içinde açılır; panel.calistir/baslat kullanılmaz, panel.json'a dokunulmaz.
Sözleşme: iş todo listeleri salt okunur (POST /api/todo -> 405). Kullanıcının kendi listesi:
  POST /api/kullanici-todo?alan=<alan>: {"eylem": "ekle", "metin": "..."}  |  {"eylem": "sil", "id": "K1"}
  GET /api/kullanici-todo?alan=<alan> -> {"acik": true, "maddeler": [{"id","metin","zaman"}]}
GET /api/todo?alan=<alan>[&is=<id>] -> {"acik": true, "is": "<id>", "isler": [{"id","baslik"...}],
  "acik_maddeler": [...], "biten_maddeler": [...]} (madde: metin dizesi ya da "metin" alanlı sözlük).
Sayfa: GET /yapilacaklar (assets/yapilacaklar.html), menüde SEKMELER içinde '/yapilacaklar'.
"""
import http.client
import http.server
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
ASSETS = os.path.join(AD, "..", "assets")
sys.path.insert(0, SCRIPTS)
import ork_lib as L  # noqa: E402
import is_kaydi as IK  # noqa: E402
import panel  # noqa: E402


def _metinler(liste):
    return [m["metin"] if isinstance(m, dict) else m for m in liste]


class PanelTodo(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        # todo yazımı P-005 sıra kapısına takılmasın: bu test dosya yazımını sınar, kapıyı değil
        self.ortam = mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "0"})
        self.ortam.start()
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        yok = os.path.join(self.t.name, "orkestrasiz")
        os.makedirs(yok)
        self.yok = {"id": "alan-y", "ad": "orkestrasiz", "yol": yok, "orkestra": False, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [self.yok, self.alan])
        self.yama.start()
        # is 1: siradan; is 2: varsayilan olmasi gereken; is 3: kapali
        self.i1 = IK.is_ac(self.sd, "Birinci iş", os.path.join(self.t.name, "k1"))
        self.i2 = IK.is_ac(self.sd, "Orkestra açık maddeler", os.path.join(self.t.name, "k2"))
        self.i3 = IK.is_ac(self.sd, "Kapalı iş", os.path.join(self.t.name, "k3"))
        IK.is_durum(self.sd, self.i3["id"], "kapandi")
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()
        self.durum_yolu = panel.DURUM
        self.once = os.path.getmtime(self.durum_yolu) if os.path.exists(self.durum_yolu) else None

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.yama.stop()
        self.ortam.stop()
        self.t.cleanup()
        sonra = os.path.getmtime(self.durum_yolu) if os.path.exists(self.durum_yolu) else None
        self.assertEqual(self.once, sonra, "panel.json değişmemeli")

    def istek(self, yontem, yol, govde=None, baslik=None, ham=None):
        h = {"Host": f"127.0.0.1:{self.port}"}
        h.update(baslik or {})
        veri = ham if ham is not None else (json.dumps(govde).encode("utf-8") if govde is not None else None)
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(yontem, yol, skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        if veri is not None:
            c.putheader("Content-Length", str(len(veri)))
        c.endheaders(veri)
        r = c.getresponse()
        b = r.read()
        c.close()
        return r.status, b

    def post(self, govde, alan="alan-x", baslik=True, **kw):
        b = {"Content-Type": "application/json"}
        if baslik:
            b["X-Orkestra"] = "1"
        return self.istek("POST", f"/api/todo?alan={alan}", govde, baslik=b, **kw)

    def get(self, is_id=None, alan="alan-x"):
        yol = f"/api/todo?alan={alan}" + (f"&is={is_id}" if is_id else "")
        k, b = self.istek("GET", yol)
        return k, json.loads(b.decode("utf-8"))

    def todo_yol(self, kayit):
        return os.path.join(kayit["klasor"], "todo.md")

    def todo_metin(self, kayit):
        with open(self.todo_yol(kayit), encoding="utf-8", newline="") as f:
            return f.read()

    def kpost(self, govde, alan="alan-x", baslik=True, **kw):
        b = {"Content-Type": "application/json"}
        if baslik:
            b["X-Orkestra"] = "1"
        return self.istek("POST", f"/api/kullanici-todo?alan={alan}", govde, baslik=b, **kw)

    def kget(self, alan="alan-x"):
        k, b = self.istek("GET", f"/api/kullanici-todo?alan={alan}")
        return k, json.loads(b.decode("utf-8"))

    def kmetinler(self):
        return [m["metin"] for m in self.kget()[1]["maddeler"]]

    # --- 1: iş todo listeleri salt okunur ---
    def test_is_todo_post_405_ve_dosya_degismez(self):
        once = self.todo_metin(self.i1)
        for g in ({"eylem": "ekle", "is": self.i1["id"], "metin": "sızma"},
                  {"eylem": "bitti", "is": self.i1["id"], "secici": "1"}):
            k, _ = self.post(g)
            self.assertEqual(k, 405)
        self.assertEqual(self.todo_metin(self.i1), once)

    # --- 2: kullanıcı yapılacakları: ekle / sil ---
    def test_basliksiz_post_403(self):
        k, _ = self.kpost({"eylem": "ekle", "metin": "sızma"}, baslik=False)
        self.assertEqual(k, 403)
        self.assertEqual(self.kmetinler(), [])

    def test_yanlis_baslik_degeri_403(self):
        k, _ = self.istek("POST", "/api/kullanici-todo?alan=alan-x", {"eylem": "ekle", "metin": "x"},
                          baslik={"X-Orkestra": "0", "Content-Type": "application/json"})
        self.assertEqual(k, 403)
        self.assertEqual(self.kmetinler(), [])

    def test_ekle_ve_listele(self):
        k, b = self.kpost({"eylem": "ekle", "metin": "yeni  madde   burada"})
        self.assertEqual(k, 200, b)
        self.assertEqual(self.kmetinler(), ["yeni madde burada"])
        self.kpost({"eylem": "ekle", "metin": "ikinci"})
        self.assertEqual(self.kmetinler(), ["yeni madde burada", "ikinci"])

    def test_ekle_satir_sonlarini_korur(self):
        k, b = self.kpost({"eylem": "ekle", "metin": "\n başlık  satırı \r\n\n\n  - bir \n- iki\n\n"})
        self.assertEqual(k, 200, b)
        self.assertEqual(self.kmetinler(), ["başlık satırı\n\n- bir\n- iki"])

    def test_ekle_is_todo_dosyalarina_dokunmaz(self):
        once = [self.todo_metin(i) for i in (self.i1, self.i2)]
        self.kpost({"eylem": "ekle", "metin": "yalnız kullanıcıya"})
        self.assertEqual([self.todo_metin(i) for i in (self.i1, self.i2)], once)

    def test_ekle_bos_metin_400(self):
        for metin in ("", "   ", None):
            k, _ = self.kpost({"eylem": "ekle", "metin": metin})
            self.assertEqual(k, 400, repr(metin))
        k, _ = self.kpost({"eylem": "ekle"})
        self.assertEqual(k, 400)
        self.assertEqual(self.kmetinler(), [])

    def test_sil(self):
        self.kpost({"eylem": "ekle", "metin": "bir"})
        self.kpost({"eylem": "ekle", "metin": "iki"})
        ilk = self.kget()[1]["maddeler"][0]["id"]
        k, b = self.kpost({"eylem": "sil", "id": ilk})
        self.assertEqual(k, 200, b)
        self.assertEqual(self.kmetinler(), ["iki"])

    def test_sil_olmayan_madde_404_ve_bos_kimlik_400(self):
        self.kpost({"eylem": "ekle", "metin": "tek"})
        k, b = self.kpost({"eylem": "sil", "id": "K99"})
        self.assertEqual(k, 404)
        self.assertNotIn(b"Traceback", b)
        k, _ = self.kpost({"eylem": "sil", "id": ""})
        self.assertEqual(k, 400)
        self.assertEqual(self.kmetinler(), ["tek"])

    def test_silinen_kimlik_cakismaz(self):
        self.kpost({"eylem": "ekle", "metin": "a"})
        self.kpost({"eylem": "ekle", "metin": "b"})
        ilk = self.kget()[1]["maddeler"][0]["id"]
        self.kpost({"eylem": "sil", "id": ilk})
        self.kpost({"eylem": "ekle", "metin": "c"})
        ids = [m["id"] for m in self.kget()[1]["maddeler"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_bilinmeyen_eylem_400(self):
        for e in ("bitti", "guncelle", None):
            k, _ = self.kpost({"eylem": e, "metin": "x"})
            self.assertEqual(k, 400, repr(e))

    def test_bozuk_json_400(self):
        k, _ = self.kpost(None, ham=b"{bozuk")
        self.assertEqual(k, 400)

    def test_orkestrasiz_alan_400(self):
        k, _ = self.kpost({"eylem": "ekle", "metin": "x"}, alan="alan-y")
        self.assertEqual(k, 400)

    def test_kalici_dosya_ve_bozuk_dosya_dayanikli(self):
        self.kpost({"eylem": "ekle", "metin": "kalıcı"})
        yol = os.path.join(self.sd, "kullanici_todo.json")
        self.assertTrue(os.path.isfile(yol))
        with open(yol, "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertEqual(self.kmetinler(), [])
        k, _ = self.kpost({"eylem": "ekle", "metin": "yeniden"})
        self.assertEqual(k, 200)

    def test_kget_orkestrasiz_alan_acik_false(self):
        k, v = self.kget("alan-y")
        self.assertEqual(k, 200)
        self.assertFalse(v["acik"])

    # --- 4: GET ---
    def test_get_acik_ve_biten(self):
        i = self.i1["id"]
        IK.todo_ekle(self.i1["klasor"], "açık kalan")
        IK.todo_ekle(self.i1["klasor"], "biten olan")
        IK.todo_bitir(self.i1["klasor"], "biten olan")
        k, v = self.get(i)
        self.assertEqual(k, 200)
        self.assertTrue(v["acik"])
        self.assertEqual(v["is"], i)
        self.assertEqual(_metinler(v["acik_maddeler"]), ["açık kalan"])
        self.assertEqual(len(v["biten_maddeler"]), 1)
        self.assertIn("biten olan", _metinler(v["biten_maddeler"])[0])

    def test_get_sablon_bos_madde_listelenmez(self):
        k, v = self.get(self.i1["id"])
        self.assertEqual(k, 200)
        self.assertEqual(_metinler(v["acik_maddeler"]), [])

    def test_get_varsayilan_is_orkestra_acik_maddeler(self):
        IK.todo_ekle(self.i2["klasor"], "varsayılanda")
        k, v = self.get()
        self.assertEqual(k, 200)
        self.assertEqual(v["is"], self.i2["id"])
        self.assertEqual(_metinler(v["acik_maddeler"]), ["varsayılanda"])

    def test_get_varsayilan_baslik_yoksa_ilk_acik_is(self):
        IK.is_durum(self.sd, self.i2["id"], "kapandi")
        _, v = self.get()
        self.assertEqual(v["is"], self.i1["id"])

    def test_get_varsayilan_kapali_orkestra_isi_secilmez(self):
        IK.is_durum(self.sd, self.i2["id"], "kapandi")
        _, v = self.get()
        self.assertNotEqual(v["is"], self.i2["id"])

    def test_get_is_secici_listesi_yalniz_acik_isler(self):
        _, v = self.get()
        ids = [x["id"] for x in v["isler"]]
        self.assertIn(self.i1["id"], ids)
        self.assertIn(self.i2["id"], ids)
        self.assertNotIn(self.i3["id"], ids)

    def test_get_olmayan_is_istisna_sizmaz(self):
        k, b = self.istek("GET", "/api/todo?alan=alan-x&is=I-999")
        self.assertIn(k, (200, 400, 404))
        self.assertNotIn(b"Traceback", b)
        if k == 200:
            self.assertEqual(_metinler(json.loads(b).get("acik_maddeler") or []), [])

    def test_get_orkestrasiz_alan_acik_false(self):
        k, v = self.get(alan="alan-y")
        self.assertEqual(k, 200)
        self.assertFalse(v["acik"])

    def test_get_yazim_sonrasi_taze(self):
        i = self.i1["id"]
        self.get(i)
        IK.todo_ekle(self.i1["klasor"], "hemen görünmeli")
        _, v = self.get(i)
        self.assertIn("hemen görünmeli", _metinler(v["acik_maddeler"]))

    # --- 5: iş todo yazımı panelde yok ---
    def test_panel_is_todo_fonksiyonlarini_cagirmaz(self):
        with mock.patch.object(IK, "todo_ekle") as e, mock.patch.object(IK, "todo_bitir") as b:
            self.post({"eylem": "ekle", "is": self.i1["id"], "metin": "x"})
            self.kpost({"eylem": "ekle", "metin": "y"})
        self.assertFalse(e.called or b.called)

    def test_panel_py_todo_md_ye_dogrudan_yazmaz(self):
        with open(os.path.join(SCRIPTS, "panel.py"), encoding="utf-8") as f:
            kod = f.read()
        self.assertNotIn("todo.md", kod, "panel.py todo.md yolunu kendisi kurmamalı")
        self.assertIsNone(re.search(r"\[ \]|\[x\]", kod), "panel.py onay kutusu biçimini bilmemeli")

    # --- 6: arayuz ---
    def _ortak_js(self):
        with open(os.path.join(ASSETS, "ortak.js"), encoding="utf-8") as f:
            return f.read()

    def _sayfa(self):
        """Sayfa HTML'i + ona bağlı sayfa .js/.css dosyaları (ortak.* hariç), sunucudan HTTP ile."""
        k, b = self.istek("GET", "/yapilacaklar")
        self.assertEqual(k, 200)
        s = b.decode("utf-8")
        for yol in re.findall(r'(?:src|href)="([\w-]+\.(?:js|css))"', s):
            if not yol.startswith("ortak."):
                k2, b2 = self.istek("GET", "/" + yol)
                self.assertEqual(k2, 200, yol)
                s += "\n" + b2.decode("utf-8")
        return s

    def test_yapilacaklar_sayfasi_var_ve_ogeler_icerir(self):
        self.assertTrue(os.path.isfile(os.path.join(ASSETS, "yapilacaklar.html")), "yapilacaklar.html yok")
        s = self._sayfa()
        self.assertNotIn("hazırlanıyor", s.lower())
        self.assertRegex(s, r"<input|<textarea", "metin kutusu")
        self.assertIn("Enter", s)
        self.assertNotIn("<select", s)
        self.assertIn("/api/kullanici-todo", s)
        self.assertIn("Benim yapılacaklarım", s)
        self.assertIn("X-Orkestra", s + self._ortak_js())
        self.assertIn("ortak.css", s)
        self.assertIn("ortak.js", s)

    def test_is_listesi_salt_okunur_arayuzde(self):
        s = self._sayfa()
        self.assertNotIn("eylem: 'bitti'", s)
        self.assertNotIn("data-n=", s)
        # "İşlerin yapılacakları" bölümü arayüzden kaldırıldı (kullanıcı kararı 15.10); API salt okunur kalır
        self.assertNotIn("İşlerin yapılacakları", s)

    def test_sayfa_i001_sabit_yazmaz(self):
        self.assertNotIn("I-001", self._sayfa())

    def test_menude_yapilacaklar_baglantisi(self):
        m = re.search(r"SEKMELER\s*=\s*\[(.*?)\];", self._ortak_js(), re.S)
        self.assertIsNotNone(m)
        self.assertIn("'/yapilacaklar'", m.group(1))

    def test_sayfa_alan_parametresini_tasir(self):
        s = self._sayfa() + self._ortak_js()
        self.assertRegex(s, r"sorgu\(\)|alan=")


if __name__ == "__main__":
    unittest.main()
