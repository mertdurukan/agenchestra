"""Teslim kuyruğu (I-323 P2; sözleşme S1, S7): eşzamanlı ekleme, durum geçişleri, bayat ve tek-koşucu kilidi, CLI.

Her test geçici dizinde çalışır; gerçek durum dizinine yazmaz.
"""
import json
import multiprocessing
import os
import sys
import time

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kuyruk as K  # noqa: E402
import ic_kos  # noqa: E402  (CLI'yi süreç içinde koşar)

CLI = os.path.join(KOK, "scripts", "orkestra.py")


def _sd(tmp_path):
    sd = tmp_path / "proje" / ".claude" / "orkestra"
    sd.mkdir(parents=True)
    return str(sd)


def _ekle_isci(sd, i):
    sys.path.insert(0, os.path.join(KOK, "scripts"))
    import kuyruk as K2
    K2.ekle(sd, f"t-{i:02d}", f"oturum-{i:02d}", f"dal-{i:02d}")


def test_20_eszamanli_ekleme_kayipsiz(tmp_path):
    sd = _sd(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    surecler = [ctx.Process(target=_ekle_isci, args=(sd, i)) for i in range(20)]
    for p in surecler:
        p.start()
    for p in surecler:
        p.join(120)
    assert all(p.exitcode == 0 for p in surecler)
    kayitlar = K.liste(sd)
    assert len(kayitlar) == 20
    assert sorted(k["teslim"] for k in kayitlar) == [f"t-{i:02d}" for i in range(20)]
    assert sorted(k["sira"] for k in kayitlar) == list(range(1, 21))  # sıra numarası tekrarsız, boşluksuz
    assert all(k["durum"] == "bekliyor" for k in kayitlar)
    with open(K.kuyruk_yolu(sd), encoding="utf-8") as f:
        assert sum(1 for s in f if s.strip()) == 20  # bozuk ya da yarım satır yok


def test_alanlar_ve_yesil_teslim_birlesti(tmp_path):
    sd = _sd(tmp_path)
    k = K.ekle(sd, "t1", "oturum-a", "dal-a", "gecti")
    assert {k[a] for a in ("teslim", "oturum", "dal", "test", "durum")} == {"t1", "oturum-a", "dal-a", "gecti", "bekliyor"}
    assert k["sira"] == 1 and k["onunde"] == 0
    K.gecis(sd, "t1", "kosuyor")
    K.gecis(sd, "t1", "birlesti")
    assert K.liste(sd)[0]["durum"] == "birlesti"
    with pytest.raises(K.KuyrukHatasi):
        K.gecis(sd, "t1", "kosuyor")  # birleşti son durumdur
    with pytest.raises(K.KuyrukHatasi):
        K.ekle(sd, "t1", "oturum-a", "dal-a")  # birleşmiş teslim yeniden eklenmez


def test_karantina_yeniden_teslimde_bekliyor(tmp_path):
    sd = _sd(tmp_path)
    K.ekle(sd, "t1", "o", "dal-a")
    K.ekle(sd, "t2", "o", "dal-b")
    with pytest.raises(K.KuyrukHatasi):
        K.gecis(sd, "t1", "karantina")  # bekliyor -> karantina yok
    K.gecis(sd, "t1", "kosuyor")
    K.gecis(sd, "t1", "karantina", neden="suçlu")
    with pytest.raises(K.KuyrukHatasi):
        K.gecis(sd, "t1", "bekliyor")  # karantinadan çıkış yalnız yeniden teslimle
    k = K.ekle(sd, "t1", "o", "dal-a")
    assert k["durum"] == "bekliyor" and k["onceki"] == "karantina" and k["sira"] == 3  # kuyruğun sonuna
    assert [x["teslim"] for x in K.liste(sd, "bekliyor")] == ["t2", "t1"]


def test_bekleyen_ve_kosan_cift_eklenmez_kalan_test_reddedilir(tmp_path):
    sd = _sd(tmp_path)
    K.ekle(sd, "t1", "o", "dal-a")
    with pytest.raises(K.KuyrukHatasi):
        K.ekle(sd, "t1", "o", "dal-a")
    with pytest.raises(K.KuyrukHatasi):
        K.ekle(sd, "t2", "o", "dal-b", "kaldi")
    with pytest.raises(K.KuyrukHatasi):
        K.gecis(sd, "yok", "kosuyor")
    assert len(K.liste(sd)) == 1


def test_ikinci_tek_kosucu_kilidi_reddedilir(tmp_path):
    sd = _sd(tmp_path)
    assert K.kosucu_al(sd, "kosucu-a")
    assert not K.kosucu_al(sd, "kosucu-b")
    assert K.kosucu_tazele(sd, "kosucu-a") and not K.kosucu_tazele(sd, "kosucu-b")
    assert not K.kosucu_birak(sd, "kosucu-b")  # başkasının kilidi bırakılmaz
    assert K.kosucu_birak(sd, "kosucu-a")
    assert K.kosucu_al(sd, "kosucu-b")


def test_bayat_kilit_30_sn_sonra_devralinir(tmp_path):
    sd = _sd(tmp_path)
    t0 = time.time()
    assert K.BAYAT_S == 30.0
    assert K.kosucu_al(sd, "olu-kosucu", simdi=t0)
    assert not K.kosucu_al(sd, "yeni", simdi=t0 + 29)  # 29 sn: hâlâ canlı
    assert K.kosucu_al(sd, "yeni", simdi=t0 + 30)       # 30 sn: bayat, devralınır
    with open(K.kosucu_yolu(sd), encoding="utf-8") as f:
        k = json.load(f)
    assert k["sahip"] == "yeni" and k["devralinan"] == "olu-kosucu"


def _kos(args, proje):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=proje, CLAUDE_CODE_SESSION_ID="oturum-cli-1", PYTHONUTF8="1")
    return ic_kos.kos([CLI] + args, cwd=proje, env=env)


def test_cli_kuyruk_ekle_sira_yazar_ve_liste(tmp_path):
    sd = _sd(tmp_path)
    proje = os.path.dirname(os.path.dirname(sd))
    r = _kos(["teslim", "kuyruk", "ekle", "--dal", "dal-a", "--teslim", "t1"], proje)
    assert r.returncode == 0, r.stderr
    assert "sıra 1" in r.stdout and "önünde 0" in r.stdout
    r = _kos(["teslim", "kuyruk", "ekle", "--dal", "dal-b"], proje)
    assert r.returncode == 0, r.stderr
    assert "sıra 2" in r.stdout and "önünde 1" in r.stdout
    r = _kos(["teslim", "kuyruk", "ekle", "--dal", "dal-b"], proje)
    assert r.returncode == 2 and "zaten kuyrukta" in r.stderr
    r = _kos(["teslim", "kuyruk", "liste", "--json"], proje)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert [(k["sira"], k["teslim"], k["oturum"]) for k in d["teslimler"]] == [
        (1, "t1", "oturum-cli-1"), (2, "dal-b", "oturum-cli-1")]
    assert d["kosucu"] == {}
    assert os.path.exists(K.kuyruk_yolu(sd))  # geçici proje dizinine yazıldı
