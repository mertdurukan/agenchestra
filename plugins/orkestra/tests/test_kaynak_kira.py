"""I-309 P4: makine genelinde test kirası ve ortak işçi bütçesi (scripts/kaynak_kira.py).

K1: aynı anda iki koşucu (20 tekrar) -> toplam işçi bütçeyi aşmaz, ikincinin çıktısında "sıra: 2".
K2: sahip süreç öldürülünce ikinci koşu sona erme süresi dolunca devralır.
K3: mod kapali iken davranış eski gibi (kayıt yok, bekleme yok, işçi kısılmaz).
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(KOK, "scripts")
sys.path.insert(0, SCRIPTS)
import kaynak_kira as K  # noqa: E402

KOSUCU = os.path.join(SCRIPTS, "test_paralel.py")

# test_paralel.py benzeri koşucu: bariyerde buluşur, kira alır, işçi sayısını ve zaman aralığını günlüğe yazar.
SAHTE = r'''
import os, sys, time
sys.path.insert(0, sys.argv[1])
import kaynak_kira as K
bariyer, ad, istenen, tut, gunluk = sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5], sys.argv[6]
if bariyer != "-":
    open(os.path.join(bariyer, ad), "w").close()
    while len(os.listdir(bariyer)) < 2:
        time.sleep(0.005)
with K.kira(istenen, komut="sahte " + ad) as k:
    t0 = time.time()
    print("ALINDI", ad, k.isci, flush=True)
    if tut.startswith("dosya:"):  # sabit süre yerine olay: test bırak dosyasını yazana kadar (en çok 120 sn) tut
        while not os.path.exists(tut[6:]) and time.time() - t0 < 120:
            time.sleep(0.02)
    else:
        time.sleep(float(tut))
    t1 = time.time()
with open(gunluk, "a", encoding="utf-8") as f:
    f.write(f"{ad} {k.isci} {t0:.4f} {t1:.4f}\n")
'''


@contextlib.contextmanager
def ayri_surec():
    """Aynı süreçte ikinci kira, iç içe koşu sayılmasın diye sahip ortam değişkeni geçici kaldırılır (ayrı süreç benzetimi)."""
    eski = os.environ.pop(K.SAHIP_ENV, None)
    try:
        yield
    finally:
        if eski is not None:
            os.environ[K.SAHIP_ENV] = eski


class Ortam(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ork_kira_")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        self.kira_dizini = os.path.join(self.d, "kira")
        self.ayar_yolu = os.path.join(self.d, "ayar.json")
        self.sahte = os.path.join(self.d, "sahte_kosucu.py")
        with open(self.sahte, "w", encoding="utf-8") as f:
            f.write(SAHTE)
        self.env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                        ORKESTRA_KAYNAK_KIRA_DIZINI=self.kira_dizini, ORKESTRA_KAYNAK_KIRA_AYAR=self.ayar_yolu)
        self.env.pop(K.SAHIP_ENV, None)  # dış koşucunun kirası iç testleri muaf tutmasın
        self.env.pop("ORKESTRA_KAYNAK_KIRA", None)
        self.env.pop("CLAUDE_PROJECT_DIR", None)  # gölge kaydı ve proje ezmesi gerçek projeye gitmesin
        p = mock.patch.dict(os.environ, {"ORKESTRA_KAYNAK_KIRA_DIZINI": self.kira_dizini,
                                         "ORKESTRA_KAYNAK_KIRA_AYAR": self.ayar_yolu})
        p.start()
        self.addCleanup(p.stop)
        for ad in (K.SAHIP_ENV, "ORKESTRA_KAYNAK_KIRA", "CLAUDE_PROJECT_DIR"):
            if ad in os.environ:
                eski = os.environ.pop(ad)
                self.addCleanup(os.environ.__setitem__, ad, eski)

    def ayar(self, **kw):
        d = {"mod": "ihlal", "butce": 4, "sona_erme_s": 3, "yoklama_s": 0.02, "bekleme_ust_s": 60}
        d.update(kw)
        with open(self.ayar_yolu, "w", encoding="utf-8") as f:
            json.dump(d, f)

    def sahte_baslat(self, ad, istenen, tut, bariyer="-", gunluk=None):
        return subprocess.Popen([sys.executable, self.sahte, SCRIPTS, bariyer, ad, str(istenen), str(tut),
                                 gunluk or os.path.join(self.d, "gunluk.txt")],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", env=self.env, cwd=self.d)

    def sahip_bekle(self, sure=20):
        bitis = time.time() + sure
        while time.time() < bitis:
            if K.durum()["sahipler"]:
                return
            time.sleep(0.02)
        self.fail("sahip kaydı oluşmadı")


class EsZamanliBütce(Ortam):
    """K1: 20 tekrar, bariyerle aynı anda başlayan iki koşucu; her biri 3 işçi ister, bütçe 4."""

    def test_k1_yirmi_tekrar_butce_asilmaz_ikinci_sira_2(self):
        self.ayar()
        sira2 = 0
        for tekrar in range(20):
            bariyer = os.path.join(self.d, f"bariyer{tekrar}")
            os.makedirs(bariyer)
            gunluk = os.path.join(self.d, f"gunluk{tekrar}.txt")
            ps = [self.sahte_baslat(ad, 3, 0.3, bariyer, gunluk) for ad in ("a", "b")]
            ciktilar = [p.communicate(timeout=60)[0] for p in ps]
            for p, c in zip(ps, ciktilar):
                self.assertEqual(p.returncode, 0, c)
            with open(gunluk, encoding="utf-8") as f:
                araliklar = [(int(x.split()[1]), float(x.split()[2]), float(x.split()[3])) for x in f if x.strip()]
            self.assertEqual(len(araliklar), 2)
            # her an: o anda kira tutan koşuların işçi toplamı <= bütçe
            for isci, t0, _ in araliklar:
                toplam = sum(i for i, a0, a1 in araliklar if a0 <= t0 < a1)
                self.assertLessEqual(toplam, 4, (tekrar, araliklar))
            sirali = [c for c in ciktilar if "sıra: 2, sahip: " in c]
            self.assertEqual(len(sirali), 1, (tekrar, ciktilar))
            self.assertRegex(sirali[0], r"sıra: 2, sahip: \d+/sahte [ab]")
            sira2 += 1
        self.assertEqual(sira2, 20)
        self.assertEqual(K.durum()["sahipler"], [])  # iki koşu da bırakınca kayıt boş

    def test_kucuk_koşular_butceye_sigarsa_birlikte_girer(self):
        self.ayar()
        with K.kira(2, komut="bir", cikti=io.StringIO()) as k1:
            buf = io.StringIO()
            t = time.time()
            with ayri_surec(), K.kira(2, komut="iki", cikti=buf) as k2:
                self.assertLess(time.time() - t, 1.0)
                self.assertEqual((k1.isci, k2.isci, k2.sira), (2, 2, 0))
                self.assertEqual(K.durum()["kullanilan"], 4)
            self.assertNotIn("sıra:", buf.getvalue())

    def test_istenen_butceyi_asarsa_kisilir(self):
        self.ayar()
        with K.kira(16, cikti=io.StringIO()) as k:
            self.assertEqual(k.isci, 4)

    def test_bekleme_ust_siniri_zaman_asimi(self):
        self.ayar(bekleme_ust_s=0.3)
        p = self.sahte_baslat("sahip", 4, 10)
        self.addCleanup(p.kill)
        self.sahip_bekle()
        with self.assertRaises(K.KiraZamanAsimi):
            with K.kira(1, cikti=io.StringIO()):
                pass
        self.assertEqual(K.durum()["bekleyenler"], [])

    def test_bekleyen_kesilirse_bekleyen_kaydi_silinir(self):
        """Bekleyen süreç KeyboardInterrupt/SystemExit ile ölürse kuyruk başı tıkanmaz: kaydı her çıkışta silinir."""
        self.ayar()
        p = self.sahte_baslat("sahip", 4, 10)
        self.addCleanup(p.kill)
        self.sahip_bekle()
        for hata in (KeyboardInterrupt, SystemExit):
            sayac = {"n": 0}
            gercek = time.sleep

            def uyu(s, _h=hata):
                sayac["n"] += 1
                if sayac["n"] >= 3:  # kuyruğa yazıldıktan ve en az bir yoklamadan sonra kesil
                    raise _h()
                gercek(s)

            with mock.patch.object(K.time, "sleep", side_effect=uyu):
                with self.assertRaises(hata):
                    with K.kira(1, cikti=io.StringIO()):
                        pass
            self.assertEqual(K.durum()["bekleyenler"], [], hata.__name__)

    def test_gercek_test_paralel_kuyruga_girer(self):
        """Uçtan uca: tam bütçeli sahip varken test_paralel.py 'sıra: 2' yazar, sahip bırakınca koşar.

        Sahip sabit süre (eski: 2.0 sn) değil, koşucu 'sıra: 2' satırını basana kadar tutar. Kök neden: test_paralel.py
        kiradan ÖNCE önbellek anahtarını hesaplar (eklenti kökünün tam içerik özeti; isabette kira hiç alınmaz, doğru
        sıra budur). Önbellek açıkken (ADR-0131) içe aktarma + anahtar yük altında sahibin sabit süresini aşınca koşucu
        kuyruğa hiç girmiyordu; eski geçiş `onbellek: false` varsayılanına dayanıyordu. Olayla eşleme yarışı kaldırır."""
        self.ayar()
        tdir = os.path.join(self.d, "testler")
        os.makedirs(tdir)
        with open(os.path.join(tdir, "test_x.py"), "w", encoding="utf-8") as f:
            f.write("def test_x():\n    assert True\n")
        birak = os.path.join(self.d, "birak")
        p = self.sahte_baslat("sahip", 4, "dosya:" + birak)
        self.addCleanup(p.kill)
        self.sahip_bekle()
        kosu = subprocess.Popen([sys.executable, KOSUCU, "-n", "4", tdir], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=self.env,
                                cwd=self.d)
        self.addCleanup(kosu.kill)
        satirlar = []
        bitis = time.time() + 120
        for satir in kosu.stdout:  # 'sıra:' satırı görülene kadar sahip kirayı tutar
            satirlar.append(satir)
            if "kaynak kirası: sıra:" in satir or time.time() > bitis:
                break
        open(birak, "w").close()
        satirlar.append(kosu.communicate(timeout=120)[0])
        cikti = "".join(satirlar)
        self.assertEqual(kosu.returncode, 0, cikti)
        self.assertRegex(cikti, r"sıra: 2, sahip: \d+/sahte sahip")
        self.assertIn("kaynak kirası: alındı", cikti)
        self.assertIn("1 dosya, 0 düşen", cikti)


class OluSahipDevralma(Ortam):
    def test_k2_oldurulen_sahibin_kirasi_sure_dolunca_devralinir(self):
        self.ayar(sona_erme_s=2)
        p = self.sahte_baslat("sahip", 4, 120)
        self.addCleanup(p.kill)
        self.sahip_bekle()
        sahip_pid = K.durum()["sahipler"][0]["pid"]
        p.kill()  # Windows: TerminateProcess; POSIX: SIGKILL; finally bloğu koşmaz, kayıt kalır
        p.wait(timeout=10)
        self.assertFalse(K.pid_canli(sahip_pid))
        self.assertEqual(len(K.durum()["sahipler"]), 1)  # kayıt yerinde: ölü sahip
        olduruldu = time.time()
        buf = io.StringIO()
        with K.kira(4, komut="ikinci", cikti=buf) as k:
            gecen = time.time() - olduruldu
            self.assertEqual(k.devralinan, [sahip_pid])
        self.assertIn("sıra: 2, sahip: %d/sahte sahip" % sahip_pid, buf.getvalue())
        self.assertIn("devralındı: %d/" % sahip_pid, buf.getvalue())
        # son heartbeat ölümden en çok sona_erme/3 önce: devralma süre dolmadan olmaz, dolunca hemen olur
        self.assertGreaterEqual(gecen, 2 * 2 / 3 - 0.2, gecen)
        self.assertLess(gecen, 2 + 2.0, gecen)

    def test_canli_sahip_heartbeat_ile_sure_asar(self):
        """Sona erme süresinden uzun tutan canlı sahip düşürülmez (heartbeat)."""
        self.ayar(sona_erme_s=0.6, bekleme_ust_s=1.5)
        p = self.sahte_baslat("sahip", 4, 5)
        self.addCleanup(p.kill)
        self.sahip_bekle()
        with self.assertRaises(K.KiraZamanAsimi):
            with K.kira(4, cikti=io.StringIO()):
                pass

    def test_pid_canli(self):
        self.assertTrue(K.pid_canli(os.getpid()))
        self.assertFalse(K.pid_canli(0))
        self.assertFalse(K.pid_canli("x"))


class Modlar(Ortam):
    def test_k3_kapali_eski_davranis(self):
        self.ayar(mod="kapali")
        p = self.sahte_baslat("sahip", 4, 30)
        self.addCleanup(p.kill)
        time.sleep(1.0)
        self.assertFalse(os.path.exists(os.path.join(self.kira_dizini, "test_kosusu.json")))  # sahte koşucu da kayıt yazmadı
        buf = io.StringIO()
        t = time.time()
        with K.kira(16, cikti=buf) as k:
            self.assertLess(time.time() - t, 0.5)
            self.assertEqual((k.isci, k.mod, k.sira), (16, "kapali", 0))
        self.assertEqual(buf.getvalue(), "")
        self.assertFalse(os.path.exists(self.kira_dizini))

    def test_k3_ortam_degiskeni_kapatir(self):
        self.ayar(mod="ihlal")
        with mock.patch.dict(os.environ, {"ORKESTRA_KAYNAK_KIRA": "0"}):
            self.assertEqual(K.ayarlar()["mod"], "kapali")

    def test_k3_kapali_test_paralel_ciktisi_degismez(self):
        self.ayar(mod="kapali")
        tdir = os.path.join(self.d, "testler")
        os.makedirs(tdir)
        with open(os.path.join(tdir, "test_x.py"), "w", encoding="utf-8") as f:
            f.write("def test_x():\n    assert True\n")
        r = subprocess.run([sys.executable, KOSUCU, "-n", "3", tdir], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=self.env, cwd=self.d, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("kaynak kirası", r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"1 dosya, 0 düşen, 0 süre aşan, [\d.]+ s \(-n 3\) =====")

    def test_golge_kira_alinir_beklenmez_uyarir(self):
        self.ayar(mod="golge")
        with K.kira(4, komut="ilk", cikti=io.StringIO()):
            buf = io.StringIO()
            t = time.time()
            with mock.patch.object(K, "_golge_kaydet") as kayit, ayri_surec():
                with K.kira(4, komut="ikinci", cikti=buf) as k2:
                    self.assertLess(time.time() - t, 1.0)
                    self.assertEqual((k2.isci, k2.mod, k2.sira), (4, "golge", 2))
                    self.assertEqual(len(K.durum()["sahipler"]), 2)  # kira alındı, görünür
            kayit.assert_called_once()
            self.assertIn("sıra: 2, sahip: %d/ilk" % os.getpid(), kayit.call_args[0][1])
        self.assertIn("sıra: 2", buf.getvalue())
        self.assertIn("gölge", buf.getvalue())
        self.assertEqual(K.durum()["sahipler"], [])

    def test_golge_kapi_mod_kaydi(self):
        """Gölge kaydı kapi_mod.kaydet ile gunluk.jsonl'a kapi_golge olarak düşer."""
        sd = os.path.join(self.d, "proje", ".claude", "orkestra")
        os.makedirs(sd)
        with mock.patch.dict(os.environ, {"ORKESTRA_DURUM_YEREL": "1"}):
            K._golge_kaydet(os.path.join(self.d, "proje"), "sıra: 2, sahip: 1/x")
        with open(os.path.join(sd, "gunluk.jsonl"), encoding="utf-8") as f:
            satir = json.loads(f.readline())
        self.assertEqual((satir["tur"], satir["kapi"]), ("kapi_golge", "kaynak_kira"))

    def test_ic_ice_kosu_kira_almaz(self):
        self.ayar()
        with K.kira(4, cikti=io.StringIO()) as dis:
            self.assertEqual(os.environ.get(K.SAHIP_ENV), dis.kimlik)
            with K.kira(4, cikti=io.StringIO()) as ic:
                self.assertEqual(ic.mod, "ic_ice")
            self.assertEqual(len(K.durum()["sahipler"]), 1)
        self.assertNotIn(K.SAHIP_ENV, os.environ)

    def test_varsayilan_ayar_ihlal_onbellek_acik(self):
        """ADR-0131: kullanıcı kararıyla ihlal + önbellek açık; gölge ve kapalı davranışları yukarıda ayar ezmesiyle sınanır."""
        with open(os.path.join(KOK, "ayarlar", "kaynak_kira.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual((d["mod"], d["onbellek"]), ("ihlal", True))
        self.assertIn("ADR-0131", d["mod_gerekce"])
        self.assertIn("ADR-0131", d["onbellek_gerekce"])
        self.assertIn("sona_erme_s", d)
        self.assertIn("bekleme_ust_s", d)


if __name__ == "__main__":
    unittest.main()
