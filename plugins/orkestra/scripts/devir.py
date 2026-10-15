"""Şablonlu devir özeti: is.json + plan.md + todo.md + oturumlar.md + son değişen dosyalardan; model çağrısı yok.

Saf Python, yalnız standart kütüphane. `devir_metni` yan etkisizdir; yazmayı çağıran yapar.
"""
import os

_ATLA = {"is.json", "todo.md", "oturumlar.md", "plan.md", "devir.md"}


def _ilk_satirlar(yol, n=3):
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            return [s.strip() for s in f if s.strip() and not s.startswith("#")][:n]
    except OSError:
        return []


def _son_satir(yol):
    try:
        with open(yol, encoding="utf-8", errors="replace") as f:
            dolu = [s.strip() for s in f if s.strip()]
        return dolu[-1] if len(dolu) > 1 else ""
    except OSError:
        return ""


def _son_degisenler(klasor, n=5):
    dosyalar = []
    try:
        for ad in os.listdir(klasor):
            yol = os.path.join(klasor, ad)
            if os.path.isfile(yol) and ad not in _ATLA and not ad.endswith(".lock"):
                dosyalar.append((os.path.getmtime(yol), ad))
    except OSError:
        return []
    return [ad for _, ad in sorted(dosyalar, reverse=True)[:n]]


def devir_metni(kayit, todo):
    """kayit: is.json sözlüğü; todo: is_kaydi.todo_ozet çıktısı. Sabit, kısa Markdown döner."""
    klasor = kayit.get("klasor") or ""
    hedef = _ilk_satirlar(os.path.join(klasor, "plan.md")) or [kayit.get("baslik") or ""]
    sat = [f"# Devir — {kayit.get('id')} {kayit.get('baslik') or ''}", "",
           f"- Hedef: {' '.join(hedef)}",
           f"- Klasör: {klasor}",
           f"- Todo: {todo['biten']}/{todo['toplam']}; açık maddeler:"]
    sat += [f"  - [ ] {m}" for m in todo["acik_maddeler"]] or ["  - (yok)"]
    sat.append(f"- Son oturum notu: {_son_satir(os.path.join(klasor, 'oturumlar.md')) or '(yok)'}")
    sat.append(f"- Son değişen dosyalar: {', '.join(_son_degisenler(klasor)) or '(yok)'}")
    sat.append("- Bitti tanımı: todo.md'deki tüm maddeler [x]; ayrıntı plan.md'de.")
    return "\n".join(sat) + "\n"
