"""I-083 P2: kullanıcı Cursor hooks.json'u kanonik hooks/cursor-hooks.json'dan üretilir, birleştirilir, güvenle yazılır;
guncelle eşler, doktor sapmayı görür. Testler gerçek ~/.cursor'a yazmaz: tüm yollar geçici dizindedir."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import doktor  # noqa: E402
import guncelle as G  # noqa: E402

try:
    import cursor_hooks as CH  # noqa: E402
except ModuleNotFoundError:
    CH = None

KANONIK = os.path.join(KOK, "hooks", "cursor-hooks.json")
OLAYLAR = ["sessionStart", "beforeSubmitPrompt", "preToolUse", "postToolUse", "stop", "sessionEnd"]
BOM = b"\xef\xbb\xbf"
GERCEK_HOOKS = os.path.join(os.path.expanduser("~"), ".cursor", "hooks.json")
_gercek_once = None


def setUpModule():
    global _gercek_once
    try:
        with open(GERCEK_HOOKS, "rb") as f:
            _gercek_once = f.read()
    except OSError:
        _gercek_once = None


def tearDownModule():
    try:
        with open(GERCEK_HOOKS, "rb") as f:
            sonra = f.read()
    except OSError:
        sonra = None
    assert sonra == _gercek_once, "testler gerçek ~/.cursor/hooks.json dosyasını değiştirdi"


def ileri(yol):
    return yol.replace("\\", "/")


def komut(kopya, olay):
    return f'python "{ileri(kopya)}/scripts/cursor_hook.py" {olay}'


def oku_bayt(yol):
    with open(yol, "rb") as f:
        return f.read()


def yaz_bayt(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "wb") as f:
        f.write(veri)


def oku_json(yol):
    veri = oku_bayt(yol)
    assert not veri.startswith(BOM), "dosya BOM'lu yazılmış"
    return json.loads(veri.decode("utf-8"))


def elle_yazilmis(kopya):
    """Bugünkü elle yazılmış dosya biçimi: tırnaksız komut, ileri eğik çizgili kopya yolu."""
    return {"version": 1, "hooks": {o: [{"command": f"python {ileri(kopya)}/scripts/cursor_hook.py {o}",
                                         "timeout": 30 if o == "stop" else 10}] for o in OLAYLAR}}


class _Gecici(unittest.TestCase):
    def setUp(self):
        if CH is None:
            self.fail("scripts/cursor_hooks.py modülü yok")
        self.tmp = tempfile.mkdtemp(prefix="ork_chk_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.kopya = os.path.join(self.tmp, "Program Files", "plugins", "local", "orkestra")
        os.makedirs(self.kopya)
        self.kullanici = os.path.join(self.tmp, "cursor", "hooks.json")
        os.makedirs(os.path.dirname(self.kullanici))
        self.yedek_kok = os.path.join(self.tmp, "yedek")

    def esitle(self, kopya=None):
        return CH.esitle(self.kullanici, KANONIK, kopya or self.kopya, self.yedek_kok)

    def yedekler(self):
        return sorted(os.listdir(self.yedek_kok)) if os.path.isdir(self.yedek_kok) else []


# ---------------------------------------------------------------- K1 üretim

class Tanim(_Gecici):
    def test_uret_alti_olay_version_1_kanonik_sirada(self):
        r = CH.uret(KANONIK, self.kopya)
        self.assertEqual(r["version"], 1)
        self.assertEqual(list(r["hooks"]), OLAYLAR)

    def test_uret_komut_kopya_yolunu_ileri_egik_cizgiyle_gosterir(self):
        r = CH.uret(KANONIK, self.kopya)
        for olay in OLAYLAR:
            self.assertEqual(len(r["hooks"][olay]), 1, olay)
            g = r["hooks"][olay][0]
            self.assertEqual(g["command"], komut(self.kopya, olay))
            self.assertNotIn("\\", g["command"])
            self.assertNotIn("CURSOR_PLUGIN_ROOT", g["command"])

    def test_uret_timeout_kanonikten_ve_yalniz_izinli_alanlar(self):
        r = CH.uret(KANONIK, self.kopya)
        self.assertEqual(r["hooks"]["stop"][0], {"command": komut(self.kopya, "stop"), "timeout": 30})
        self.assertEqual(r["hooks"]["preToolUse"][0], {"command": komut(self.kopya, "preToolUse"), "timeout": 10})

    def test_uret_matcher_failclosed_tasinir_bilinmeyen_alan_atilir(self):
        kanonik = os.path.join(self.tmp, "kanonik.json")
        yaz_bayt(kanonik, json.dumps({"version": 1, "hooks": {
            "preToolUse": [{"command": "python -c x", "timeout": 7, "matcher": "Shell", "failClosed": True,
                            "type": "command", "gizli": "sil"}],
            "stop": [{"command": "python -c y", "timeout": 30}]}}).encode("utf-8"))
        r = CH.uret(kanonik, self.kopya)
        self.assertEqual(list(r["hooks"]), ["preToolUse", "stop"])
        self.assertEqual(r["hooks"]["preToolUse"][0], {"command": komut(self.kopya, "preToolUse"), "timeout": 7,
                                                       "matcher": "Shell", "failClosed": True})
        self.assertEqual(r["hooks"]["stop"][0], {"command": komut(self.kopya, "stop"), "timeout": 30})

    def test_uret_yok_dosyadan_alti_olay(self):
        self.assertFalse(os.path.exists(self.kullanici))
        mesaj, _ = self.esitle()
        self.assertIsInstance(mesaj, str)
        d = oku_json(self.kullanici)
        self.assertEqual(d["version"], 1)
        self.assertEqual(list(d["hooks"]), OLAYLAR)
        self.assertEqual(d["hooks"]["sessionEnd"][0]["command"], komut(self.kopya, "sessionEnd"))

    def test_uret_bos_dosyadan_alti_olay(self):
        yaz_bayt(self.kullanici, b"")
        self.esitle()
        d = oku_json(self.kullanici)
        self.assertEqual(d["version"], 1)
        self.assertEqual(list(d["hooks"]), OLAYLAR)

    def test_uret_bos_sozlukle_birlestirince_alti_olay(self):
        u = CH.uret(KANONIK, self.kopya)
        r = CH.birlestir({}, u, self.kopya)
        self.assertEqual(r["version"], 1)
        self.assertEqual(r["hooks"], u["hooks"])


# ---------------------------------------------------------------- K2 birleştirme

class Birlesim(_Gecici):
    def setUp(self):
        super().setUp()
        self.u = CH.uret(KANONIK, self.kopya)

    def test_koru_ayni_olayda_kullanici_hooklari_sirasiyla(self):
        k1 = {"command": "node C:/benim/guard.js", "timeout": 5}
        k2 = {"command": "python C:/benim/log.py"}
        eski = {"command": f"python {ileri(self.kopya)}/scripts/cursor_hook.py preToolUse", "timeout": 99}
        mevcut = {"version": 1, "hooks": {"preToolUse": [k1, eski, k2]}}
        once = copy.deepcopy(mevcut)
        r = CH.birlestir(mevcut, self.u, self.kopya)
        self.assertEqual(mevcut, once, "birlestir girdiyi değiştirmemeli")
        liste = r["hooks"]["preToolUse"]
        self.assertEqual([g for g in liste if g in (k1, k2)], [k1, k2])
        self.assertEqual([g for g in liste if g not in (k1, k2)], [self.u["hooks"]["preToolUse"][0]])
        self.assertEqual(len(liste), 3)

    def test_koru_ust_duzey_anahtarlar_ve_sira(self):
        mevcut = {"version": 1, "ozel": {"a": 1}, "hooks": {}, "son": [1, 2]}
        r = CH.birlestir(mevcut, self.u, self.kopya)
        self.assertEqual(list(r)[:4], ["version", "ozel", "hooks", "son"])
        self.assertEqual(r["ozel"], {"a": 1})
        self.assertEqual(r["son"], [1, 2])

    def test_koru_kanonikte_olmayan_olay(self):
        ek = [{"command": "python C:/benim/duzenle.py"}]
        r = CH.birlestir({"version": 1, "hooks": {"afterFileEdit": ek}}, self.u, self.kopya)
        self.assertEqual(r["hooks"]["afterFileEdit"], ek)
        for olay in OLAYLAR:
            self.assertIn(self.u["hooks"][olay][0], r["hooks"][olay])

    def test_koru_orkestra_disi_yoldaki_cursor_hook_sarmalayicisi(self):
        sarmalayici = {"command": 'python "D:/benim/araclarim/cursor_hook.py" preToolUse'}
        r = CH.birlestir({"hooks": {"preToolUse": [sarmalayici]}}, self.u, self.kopya)
        self.assertIn(sarmalayici, r["hooks"]["preToolUse"])
        self.assertIn(self.u["hooks"]["preToolUse"][0], r["hooks"]["preToolUse"])
        self.assertEqual(len(r["hooks"]["preToolUse"]), 2)

    def test_koru_baska_olay_adli_orkestra_girdisi(self):
        baska = {"command": f"python {ileri(self.kopya)}/scripts/cursor_hook.py postToolUse"}
        r = CH.birlestir({"hooks": {"preToolUse": [baska]}}, self.u, self.kopya)
        self.assertIn(baska, r["hooks"]["preToolUse"])
        self.assertEqual(len(r["hooks"]["preToolUse"]), 2)

    def test_koru_elle_yazilmis_orkestra_girdileri_tekrarlanmaz(self):
        r = CH.birlestir(elle_yazilmis(self.kopya), self.u, self.kopya)
        self.assertEqual(r["hooks"], self.u["hooks"])

    def test_koru_kopya_yolu_orkestra_icermese_de_ters_egik_cizgiyle_eslesir(self):
        kopya = os.path.join(self.tmp, "kopya")
        os.makedirs(kopya)
        u = CH.uret(KANONIK, kopya)
        eski = {"command": f'python "{ileri(kopya)}/scripts/cursor_hook.py" stop', "timeout": 5}
        r = CH.birlestir({"hooks": {"stop": [eski]}}, u, kopya)
        self.assertEqual(r["hooks"]["stop"], u["hooks"]["stop"])

    def test_idempotent_birlestir_iki_kez(self):
        mevcut = {"version": 1, "hooks": {"stop": [{"command": "echo x"}]}}
        bir = CH.birlestir(mevcut, self.u, self.kopya)
        self.assertEqual(CH.birlestir(bir, self.u, self.kopya), bir)


# ---------------------------------------------------------------- K3-K5 yazım

class Yazim(_Gecici):
    def test_idempotent_ikinci_kosu_bayt_ayni_yedek_yok(self):
        self.esitle()
        once = oku_bayt(self.kullanici)
        yedek_once = self.yedekler()
        mesaj, yedek = self.esitle()
        self.assertIn("zaten güncel", mesaj)
        self.assertIsNone(yedek)
        self.assertEqual(oku_bayt(self.kullanici), once)
        self.assertEqual(self.yedekler(), yedek_once)

    def test_idempotent_kullanici_girdileriyle(self):
        d = elle_yazilmis(self.kopya)
        d["hooks"]["stop"].insert(0, {"command": "echo öncesi ğüş"})
        d["ozel"] = True
        yaz_bayt(self.kullanici, json.dumps(d).encode("utf-8"))
        self.esitle()
        once = oku_bayt(self.kullanici)
        mesaj, yedek = self.esitle()
        self.assertIn("zaten güncel", mesaj)
        self.assertIsNone(yedek)
        self.assertEqual(oku_bayt(self.kullanici), once)
        self.assertEqual(oku_json(self.kullanici)["hooks"]["stop"][0], {"command": "echo öncesi ğüş"})

    def test_yedek_degisiklikte_once_alinir(self):
        eski_d = elle_yazilmis(os.path.join(self.tmp, "eski", "orkestra"))
        eski = json.dumps(eski_d, indent=2).encode("utf-8")
        yaz_bayt(self.kullanici, eski)
        mesaj, yedek = self.esitle()
        self.assertNotIn("zaten güncel", mesaj)
        self.assertIsNotNone(yedek)
        self.assertEqual(os.path.basename(yedek), "hooks.json")
        self.assertEqual(os.path.normcase(os.path.dirname(os.path.dirname(os.path.abspath(yedek)))),
                         os.path.normcase(os.path.abspath(self.yedek_kok)))
        self.assertEqual(oku_bayt(yedek), eski)
        self.assertEqual(oku_json(self.kullanici)["hooks"]["stop"][0]["command"], komut(self.kopya, "stop"))

    def test_yedek_en_cok_bes(self):
        a = os.path.join(self.tmp, "a", "orkestra")
        b = os.path.join(self.tmp, "b", "orkestra")
        yaz_bayt(self.kullanici, json.dumps(elle_yazilmis(b)).encode("utf-8"))
        son = None
        for i in range(7):
            _, son = self.esitle(a if i % 2 == 0 else b)
            self.assertIsNotNone(son, f"{i}. değişiklikte yedek alınmadı")
        self.assertEqual(len(self.yedekler()), 5)
        self.assertTrue(os.path.isfile(son))

    def test_bom_suz_utf8_yazim(self):
        d = {"version": 1, "not": "çğıöşü", "hooks": {}}
        yaz_bayt(self.kullanici, json.dumps(d, ensure_ascii=False).encode("utf-8"))
        self.esitle()
        veri = oku_bayt(self.kullanici)
        self.assertFalse(veri.startswith(BOM))
        self.assertEqual(json.loads(veri.decode("utf-8"))["not"], "çğıöşü")

    def test_bom_lu_gecerli_guncel_dosya_bomsuz_yeniden_yazilir(self):
        self.esitle()
        icerik = oku_bayt(self.kullanici)
        yaz_bayt(self.kullanici, BOM + icerik)
        self.esitle()
        sonra = oku_bayt(self.kullanici)
        self.assertFalse(sonra.startswith(BOM))
        self.assertEqual(json.loads(sonra.decode("utf-8")), json.loads(icerik.decode("utf-8")))

    def test_bom_or_yedek_bomlu_eski_dosya_yedeklenip_bomsuz_yazilir(self):
        eski = BOM + json.dumps(elle_yazilmis(os.path.join(self.tmp, "eski", "orkestra"))).encode("utf-8")
        yaz_bayt(self.kullanici, eski)
        _, yedek = self.esitle()
        self.assertIsNotNone(yedek)
        self.assertEqual(oku_bayt(yedek), eski)
        d = oku_json(self.kullanici)
        self.assertEqual(d["hooks"]["preToolUse"], [{"command": komut(self.kopya, "preToolUse"), "timeout": 10}])

    def test_esitle_atomik_yazim_gecici_dosya_birakmaz(self):
        yaz_bayt(self.kullanici, json.dumps(elle_yazilmis(os.path.join(self.tmp, "x", "orkestra"))).encode("utf-8"))
        self.esitle()
        self.assertEqual(os.listdir(os.path.dirname(self.kullanici)), ["hooks.json"])

    def test_bozuk_json_dokunulmaz_hata_mesaji(self):
        bozuk = b'{"version": 1, "hooks": {'
        yaz_bayt(self.kullanici, bozuk)
        mesaj, yedek = self.esitle()
        self.assertIn("ayrıştırılamıyor", mesaj)
        self.assertIsNone(yedek)
        self.assertEqual(oku_bayt(self.kullanici), bozuk)
        self.assertEqual(self.yedekler(), [])

    def test_bozuk_bomlu_json_dokunulmaz(self):
        bozuk = BOM + b'{"hooks": [,]}'
        yaz_bayt(self.kullanici, bozuk)
        mesaj, yedek = self.esitle()
        self.assertIn("ayrıştırılamıyor", mesaj)
        self.assertIsNone(yedek)
        self.assertEqual(oku_bayt(self.kullanici), bozuk)

    def test_bozuk_ust_duzey_sozluk_degilse_dokunulmaz(self):
        bozuk = b"[1, 2, 3]"
        yaz_bayt(self.kullanici, bozuk)
        mesaj, yedek = self.esitle()
        self.assertIsInstance(mesaj, str)
        self.assertIsNone(yedek)
        self.assertEqual(oku_bayt(self.kullanici), bozuk)


# ---------------------------------------------------------------- K6 guncelle bağlantısı

class GuncelleCagri(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_chg_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ev = os.path.join(self.tmp, "ev")
        self.hedef = os.path.join(self.ev, ".cursor", "plugins", "local", "orkestra")
        os.makedirs(os.path.join(self.hedef, "hooks"))
        shutil.copy(KANONIK, os.path.join(self.hedef, "hooks", "cursor-hooks.json"))
        self.klon = os.path.join(self.tmp, "klon")
        os.makedirs(os.path.join(self.klon, "plugins", "orkestra", "hooks"))
        shutil.copy(KANONIK, os.path.join(self.klon, "plugins", "orkestra", "hooks", "cursor-hooks.json"))
        self.kullanici = os.path.join(self.ev, ".cursor", "hooks.json")
        self.cikti = []
        self.kopya_sirasinda_hooks_vardi = None

        def kopya_guncelle(kaynak, hedef, yedek_kok):
            self.kopya_sirasinda_hooks_vardi = os.path.exists(self.kullanici)
            return ("yerel Cursor kopyası güncellendi: 1 yeni, 0 değişen dosya", None)

        ev = self.ev
        yamalar = [
            mock.patch("os.path.expanduser", side_effect=lambda p: ev + p[1:] if p.startswith("~") else p),
            mock.patch.object(G.cursor_kur, "varsayilan_hedef", return_value=self.hedef),
            mock.patch.object(G.cursor_kur, "baglanti_mi", return_value=False),
            mock.patch.object(G.cfg, "ev_dizini", return_value=os.path.join(self.tmp, "orkev")),
            mock.patch.object(G.cursor_kur, "guncelle", side_effect=kopya_guncelle),
        ]
        baslayan = [p.start() for p in yamalar]
        for p in yamalar:
            self.addCleanup(p.stop)
        self.kopya_mock = baslayan[-1]
        os.environ.pop("ORKESTRA_CURSOR_ESITLE", None)
        self.addCleanup(lambda: os.environ.pop("ORKESTRA_CURSOR_ESITLE", None))

    def hooks_satirlari(self):
        return [s for s in self.cikti if s.startswith("Cursor hooks.json:")]

    def test_esitle_kopya_sonrasi_hooks_json_yazilir(self):
        G._cursor_esitle(self.klon, self.cikti.append)
        self.kopya_mock.assert_called_once()
        self.assertIs(self.kopya_sirasinda_hooks_vardi, False, "hooks.json kopya eşlemesinden önce yazılmış")
        d = oku_json(self.kullanici)
        self.assertEqual(list(d["hooks"]), OLAYLAR)
        self.assertEqual(d["hooks"]["stop"][0]["command"], komut(self.hedef, "stop"))
        self.assertEqual(len(self.hooks_satirlari()), 1, self.cikti)
        kopya_i = next(i for i, s in enumerate(self.cikti) if s.startswith("Cursor yerel kopyası"))
        self.assertLess(kopya_i, self.cikti.index(self.hooks_satirlari()[0]))

    def test_esitle_ikinci_kosu_zaten_guncel(self):
        G._cursor_esitle(self.klon, self.cikti.append)
        once = oku_bayt(self.kullanici)
        self.cikti.clear()
        G._cursor_esitle(self.klon, self.cikti.append)
        self.assertIn("zaten güncel", self.hooks_satirlari()[0])
        self.assertEqual(oku_bayt(self.kullanici), once)

    def test_esitle_bozuk_kullanici_dosyasina_dokunmaz(self):
        bozuk = b'{"hooks": '
        yaz_bayt(self.kullanici, bozuk)
        G._cursor_esitle(self.klon, self.cikti.append)
        self.assertEqual(oku_bayt(self.kullanici), bozuk)
        self.assertIn("ayrıştırılamıyor", self.hooks_satirlari()[0])

    def test_esitle_hata_guncellemeyi_basarisiz_kilmaz(self):
        with mock.patch.object(G.cursor_hooks, "esitle", side_effect=RuntimeError("patladı")):
            G._cursor_esitle(self.klon, self.cikti.append)
        self.assertTrue(any(s.startswith("Cursor yerel kopyası") for s in self.cikti), self.cikti)
        self.assertTrue(any("hooks.json" in s for s in self.cikti), self.cikti)
        self.assertFalse(os.path.exists(self.kullanici))

    def test_esitle_kapali_bayrak_ikisini_de_kapatir(self):
        os.environ["ORKESTRA_CURSOR_ESITLE"] = "0"
        with mock.patch.object(G.cursor_hooks, "esitle") as hooks_esitle:
            G._cursor_esitle(self.klon, self.cikti.append)
        self.kopya_mock.assert_not_called()
        hooks_esitle.assert_not_called()
        self.assertFalse(os.path.exists(self.kullanici))
        self.assertEqual(self.hooks_satirlari(), [])


# ---------------------------------------------------------------- K7 doktor

class DoktorKontrol(unittest.TestCase):
    def setUp(self):
        if CH is None:
            self.fail("scripts/cursor_hooks.py modülü yok")
        self.tmp = tempfile.mkdtemp(prefix="ork_chd_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ev = os.path.join(self.tmp, "ev")
        self.proje = os.path.join(self.tmp, "proje")
        os.makedirs(os.path.join(self.ev, ".cursor"))
        os.makedirs(self.proje)
        self.kopya = os.path.join(self.ev, ".cursor", "plugins", "local", "orkestra")
        self.kullanici = os.path.join(self.ev, ".cursor", "hooks.json")
        ev = self.ev
        for p in (mock.patch("os.path.expanduser", side_effect=lambda y: ev + y[1:] if y.startswith("~") else y),
                  mock.patch.object(doktor.cfg, "ev_dizini", return_value=os.path.join(self.tmp, "orkev"))):
            p.start()
            self.addCleanup(p.stop)

    def kontrol(self):
        k = next((x for x in doktor.KONTROLLER if x.id == "cursor_hooks"), None)
        self.assertIsNotNone(k, "KONTROLLER'de cursor_hooks yok")
        return k, k.kontrol(doktor.Baglam(proje=self.proje))

    def guncel_yaz(self):
        os.makedirs(self.kopya, exist_ok=True)
        CH.esitle(self.kullanici, KANONIK, self.kopya, os.path.join(self.tmp, "y"))

    def test_doktor_kayitli_opsiyonel_tekil(self):
        k = next((x for x in doktor.KONTROLLER if x.id == "cursor_hooks"), None)
        self.assertIsNotNone(k)
        self.assertEqual(k.sinif, "opsiyonel")
        ids = [x.id for x in doktor.KONTROLLER]
        self.assertEqual(len(ids), len(set(ids)))

    def test_doktor_yerel_kopya_yoksa_atlandi(self):
        yaz_bayt(self.kullanici, b"{bozuk")
        _, s = self.kontrol()
        self.assertEqual(s.durum, "atlandi")

    def test_doktor_guncel_dosya_ok(self):
        self.guncel_yaz()
        _, s = self.kontrol()
        self.assertEqual(s.durum, "gecti", s.mesaj)

    def test_doktor_sapma_uyari_ve_onarim(self):
        os.makedirs(self.kopya)
        eski = json.dumps(elle_yazilmis(os.path.join(self.tmp, "eski", "orkestra"))).encode("utf-8")
        yaz_bayt(self.kullanici, eski)
        k, s = self.kontrol()
        self.assertEqual(s.durum, "uyari")
        self.assertEqual(oku_bayt(self.kullanici), eski, "kontrol dosyaya yazmamalı")
        self.assertIsNotNone(k.onar)
        onarim = k.onar(doktor.Baglam(proje=self.proje), s)
        self.assertIsNotNone(onarim)
        if onarim.uygula is not None:
            onarim.uygula()
            self.assertEqual(self.kontrol()[1].durum, "gecti")

    def test_doktor_dosya_yoksa_uyari(self):
        os.makedirs(self.kopya)
        _, s = self.kontrol()
        self.assertEqual(s.durum, "uyari")
        self.assertFalse(os.path.exists(self.kullanici))

    def test_doktor_bozuk_dosya_ayristirilamiyor_uyarisi(self):
        os.makedirs(self.kopya)
        bozuk = b'{"version": 1,'
        yaz_bayt(self.kullanici, bozuk)
        _, s = self.kontrol()
        self.assertEqual(s.durum, "uyari")
        self.assertIn("ayrıştırılamıyor", s.mesaj)
        self.assertEqual(oku_bayt(self.kullanici), bozuk)

    def test_doktor_proje_duzeyi_dosyaya_bakmaz(self):
        self.guncel_yaz()
        yaz_bayt(os.path.join(self.proje, ".cursor", "hooks.json"), b"{bozuk")
        _, s = self.kontrol()
        self.assertEqual(s.durum, "gecti", s.mesaj)

    def test_doktor_sapma_fonksiyonu_guncelde_bos(self):
        self.guncel_yaz()
        self.assertEqual(CH.sapma(self.kullanici, KANONIK, self.kopya), [])

    def test_doktor_sapma_fonksiyonu_farkta_dolu(self):
        os.makedirs(self.kopya)
        yaz_bayt(self.kullanici, json.dumps(elle_yazilmis(os.path.join(self.tmp, "eski", "orkestra"))).encode("utf-8"))
        s = CH.sapma(self.kullanici, KANONIK, self.kopya)
        self.assertTrue(s)
        self.assertTrue(all(isinstance(x, str) for x in s))
        self.assertTrue(CH.sapma(os.path.join(self.tmp, "yok.json"), KANONIK, self.kopya))


if __name__ == "__main__":
    unittest.main()
