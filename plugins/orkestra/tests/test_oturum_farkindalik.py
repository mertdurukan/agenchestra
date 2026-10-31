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
