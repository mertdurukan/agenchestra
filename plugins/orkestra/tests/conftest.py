"""Testler gerçek eklenti kural deposunu görmesin: eklenti katmanı varsayılan olarak boş bir geçici dosyaya bakar.
Eklenti katmanını sınayan testler ORKESTRA_EKLENTI_KURALLARI'nı kendi geçici dosyasına çevirir."""
import os
import sys
import tempfile

# Testler gerçek ~/.claude/orkestra-makine/makine.json dosyasını okumasın ya da yazmasın (I-026 cfg).
# SessionStart hızlı yolu test koşusunda arka plan doktoru başlatmasın (süreç sızıntısı + gerçek makine config'i).
os.environ.setdefault("ORKESTRA_DOKTOR_OTOMATIK", "0")
# SessionStart'ta panel görevi otomatik kurulmasın (gerçek Task Scheduler kaydı; ADR-0034). panel_servis testleri kendisi açar.
os.environ.setdefault("ORKESTRA_PANEL_SERVIS", "0")
# SessionStart bakım işleri testte ayrık süreç başlatmasın (ADR-0092); test_oturum_bakim.py kendisi açar.
os.environ.setdefault("ORKESTRA_OTURUM_BAKIM", "0")
os.environ.setdefault("ORKESTRA_HOME", os.path.join(tempfile.gettempdir(), "orkestra_test_ev"))
os.environ.setdefault("ORKESTRA_EKLENTI_KURALLARI",
                      os.path.join(tempfile.gettempdir(), "orkestra_test_eklenti_yok", "kurallar", "eklenti_kurallari.json"))
# İş sırası kapısı (P-005): eski testler plan.md/todo.md'nin `is ac` ile hemen açılmasını bekler; sıra testleri '1' yapar.
os.environ.setdefault("ORKESTRA_SIRA_KAPISI", "0")
os.environ.setdefault("ORKESTRA_KART_KONTROL", "0")  # kart `kontrol:` alanı (I-224 P8): eski kart fikstürleri taşımaz; test_kart_kontrol_alani '1' yapar
os.environ.setdefault("ORKESTRA_IZIN", "0")  # izin politikası (geniş allow): eski hook testleri kapı kararını sınar; izin testleri modu kendisi seçer
os.environ.setdefault("ORKESTRA_OZET_KAPISI", "0")  # kapanış özet kapısı (P-009): eski testler özetsiz kapatır
os.environ.setdefault("ORKESTRA_ADR_KAPISI", "0")  # kapanış ADR kapısı (P-015): eski testler ADR satırsız kapatır; ADR testleri '1' yapar
os.environ.setdefault("ORKESTRA_SOZLESME_KAPISI", "0")  # görev sözleşmesi (ADR-0035): eski testler sözleşmesiz iş açar; sözleşme testleri '1' yapar
os.environ.setdefault("ORKESTRA_TESLIM_KAPISI", "0")  # teslim kapısı (ADR-0035): testler gerçek gh/PR aramasın; test_teslim.py "1" yapar
os.environ.setdefault("ORKESTRA_IZOLE_UYARI", "0")  # izole ortam uyarısı (ADR-0035): on_kontrol testleri uyarısız koşar
os.environ.setdefault("ORKESTRA_SKILL_SUREKLI", "0")  # sürekli açık skill gövdesi (ADR-0113/0119) SessionStart not bütçesini ölçmez; test_skill_surekli.py kendisi açar


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _eklenti_varsayilan_modu_plan():
    """ADR-0115: eklentinin gerçek varsayılan modu (auto) eski testleri etkilemesin; testler `plan` varsayılanıyla koşar.
    Varsayılan modu sınayan testler `mod_yalitim.eklenti_varsayilani(...)` ile kendi değerini seçer (iç içe geçer)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from mod_yalitim import eklenti_varsayilani  # noqa: PLC0415
    with eklenti_varsayilani("plan"):
        yield
