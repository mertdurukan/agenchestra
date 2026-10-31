"""İki git çalışma ağacından eşzamanlı `is_kaydi.klasor_ayir` aynı NNN'yi vermez (I-309 P2, ADR-0033).

Gerçek `git worktree` ile ana ağaç + oturum ağacı kurulur; iki ağaç aynı durum dizinini (sd) görür. Her ağaç için
bir uzun ömürlü işçi süreç açılır; her turda ikisi dosya tabanlı başlangıç bayrağını bekler (bariyer) ve aynı anda
`klasor_ayir` çağırır. 100 turun her birinde iki NNN farklı olmalıdır. Worktree bir kez kurulur, turlar arasında
yalnız iş klasörleri silinir.
`PYTHONUTF8=1 python -m pytest plugins/orkestra/tests/test_klasor_numara_esz.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402

TUR = 100
BEKLEME_S = 60.0

# İşçi: sd'yi kendi ağacından çözer (paylaşım kanıtı), her tur bayrağı bekler, klasor_ayir çağırır, sonucu yazar.
ISCI = r"""
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
agac, kok, bayrak, ad, tur = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6])
import ork_lib as L
import is_kaydi as K
sd = L.durum_dizini(agac)
with open(os.path.join(bayrak, "hazir_" + ad), "w", encoding="utf-8") as f:
    f.write(json.dumps({"sd": sd}))
for i in range(tur):
    basla = os.path.join(bayrak, "basla_%03d" % i)
    while not os.path.exists(basla):  # bariyer: iki işçi de aynı bayrağı döngüde bekler
        pass
    t0 = time.perf_counter()
    try:
        sonuc = {"ad": K.klasor_ayir(sd, kok, "esz", tarih="20261101")}
    except Exception as e:
        sonuc = {"hata": repr(e)}
    sonuc["t0"], sonuc["t1"] = t0, time.perf_counter()
    gecici = os.path.join(bayrak, "sonuc_%03d_%s.tmp" % (i, ad))
    with open(gecici, "w", encoding="utf-8") as f:
        f.write(json.dumps(sonuc))
    os.replace(gecici, gecici[:-4])
"""


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


def n(yol):
    return os.path.normcase(os.path.realpath(yol)).replace("\\", "/").rstrip("/")


def bekle(yollar, zaman_asimi=BEKLEME_S):
    son = time.monotonic() + zaman_asimi
    while not all(os.path.exists(y) for y in yollar):
        if time.monotonic() > son:
            raise AssertionError(f"bekleme zaman aşımı: {[y for y in yollar if not os.path.exists(y)]}")
        time.sleep(0.001)


def oku_json(yol, deneme=200):
    """Windows'ta os.replace hemen ardından dosya kısa süre paylaşım ihlali verebilir: kısa beklemeyle yeniden dene."""
    for _ in range(deneme):
        try:
            with open(yol, encoding="utf-8") as f:
                return json.load(f)
        except PermissionError:
            time.sleep(0.005)
    raise AssertionError(f"okunamadı: {yol}")


class KlasorNumaraEszamanli(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_kne_"))
        self.ana = os.path.join(self.taban, "depo")
        os.makedirs(os.path.join(self.ana, ".claude", "orkestra"))
        git(self.ana, "init", "-q", "-b", "main")
        git(self.ana, "config", "user.name", "Test")
        git(self.ana, "config", "user.email", "test@example.invalid")
        with open(os.path.join(self.ana, ".gitignore"), "w", encoding="utf-8", newline="\n") as f:
            f.write(".claude/orkestra/\n.claude/worktrees/\nisler/\n")
        with open(os.path.join(self.ana, "a.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("bir\n")
        git(self.ana, "add", ".")
        git(self.ana, "commit", "-q", "-m", "ilk")
        self.wt = os.path.join(self.ana, ".claude", "worktrees", "oturum-ab12cd")
        git(self.ana, "worktree", "add", "-q", "-b", "claude/oturum-ab12cd", self.wt)
        # uygulamanın yaptığı gibi git dışı durum kopyası oturum ağacına konur
        shutil.copytree(os.path.join(self.ana, ".claude", "orkestra"), os.path.join(self.wt, ".claude", "orkestra"))
        self.kokler = {"ana": os.path.join(self.ana, "isler"), "wt": os.path.join(self.wt, "isler")}
        for k in self.kokler.values():
            os.makedirs(k)
        self.bayrak = os.path.join(self.taban, "bayrak")
        os.makedirs(self.bayrak)
        self.env = dict(os.environ, PYTHONUTF8="1")
        for k in ("CLAUDE_PROJECT_DIR", L.DURUM_YEREL_ORTAM):
            self.env.pop(k, None)
            os.environ.pop(k, None)

    def tearDown(self):
        subprocess.run(["git", "-C", self.ana, "worktree", "remove", "--force", self.wt], capture_output=True)
        shutil.rmtree(self.taban, ignore_errors=True)

    def test_iki_agac_ayni_sd_yi_paylasir(self):  # K2: oturum ağacının durumu ana ağaca çözülür
        self.assertEqual(n(L.durum_dizini(self.wt)), n(L.durum_dizini(self.ana)))
        self.assertEqual(n(L.durum_dizini(self.ana)), n(os.path.join(self.ana, ".claude", "orkestra")))

    def test_esz_iki_agac_100_turda_farkli_nnn(self):  # K1
        isciler = {}
        for ad, kok in self.kokler.items():
            agac = self.ana if ad == "ana" else self.wt
            isciler[ad] = subprocess.Popen(
                [sys.executable, "-c", ISCI, os.path.join(KOK, "scripts"), agac, kok, self.bayrak, ad, str(TUR)],
                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            bekle([os.path.join(self.bayrak, "hazir_" + a) for a in isciler])
            sdler = set()
            for a in isciler:
                sdler.add(n(oku_json(os.path.join(self.bayrak, "hazir_" + a))["sd"]))
            self.assertEqual(sdler, {n(os.path.join(self.ana, ".claude", "orkestra"))}, "işçiler aynı sd'yi görmedi")

            cakisma, ust_uste = [], 0
            for i in range(TUR):
                for kok in self.kokler.values():  # yalnız iş klasörleri temizlenir; worktree yerinde kalır
                    for a in os.listdir(kok):
                        shutil.rmtree(os.path.join(kok, a))
                open(os.path.join(self.bayrak, "basla_%03d" % i), "w").close()
                yollar = {a: os.path.join(self.bayrak, "sonuc_%03d_%s" % (i, a)) for a in isciler}
                bekle(yollar.values())
                sonuc = {}
                for a, y in yollar.items():
                    sonuc[a] = oku_json(y)
                hatalar = {a: s["hata"] for a, s in sonuc.items() if "hata" in s}
                self.assertFalse(hatalar, f"tur {i}: {hatalar}")
                nolar = {a: s["ad"][:3] for a, s in sonuc.items()}
                if len(set(nolar.values())) != len(nolar):
                    cakisma.append((i, sonuc["ana"]["ad"], sonuc["wt"]["ad"]))
                s1, s2 = sonuc["ana"], sonuc["wt"]
                if s1["t0"] < s2["t1"] and s2["t0"] < s1["t1"]:  # iki çağrının süresi kesişti: bariyer işledi
                    ust_uste += 1
                for a, s in sonuc.items():  # klasör gerçekten kendi ağacında oluştu
                    self.assertTrue(os.path.isdir(os.path.join(self.kokler[a], s["ad"])), (i, a, s["ad"]))
            print(f"\n[klasor_numara_esz] tur={TUR} cakisma={len(cakisma)} ust_uste={ust_uste}", file=sys.stderr)
            self.assertEqual(cakisma, [], f"aynı NNN (tur, ana, wt): {cakisma}")
            self.assertGreaterEqual(ust_uste, TUR // 2, f"çağrılar yeterince eşzamanlı değil: {ust_uste}/{TUR}")
        finally:
            for p in isciler.values():
                try:
                    p.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
                if p.returncode not in (0, None):
                    print(p.stderr.read() if p.stderr else "", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
