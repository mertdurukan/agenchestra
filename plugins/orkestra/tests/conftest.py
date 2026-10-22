"""Testler gerçek eklenti kural deposunu görmesin: eklenti katmanı varsayılan olarak boş bir geçici dosyaya bakar.
Eklenti katmanını sınayan testler ORKESTRA_EKLENTI_KURALLARI'nı kendi geçici dosyasına çevirir."""
import os
import tempfile

# Testler gerçek ~/.claude/orkestra-makine/makine.json dosyasını okumasın ya da yazmasın (I-026 cfg).
# SessionStart hızlı yolu test koşusunda arka plan doktoru başlatmasın (süreç sızıntısı + gerçek makine config'i).
os.environ.setdefault("ORKESTRA_DOKTOR_OTOMATIK", "0")
# SessionStart'ta panel görevi otomatik kurulmasın (gerçek Task Scheduler kaydı; ADR-0034). panel_servis testleri kendisi açar.
os.environ.setdefault("ORKESTRA_PANEL_SERVIS", "0")
os.environ.setdefault("ORKESTRA_HOME", os.path.join(tempfile.gettempdir(), "orkestra_test_ev"))
os.environ.setdefault("ORKESTRA_EKLENTI_KURALLARI",
                      os.path.join(tempfile.gettempdir(), "orkestra_test_eklenti_yok", "kurallar", "eklenti_kurallari.json"))
# İş sırası kapısı (P-005): eski testler plan.md/todo.md'nin `is ac` ile hemen açılmasını bekler; sıra testleri '1' yapar.
os.environ.setdefault("ORKESTRA_SIRA_KAPISI", "0")
os.environ.setdefault("ORKESTRA_IZIN", "0")  # izin politikası (geniş allow): eski hook testleri kapı kararını sınar; izin testleri modu kendisi seçer
os.environ.setdefault("ORKESTRA_OZET_KAPISI", "0")  # kapanış özet kapısı (P-009): eski testler özetsiz kapatır
os.environ.setdefault("ORKESTRA_ADR_KAPISI", "0")  # kapanış ADR kapısı (P-015): eski testler ADR satırsız kapatır; ADR testleri '1' yapar
os.environ.setdefault("ORKESTRA_SOZLESME_KAPISI", "0")  # görev sözleşmesi (ADR-0035): eski testler sözleşmesiz iş açar; sözleşme testleri '1' yapar
os.environ.setdefault("ORKESTRA_TESLIM_KAPISI", "0")  # teslim kapısı (ADR-0035): testler gerçek gh/PR aramasın; test_teslim.py "1" yapar
os.environ.setdefault("ORKESTRA_IZOLE_UYARI", "0")  # izole ortam uyarısı (ADR-0035): on_kontrol testleri uyarısız koşar
