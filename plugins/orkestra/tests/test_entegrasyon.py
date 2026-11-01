"""Entegrasyon şeridi (I-323 P3; sözleşme S2, S3, S6, S8): tek tam koşu, bisect, karantina, flaky, ff yarışı, kurtarma.

Her test geçici bir git deposunda ve geçici durum dizininde çalışır; gerçek depoya git yazmaz. Test komutu enjekte
edilir (callable ya da komut listesi); kırmızı/yeşil, birleşik ağaçtaki dosya içeriğinden belirlenir.
"""
import os
import subprocess
import sys
import time

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import entegrasyon as E  # noqa: E402
import kuyruk as K  # noqa: E402

_SIZINTI = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")


def _git(cwd, *args, env_ek=None):
    env = {k: v for k, v in os.environ.items() if k not in _SIZINTI}
    env.update(env_ek or {})
    r = subprocess.run(["git", "-c", "safe.directory=*", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _depo(tmp_path, teslimler):
    """teslimler: [(ad, dosya_icerigi)] -> her biri main'den dallanan `dal-<ad>` dalında `<ad>.txt` ekler.
    Ana ağaç sonunda ayrık HEAD'e geçer (main hiçbir ağaçta çıkılı değil)."""
    depo = str(tmp_path / "depo")
    os.makedirs(depo)
    _git(depo, "init", "-q", "-b", "main")
    _git(depo, "config", "user.name", "test")
    _git(depo, "config", "user.email", "test@example.invalid")
    with open(os.path.join(depo, "taban.txt"), "w", encoding="utf-8") as f:
        f.write("taban\n")
    _git(depo, "add", "taban.txt")
    _git(depo, "commit", "-q", "-m", "taban")
    for ad, icerik in teslimler:
        _git(depo, "checkout", "-q", "-b", f"dal-{ad}", "main")
        with open(os.path.join(depo, f"{ad}.txt"), "w", encoding="utf-8") as f:
            f.write(icerik)
        _git(depo, "add", f"{ad}.txt")
        _git(depo, "commit", "-q", "-m", ad)
    _git(depo, "checkout", "-q", "--detach", "main")
    return depo


def _sd(tmp_path, depo, teslimler):
    sd = str(tmp_path / "durum")
    os.makedirs(sd)
    for ad, _ in teslimler:
        K.ekle(sd, ad, f"oturum-{ad}", f"dal-{ad}")
    return sd


def _icerikler(agac):
    return {a: open(os.path.join(agac, a), encoding="utf-8").read() for a in os.listdir(agac) if a.endswith(".txt")}


class _Sayac:
    """Kırmızı kuralı: herhangi bir dosyada KIRMIZI geçerse kırmızı."""

    def __init__(self, kural=None):
        self.n = 0
        self.kural = kural or (lambda ic: not any("KIRMIZI" in v for v in ic.values()))

    def __call__(self, agac):
        self.n += 1
        ok = self.kural(_icerikler(agac))
        return ok, "" if ok else "FAILED test_ornek"


def _main_dosyalari(depo):
    return set(_git(depo, "ls-tree", "--name-only", "main").splitlines())


def test_8_teslimde_tek_suclu_en_cok_4_bisect_kosusunda_bulunur(tmp_path):
    teslimler = [(f"t{i}", "KIRMIZI\n" if i == 6 else f"ok{i}\n") for i in range(1, 9)]
    depo = _depo(tmp_path, teslimler)
    sd = _sd(tmp_path, depo, teslimler)
    test, bildirimler = _Sayac(), []
    s = E.entegre_et(sd, depo, test_komutu=test, kanca=bildirimler.append)
    assert [k["teslim"] for k in s["karantina"]] == ["t6"]
    assert s["bisect_kosu"] <= 4 and s["bisect_kosu"] == 3  # log2(8)
    assert s["kosu"] == test.n == 6  # tam + flaky tekrarı + 3 bisect + suçlusuz yeniden koşu
    assert s["durum"] == "birlesti" and sorted(s["birlesen"]) == sorted(f"t{i}" for i in range(1, 9) if i != 6)
    assert bildirimler and bildirimler[0]["teslim"] == "t6" and bildirimler[0]["oturum"] == "oturum-t6"
    assert "FAILED" in bildirimler[0]["gunluk"]
    durumlar = {k["teslim"]: k["durum"] for k in K.liste(sd)}
    assert durumlar["t6"] == "karantina" and sum(d == "birlesti" for d in durumlar.values()) == 7
    assert "t6.txt" not in _main_dosyalari(depo) and "t5.txt" in _main_dosyalari(depo)
    assert K.kosucu(sd) == {}  # kilit bırakıldı


def test_iki_bagimsiz_suclu_ikisi_de_bulunur(tmp_path):
    teslimler = [(f"t{i}", "KIRMIZI\n" if i in (3, 6) else f"ok{i}\n") for i in range(1, 9)]
    depo = _depo(tmp_path, teslimler)
    sd = _sd(tmp_path, depo, teslimler)
    s = E.entegre_et(sd, depo, test_komutu=_Sayac())
    assert sorted(k["teslim"] for k in s["karantina"]) == ["t3", "t6"]
    assert len(s["birlesen"]) == 6 and s["durum"] == "birlesti"
    assert not ({"t3.txt", "t6.txt"} & _main_dosyalari(depo))


def test_etkilesim_hatasinda_son_eklenen_atanir(tmp_path):
    teslimler = [("t1", "A\n"), ("t2", "B\n"), ("t3", "C\n")]
    depo = _depo(tmp_path, teslimler)
    sd = _sd(tmp_path, depo, teslimler)

    def kural(ic):  # t1 ve t2 ayrı ayrı yeşil, birlikte kırmızı
        return not ("A\n" in ic.values() and "B\n" in ic.values())
    assert kural({"t1.txt": "A\n"}) and kural({"t2.txt": "B\n"})
    s = E.entegre_et(sd, depo, test_komutu=_Sayac(kural))
    assert [k["teslim"] for k in s["karantina"]] == ["t2"]
    assert "son eklenen" in s["karantina"][0]["neden"]
    assert sorted(s["birlesen"]) == ["t1", "t3"]


def test_flaky_kirmizi_yeniden_kosuda_yesil(tmp_path):
    teslimler = [("t1", "a\n"), ("t2", "b\n"), ("t3", "c\n")]
    depo = _depo(tmp_path, teslimler)
    sd = _sd(tmp_path, depo, teslimler)
    cagri = []

    def bir_kez_kirmizi(agac):
        cagri.append(1)
        return len(cagri) > 1
    s = E.entegre_et(sd, depo, test_komutu=bir_kez_kirmizi)
    assert s["flaky"] and s["kosu"] == 2 and s["bisect_kosu"] == 0
    assert s["karantina"] == [] and sorted(s["birlesen"]) == ["t1", "t2", "t3"]


def test_ff_yarisinda_yeniden_temellendirme(tmp_path, tmp_path_factory):
    teslimler = [("t1", "a\n"), ("t2", "b\n")]
    depo = _depo(tmp_path, teslimler)
    sd = _sd(tmp_path, depo, teslimler)
    cagri = []

    def yaris(agac):
        """İlk koşu sürerken başka bir oturum main'e yazar (geçici indeksle commit, GELISTIRME.md yöntemi)."""
        cagri.append(1)
        if len(cagri) == 1:
            eski = _git(depo, "rev-parse", "main")
            idx = {"GIT_INDEX_FILE": str(tmp_path_factory.mktemp("idx") / "index")}
            _git(depo, "read-tree", eski, env_ek=idx)
            blob = subprocess.run(["git", "-c", "safe.directory=*", "hash-object", "-w", "--stdin"], cwd=depo,
                                  input="yaris\n", capture_output=True, text=True).stdout.strip()
            _git(depo, "update-index", "--add", "--cacheinfo", f"100644,{blob},yaris.txt", env_ek=idx)
            agac_sha = _git(depo, "write-tree", env_ek=idx)
            yeni = _git(depo, "commit-tree", agac_sha, "-p", eski, "-m", "yaris")
            _git(depo, "update-ref", "refs/heads/main", yeni, eski)
        return True
    s = E.entegre_et(sd, depo, test_komutu=yaris)
    assert s["yeniden_temel"] == 1 and s["kosu"] == 2 and s["durum"] == "birlesti"
    assert {"yaris.txt", "t1.txt", "t2.txt"} <= _main_dosyalari(depo)
    yaris_sha = _git(depo, "log", "--format=%H", "-1", "main", "--", "yaris.txt")
    _git(depo, "merge-base", "--is-ancestor", yaris_sha, "main")  # yarışan commit kaybolmadı (yalnız ff)


def test_bayat_kosucu_kurtarma(tmp_path):
    teslimler = [("t1", "a\n"), ("t2", "b\n")]
    depo = _depo(tmp_path, teslimler)
    sd = _sd(tmp_path, depo, teslimler)
    t0 = time.time() - 100
    assert K.kosucu_al(sd, "olu-kosucu", simdi=t0)
    K.gecis(sd, "t1", "kosuyor")
    assert K.kurtar(sd, simdi=t0 + 29) == []  # kilit hâlâ canlı: dokunulmaz
    assert K.liste(sd, "kosuyor")[0]["teslim"] == "t1"
    assert K.kurtar(sd, sahip="baska", simdi=t0 + 10) == []  # canlı başka sahip
    # kilit bayat: yeni koşucu devralır, ölünün bıraktığı t1 bekliyor'a döner ve bu turda birleşir
    s = E.entegre_et(sd, depo, test_komutu=_Sayac(), sahip="yeni-kosucu")
    assert s["kurtarilan"] == ["t1"]
    assert s["durum"] == "birlesti" and sorted(s["birlesen"]) == ["t1", "t2"]
    olaylar = [o for o in K.L.jsonl_oku(K.kuyruk_yolu(sd)) if o.get("teslim") == "t1"]
    assert [o["durum"] for o in olaylar] == ["bekliyor", "kosuyor", "bekliyor", "kosuyor", "birlesti"]


def test_kurtar_kilit_yokken_ve_canli_kosucu_varken(tmp_path):
    sd = str(tmp_path / "durum")
    os.makedirs(sd)
    K.ekle(sd, "t1", "o", "dal-a")
    K.gecis(sd, "t1", "kosuyor")
    assert K.kosucu_al(sd, "canli")
    assert K.kurtar(sd) == []  # canlı koşucu: dokunulmaz
    assert K.kosucu_birak(sd, "canli")
    assert K.kurtar(sd) == ["t1"]  # kilit yok: sahipsiz
    k = K.liste(sd)[0]
    assert k["durum"] == "bekliyor" and k["sira"] == 1 and "kurtarıldı" in k["neden"]


def test_tam_paket_tek_kosu_yesilde_ve_komut_listesi(tmp_path):
    teslimler = [(f"t{i}", f"ok{i}\n") for i in range(1, 6)]
    depo = _depo(tmp_path, teslimler)
    sd = _sd(tmp_path, depo, teslimler)
    sayac = tmp_path / "kosular.txt"
    komut = [sys.executable, "-c",
             f"open({str(sayac)!r}, 'a').write('1\\n'); import os; "
             "raise SystemExit(0 if all(os.path.exists(f't{i}.txt') for i in range(1, 6)) else 1)"]
    eski = _git(depo, "rev-parse", "main")
    s = E.entegre_et(sd, depo, test_komutu=komut)
    assert s["kosu"] == 1 and sayac.read_text().count("1") == 1  # 5 teslim, tam paket bir kez
    assert s["durum"] == "birlesti" and len(s["birlesen"]) == 5
    _git(depo, "merge-base", "--is-ancestor", eski, "main")  # yalnız ileri alındı
    assert _git(depo, "worktree", "list").count("\n") == 0  # geçici worktree kaldırıldı


def test_mesgul_bos_ve_cikili_hedef(tmp_path):
    teslimler = [("t1", "a\n")]
    depo = _depo(tmp_path, teslimler)
    sd = _sd(tmp_path, depo, teslimler)
    assert K.kosucu_al(sd, "baska")
    assert E.entegre_et(sd, depo, test_komutu=_Sayac())["durum"] == "mesgul"
    assert K.kosucu_birak(sd, "baska")
    _git(depo, "checkout", "-q", "main")  # main çıkılı: update-ref o ağacı eski bırakacağı için ilerletilmez
    s = E.entegre_et(sd, depo, test_komutu=_Sayac())
    assert s["durum"] == "hedef_cikili" and K.liste(sd)[0]["durum"] == "bekliyor"
    _git(depo, "checkout", "-q", "--detach", "main")
    assert E.entegre_et(sd, depo, test_komutu=_Sayac())["durum"] == "birlesti"
    assert E.entegre_et(sd, depo, test_komutu=_Sayac())["durum"] == "bos"


def test_cakisan_teslim_karantinaya_kalanlar_birlesir(tmp_path):
    depo = _depo(tmp_path, [("t1", "a\n")])
    _git(depo, "checkout", "-q", "-b", "dal-t2", "main")
    with open(os.path.join(depo, "t1.txt"), "w", encoding="utf-8") as f:
        f.write("cakisma\n")
    _git(depo, "add", "t1.txt")
    _git(depo, "commit", "-q", "-m", "t2")
    _git(depo, "checkout", "-q", "--detach", "main")
    sd = str(tmp_path / "durum")
    os.makedirs(sd)
    K.ekle(sd, "t1", "o1", "dal-t1")
    K.ekle(sd, "t2", "o2", "dal-t2")
    K.ekle(sd, "t3", "o3", "dal-yok")
    s = E.entegre_et(sd, depo, test_komutu=_Sayac())
    assert sorted(k["teslim"] for k in s["karantina"]) == ["t2", "t3"] and s["birlesen"] == ["t1"]
    assert s["kosu"] == 1
