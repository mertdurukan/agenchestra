"""Oturum konum kaydı ve komşu çözücü (ADR-0125)."""
import json
import multiprocessing
import os
import subprocess
import sys
import time

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import oturum_farkindalik as F  # noqa: E402
import ork_lib as L  # noqa: E402


def _depo(yol):
    os.makedirs(yol, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(yol)], check=True)
    subprocess.run(["git", "-C", str(yol), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    return str(yol)


def _sd(tmp_path):
    sd = tmp_path / "durum"
    (sd / "oturumlar").mkdir(parents=True)
    return str(sd)


def test_git_konumu_ana_ve_worktree(tmp_path):
    ana = _depo(tmp_path / "ana")
    wt = str(tmp_path / "wt")
    subprocess.run(["git", "-C", ana, "worktree", "add", "-q", "-b", "dal-a", wt], check=True)
    a, w = F.git_konumu(ana), F.git_konumu(wt)
    assert a["depo"] == w["depo"] and a["ana"] and not w["ana"]
    assert a["dal"] == "main" and w["dal"] == "dal-a"
    assert F.git_konumu(str(tmp_path / "yok")) is None


def test_kaydet_ve_komsu_dosya_ve_yuzey(tmp_path):
    ana = _depo(tmp_path / "ana")
    wt = str(tmp_path / "wt")
    subprocess.run(["git", "-C", ana, "worktree", "add", "-q", "-b", "dal-a", wt], check=True)
    sd = _sd(tmp_path)
    assert F.kaydet(sd, "aaaa1111-0000", wt, dosya=os.path.join(wt, "x.py"), is_id="I-1")
    # B ana ağaçta: yüzey nedeniyle A'yı görür; çakışmasız (kendi dosyası) bile
    k = F.komsular(sd, "bbbb2222-0000", ana)
    assert [x["neden"] for x in k] == ["yuzey"] and k[0]["is"] == "I-1"
    # B de aynı dosyaya yazarsa neden 'dosya'
    k = F.komsular(sd, "bbbb2222-0000", ana, dosya=os.path.join(wt, "x.py"))
    assert k[0]["neden"] == "dosya"
    assert "aaaa1111" in F.satir(k) and len(F.satir(k)) <= 250
    assert F.satir([]) == ""  # çakışmasız: 0 karakter


def test_iki_ayri_worktree_yuzeysiz_sessiz(tmp_path):
    ana = _depo(tmp_path / "ana")
    w1, w2 = str(tmp_path / "w1"), str(tmp_path / "w2")
    subprocess.run(["git", "-C", ana, "worktree", "add", "-q", "-b", "d1", w1], check=True)
    subprocess.run(["git", "-C", ana, "worktree", "add", "-q", "-b", "d2", w2], check=True)
    sd = _sd(tmp_path)
    F.kaydet(sd, "aaaa1111-0000", w1)
    assert F.komsular(sd, "bbbb2222-0000", w2) == []
    # ama dal/ağaç değiştiren git komutunda depo nedeniyle görünür
    assert F.komsular(sd, "bbbb2222-0000", w2, git_islemi=True)[0]["neden"] == "depo"
    assert F.git_yazan_komut("git -C x rebase main") and not F.git_yazan_komut("git status")


def test_bayat_oturum_gorunmez_ve_baska_depo(tmp_path):
    a, b = _depo(tmp_path / "a"), _depo(tmp_path / "b")
    sd = _sd(tmp_path)
    t0 = time.time()
    F.kaydet(sd, "aaaa1111-0000", a, simdi=t0)
    assert F.komsular(sd, "bbbb2222-0000", a, simdi=t0 + 60)[0]["neden"] == "dal"
    assert F.komsular(sd, "bbbb2222-0000", a, simdi=t0 + 31 * 60) == []
    assert F.komsular(sd, "bbbb2222-0000", b, simdi=t0 + 60) == []


def test_kapatma_ve_uyar_bir_kez(tmp_path, monkeypatch):
    a = _depo(tmp_path / "a")
    sd = _sd(tmp_path)
    assert F.kaydet(sd, "aaaa1111-0000", a)
    assert F.uyar_bir_kez(sd, "aaaa1111-0000", "k1") and not F.uyar_bir_kez(sd, "aaaa1111-0000", "k1")
    monkeypatch.setenv("ORKESTRA_OTURUM_FARKINDALIK", "0")
    assert not F.kaydet(sd, "cccc3333-0000", a) and F.komsular(sd, "bbbb2222-0000", a) == []


def _yaz(sd, depo, i):
    for j in range(15):
        F.kaydet(sd, "ssss0000-0000", depo, dosya=os.path.join(depo, f"d{i}_{j}.py"))


def test_eszamanli_yazim_kaydi_bozmaz(tmp_path):
    a = _depo(tmp_path / "a")
    sd = _sd(tmp_path)
    ps = [multiprocessing.Process(target=_yaz, args=(sd, a, i)) for i in range(3)]
    [p.start() for p in ps]
    [p.join(60) for p in ps]
    with open(os.path.join(sd, "oturumlar", "ssss0000-0000.json"), encoding="utf-8") as f:
        d = json.load(f)
    assert len(d["konum"]["yazilan"]) == F.YAZILAN_EN_COK or len(d["konum"]["yazilan"]) == 45


def test_not_birak_oku_bir_kez_ve_sir_reddi(tmp_path):
    a = _depo(tmp_path / "a")
    sd = _sd(tmp_path)
    F.kaydet(sd, "aaaa1111-0000", a)
    hedef, hata = F.hedef_coz(sd, "aaaa")
    assert hedef == "aaaa1111-0000" and not hata
    assert F.hedef_coz(sd, "zz")[0] is None and F.hedef_coz(sd, "bbbb")[0] is None
    ok, _ = F.not_birak(sd, hedef, "bbbb2222-0000", "main'i ff etme, rebase yapıyorum")
    assert ok
    assert not F.not_birak(sd, hedef, "bbbb2222-0000", "password: hunter2xx")[0]
    assert not F.not_birak(sd, hedef, "bbbb2222-0000", "x" * 301)[0]
    m = F.gelen_metin(sd, hedef)
    assert "VERİ" in m and "main'i ff etme" in m and "bbbb2222" in m
    assert F.gelen_metin(sd, hedef) == ""  # ikinci okumada yok
    F.not_birak(sd, hedef, "bbbb2222-0000", "ikinci")
    assert "ikinci" in F.gelen_metin(sd, hedef)


def test_aday_onbellegi_yeni_komsuyu_taze_taramada_gorur(tmp_path):
    """arac_oncesi yolu (taze=False) aday listesini ADAY_S boyunca önbellekten okur; taze tarama (SessionStart) yeni komşuyu hemen görür."""
    import json as _j
    sd = str(tmp_path / "sd")
    os.makedirs(os.path.join(sd, "oturumlar"))
    repo = str(tmp_path / "r")
    os.makedirs(repo)
    subprocess.run(["git", "init", "-q", repo], check=True)
    assert F.kaydet(sd, "aaaaaaaa-0000", repo)
    F.komsular(sd, "bbbbbbbb-0000", repo, taze=False)  # önbelleği doldurur
    assert F.kaydet(sd, "cccccccc-0000", repo)  # önbellekten sonra doğan komşu
    adlar = _j.load(open(os.path.join(sd, "oturum_adaylar.json"), encoding="utf-8"))["konumlar"]
    assert "cccccccc-0000.json" not in adlar
    assert any(k["oturum"] == "cccccccc-0000" for k in F.komsular(sd, "bbbbbbbb-0000", repo))  # taze


def test_ihlal_modunda_uyari_oneki_ve_kapi_ihlal_kaydi(tmp_path):
    k = [{"oturum": "bbbbbbbb-0000", "neden": "dal", "dal": "main", "is": None, "dk": 1}]
    assert not F.satir(k).startswith("UYARI") and F.satir(k, mod="ihlal").startswith("UYARI: ")
    assert len(F.satir(k, "git komutu dal/ağacı değiştirebilir. ", "ihlal")) <= 250
    sd = str(tmp_path)
    F.golge_yaz(sd, "aaaaaaaa-0000", k[0], None, "arac_oncesi", "ihlal")
    F.golge_yaz(sd, "aaaaaaaa-0000", k[0], None, "arac_oncesi")
    turler = [json.loads(x)["tur"] for x in open(os.path.join(sd, "gunluk.jsonl"), encoding="utf-8")]
    assert turler == ["kapi_ihlal", "kapi_golge"]


# ---------------------------------------------------------------- bağlam paketi ve devir (I-324 P3, S4/S5/S8)

def _is_kur(tmp_path, sd, notlar):
    """Merkez kayıtta I-9 ve iş klasöründe todo.md (verilen '- [x]' notlarıyla)."""
    klasor = tmp_path / "is9"
    klasor.mkdir()
    (klasor / "is.json").write_text(json.dumps({"id": "I-9", "baslik": "Todo çakışması"}), encoding="utf-8")
    satirlar = ["# Todo", "- [ ] P9: bitmedi — kanıt: görünmemeli"]
    satirlar += [f"- [x] P{i}: madde {i} — 2026-11-01: {n}" for i, n in enumerate(notlar, 1)]
    (klasor / "todo.md").write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    with open(os.path.join(sd, "isler.json"), "w", encoding="utf-8") as f:
        json.dump({"isler": {"I-9": {"klasor": str(klasor), "baslik": "Todo çakışması", "durum": "acik"}}}, f)
    return str(klasor)


def _sahip_kur(tmp_path, sd, t0):
    """Sahip oturum scripts/x.py yazmış; tests/test_x.py düşer. (depo, test yolu, kaynak yolu)"""
    import test_atif as A
    depo = _depo(tmp_path / "d")
    kaynak = os.path.join(depo, "scripts", "x.py")
    F.kaydet(sd, "aaaa1111-0000", depo, dosya=kaynak, is_id="I-9", simdi=t0)
    test = os.path.join(depo, "tests", "test_x.py")
    return A, test, kaynak


def test_paket_olustur_todo_kanit_notlari_ve_sinirlar(tmp_path):
    sd = _sd(tmp_path)
    notlar = [f"kanıt: pytest tests/test_{i}.py => {i} passed" for i in range(12)] + ["kanıt: password: hunter2xx"]
    notlar.append("kanıt: " + "uzun " * 60)
    _is_kur(tmp_path, sd, notlar)
    p = F.paket_olustur(sd, "I-9", [f"d{i}.py" for i in range(25)], test="tests/test_x.py::test_a")
    assert p["is_id"] == "I-9" and p["baslik"] == "Todo çakışması" and p["test"] == "tests/test_x.py::test_a"
    kn = p["todo_kanit_notlari"]
    assert len(kn) == F.PAKET_NOT_EN_COK and all(len(n) <= F.PAKET_NOT_UZUNLUK for n in kn)
    assert not any("hunter2" in n for n in kn)  # sır kalıbı taşıyan not pakete girmez
    assert not any("görünmemeli" in n for n in kn)  # açık madde kanıt sayılmaz
    assert kn[-1].endswith("…")  # uzun not kısaltıldı
    assert len(p["yazilan_dosyalar"]) == F.PAKET_DOSYA_EN_COK and p["yazilan_dosyalar"][-1] == "d24.py"
    bos = F.paket_olustur(sd, "I-yok", [])
    assert bos["todo_kanit_notlari"] == [] and bos["baslik"] == "" and "test" not in bos


def test_paket_canli_sahibe_gelen_kutusuna_duser(tmp_path):
    sd = _sd(tmp_path)
    _is_kur(tmp_path, sd, ["kanıt: pytest => 3 passed"])
    t0 = time.time()
    A, test, kaynak = _sahip_kur(tmp_path, sd, t0)
    atif = A.sahip_bul(sd, test, [{"dosya": kaynak, "tur": "ad_kurali"}], simdi=t0 + 60, test_adi="test_a")
    assert atif["sahip"] == "aaaa1111-0000" and atif["canli"]
    assert F.cozum_sorumlusu(atif) == "sahip"
    p = F.paket_olustur(sd, "I-9", [kaynak], test=atif["test"])
    y = F.paket_yonlendir(sd, "bbbb2222-0000", atif, p)
    assert y["sorumlu"] == "sahip" and y["hedef"] == "aaaa1111-0000" and y["birakildi"], y
    m = F.gelen_metin(sd, "aaaa1111-0000")
    assert "Bağlam paketi I-9" in m and "test_x.py::test_a" in m and "x.py" in m and "3 passed" in m
    assert "bbbb2222" in m  # koşan oturum kimden olarak görünür


def test_paket_olu_ve_sahipsiz_kosana_doner(tmp_path):
    sd = _sd(tmp_path)
    t0 = time.time()
    A, test, kaynak = _sahip_kur(tmp_path, sd, t0)
    olu = A.sahip_bul(sd, test, [{"dosya": kaynak, "tur": "ad_kurali"}], simdi=t0 + 31 * 60)
    assert olu["sahip"] == "aaaa1111-0000" and not olu["canli"]
    p = F.paket_olustur(sd, "I-9", [kaynak], test=olu["test"])
    for atif in (olu, {"test": test, "sahip": None, "kanit": None, "canli": False}, None):
        assert F.cozum_sorumlusu(atif) == "kosan"
        y = F.paket_yonlendir(sd, "bbbb2222-0000", atif, p)
        assert y["sorumlu"] == "kosan" and y["hedef"] == "bbbb2222-0000" and not y["birakildi"]
        assert "Bağlam paketi I-9" in y["metin"]  # paket koşana metin olarak döner
    assert not os.path.exists(F.gelen_yol(sd, "aaaa1111-0000"))  # ölü sahibin kutusuna yazılmadı
    assert not os.path.exists(F.gelen_yol(sd, "bbbb2222-0000"))  # yeni kanal yok: koşana kutu değil, metin


def test_paket_sir_kalibi_reddedilir(tmp_path):
    sd = _sd(tmp_path)
    for kn in (["token=abcd1234efgh"], ["sk-" + "A" * 20], ["X" * 45]):
        p = {"is_id": "I-9", "baslik": "", "todo_kanit_notlari": kn, "yazilan_dosyalar": []}
        ok, hata = F.paket_birak(sd, "aaaa1111-0000", "bbbb2222-0000", p)
        assert not ok and "sır" in hata
        y = F.paket_yonlendir(sd, "bbbb2222-0000", {"sahip": None}, p)
        assert not y["birakildi"] and y["metin"] == "" and "sır" in y["hata"]  # koşana da sır dönmez
    assert not os.path.exists(F.gelen_yol(sd, "aaaa1111-0000"))
    # kimlik alanındaki uzun ad (test adı, dosya adı) sır sayılmaz: belirteç kırpılır
    uzun = "test_" + "cok_uzun_bir_test_adi_" * 3
    p = {"is_id": "I-9", "test": f"tests/test_x.py::{uzun}", "yazilan_dosyalar": ["a/" + "b" * 50 + ".py"]}
    ok, hata = F.paket_birak(sd, "aaaa1111-0000", "bbbb2222-0000", p)
    assert ok, hata


def test_paket_uzunluk_siniri(tmp_path):
    sd = _sd(tmp_path)
    p = {"is_id": "I-9", "baslik": "b", "todo_kanit_notlari": ["kanıt: " + "uzun not " * 12] * 10,
         "yazilan_dosyalar": [f"scripts/d{i}.py" for i in range(20)], "test": "tests/test_x.py::test_a"}
    assert len(F.paket_metni(p)) > F.NOT_EN_COK
    ok, hata = F.paket_birak(sd, "aaaa1111-0000", "bbbb2222-0000", p)
    assert ok, hata
    with open(F.gelen_yol(sd, "aaaa1111-0000"), encoding="utf-8") as f:
        kayit = json.loads(f.readline())
    assert len(kayit["metin"]) <= F.NOT_EN_COK and kayit["metin"].endswith("…")
    assert "(+15)" in kayit["metin"]  # dosya listesi özetlenir
    assert len(F.paket_yonlendir(sd, "bbbb2222-0000", {"sahip": None}, p)["metin"]) <= F.NOT_EN_COK


def test_paket_devret_isaret_metni_ve_sahibe_paket(tmp_path):
    sd = _sd(tmp_path)
    _is_kur(tmp_path, sd, ["kanıt: pytest => 2 passed"])
    depo = _depo(tmp_path / "d")
    F.kaydet(sd, "bbbb2222-0000", depo, dosya=os.path.join(depo, "scripts", "y.py"), is_id="I-9")
    F.kaydet(sd, "aaaa1111-0000", depo, is_id="I-9")
    d = F.devret(sd, "bbbb2222-0000", "aaaa1111-0000", "I-9", 3, "paket_birak ekle")
    assert d["isaret"] == "devredildi → I-9#3"
    assert d["birakildi"] and not d["hata"]
    assert d["paket"]["madde"] == "#3 paket_birak ekle" and any(x.endswith("y.py") for x in d["paket"]["yazilan_dosyalar"])
    m = F.gelen_metin(sd, "aaaa1111-0000")
    assert "madde: #3 paket_birak ekle" in m and "y.py" in m and "2 passed" in m
    assert F.devret(sd, "bbbb2222-0000", "aaaa1111-0000", "I-9", 4, "token: gizli123")["paket"].get("madde") is None
