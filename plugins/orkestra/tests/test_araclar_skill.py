"""Panel /araclar skill arka ucu (ADR-0098): liste, aç/kapat, atomik yazma, bozuk JSON'a dokunmama."""
import json
import os
import sys

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import araclar_skill as S  # noqa: E402


def skill(dizin, klasor, ad=None, aciklama="bir skill"):
    d = dizin / klasor
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {ad or klasor}\ndescription: {aciklama}\n---\nGövde\n", encoding="utf-8")


@pytest.fixture
def ortam(tmp_path):
    ek, ku, pr = tmp_path / "ek", tmp_path / "ku", tmp_path / "proje"
    skill(ek, "textual"); skill(ek, "is")
    skill(ku, "synced")
    skill(pr / ".claude" / "skills", "yerel")
    return dict(proje=str(pr), kullanici_dizin=str(ku), eklenti_dizin=str(ek)), pr


def yerel(pr):
    return json.loads((pr / ".claude" / "settings.local.json").read_text(encoding="utf-8"))


def test_liste_uc_kaynak_ve_sayi(ortam):
    kw, _ = ortam
    s = S.liste(**kw)
    assert [(x["ad"], x["kaynak"]) for x in s] == [("orkestra:is", "eklenti"), ("orkestra:textual", "eklenti"),
                                                  ("synced", "kullanici"), ("yerel", "proje")]
    assert all(x["durum"] == "acik" for x in s)
    assert {x["mekanizma"] for x in s} == {"deny", "skillOverrides"}


def test_sayi_klasor_sayisina_esit():
    s = S.liste(proje=os.path.join(KOK, "yok-proje"), kullanici_dizin=os.path.join(KOK, "yok-ku"))
    klasor = [k for k in os.listdir(os.path.join(KOK, "skills")) if os.path.isfile(os.path.join(KOK, "skills", k, "SKILL.md"))]
    assert len(s) == len(klasor) and all(x["ad"].startswith("orkestra:") for x in s)


def test_eklenti_skill_deny_kurali(ortam):
    kw, pr = ortam
    r = S.degistir("orkestra:textual", "kapali", **kw)
    assert r["tamam"] and yerel(pr)["permissions"]["deny"] == ["Skill(orkestra:textual)"]
    assert "skillOverrides" not in yerel(pr)


def test_kullanici_skill_off(ortam):
    kw, pr = ortam
    S.degistir("synced", "kapali", **kw)
    assert yerel(pr)["skillOverrides"] == {"synced": "off"}


def test_gidis_donus_dosyayi_baslangica_esitler(ortam):
    kw, pr = ortam
    yol = pr / ".claude" / "settings.local.json"
    yol.parent.mkdir(parents=True, exist_ok=True)
    ilk = {"permissions": {"allow": ["Bash(ls)"]}, "baska": 1}
    yol.write_text(json.dumps(ilk), encoding="utf-8")
    for ad in ("orkestra:is", "yerel"):
        S.degistir(ad, "kapali", **kw)
        S.degistir(ad, "acik", **kw)
    assert yerel(pr) == ilk


def test_yabanci_ayarlar_korunur(ortam):
    kw, pr = ortam
    yol = pr / ".claude" / "settings.local.json"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps({"permissions": {"deny": ["Bash(rm*)"]}, "env": {"A": "1"}}), encoding="utf-8")
    S.degistir("orkestra:is", "kapali", **kw)
    d = yerel(pr)
    assert d["permissions"]["deny"] == ["Bash(rm*)", "Skill(orkestra:is)"] and d["env"] == {"A": "1"}


def test_gecersiz_ad_durum_ve_yol_ayraci_reddedilir(ortam):
    kw, pr = ortam
    for ad in ("yok", "../x", "orkestra:../is", "", None, ["yerel"]):
        with pytest.raises(S.SkillHata):
            S.degistir(ad, "kapali", **kw)
    with pytest.raises(S.SkillHata):
        S.degistir("yerel", "belki", **kw)
    assert not (pr / ".claude" / "settings.local.json").exists()


def test_bozuk_json_yazilmaz_dosya_korunur(ortam):
    kw, pr = ortam
    yol = pr / ".claude" / "settings.local.json"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text("{bozuk", encoding="utf-8")
    with pytest.raises(S.SkillHata):
        S.degistir("yerel", "kapali", **kw)
    assert yol.read_text(encoding="utf-8") == "{bozuk"
    with pytest.raises(S.SkillHata):
        S.liste(**kw)


def test_yedek_olusur_ve_gecici_dosya_kalmaz(ortam):
    kw, pr = ortam
    yol = pr / ".claude" / "settings.local.json"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text('{"a": 1}', encoding="utf-8")
    S.degistir("yerel", "kapali", **kw)
    assert json.loads((yol.parent / "settings.local.json.orkestra.bak").read_text(encoding="utf-8")) == {"a": 1}
    assert not (yol.parent / "settings.local.json.orkestra.tmp").exists()
