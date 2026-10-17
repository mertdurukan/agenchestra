'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { esc } = O;
  const SINIR = 2000;
  let KK, maddeler = [], ara = '', geri = null, geriZ = 0;

  const kYol = () => '/api/kullanici-todo?alan=' + encodeURIComponent(O.alan);

  function goreli(z) {
    const t = Date.parse(String(z || '').replace(' ', 'T'));
    if (!t) return '';
    const dk = Math.max(0, Math.round((Date.now() - t) / 60000));
    if (dk < 1) return 'şimdi';
    if (dk < 60) return dk + ' dk önce';
    if (dk < 1440) return Math.round(dk / 60) + ' sa önce';
    return Math.round(dk / 1440) + ' gün önce';
  }

  function listeCiz() {
    $('#kAra').hidden = maddeler.length < 8;
    const q = ara.trim().toLowerCase();
    const g = q ? maddeler.filter(x => x.metin.toLowerCase().includes(q)) : maddeler;
    $('#kSayi').textContent = maddeler.length + ' madde';
    ozetCiz();
    $('#kListe').innerHTML = g.length ? g.map(x =>
      `<li><div class="yap-dugme"><button type="button" data-kopya="${esc(x.id)}" aria-label="Kopyala: ${esc(x.metin)}">Kopyala</button>` +
      `<button type="button" data-id="${esc(x.id)}" aria-label="Tamamla: ${esc(x.metin)}">Tamamla</button></div>` +
      `<div class="yap-metin"><span>${esc(x.metin)}</span><small title="${esc(x.zaman || '')}">${esc(goreli(x.zaman))}</small></div></li>`).join('')
      : `<li class="bos">${q ? 'Aramaya uyan madde yok.' : 'Henüz madde yok. Yukarıya yaz, Enter ile ekle.'}</li>`;
  }

  function kCiz(v) {
    if (!v.acik) {
      maddeler = [];
      $('#kListe').innerHTML = '<li class="bos">' + esc(v.hata || 'Bu çalışma alanında orkestra açık değil.') + '</li>';
      $('#kSayi').textContent = '';
      $('#kYeni').disabled = true; $('#kEkle').disabled = true;
      return;
    }
    if (v.alan && v.alan.ad) $('#kAlan').textContent = v.alan.ad + ' · yalnız sen düzenlersin: yaz, Enter ile ekle, işin bitince tamamla.';
    $('#kYeni').disabled = false; $('#kEkle').disabled = false;
    maddeler = v.maddeler || [];
    listeCiz();
  }

  async function kYaz(govde) {
    try {
      await O.gonder(kYol(), govde);
      kCiz(await fetch(kYol()).then(r => r.json()));
      return true;
    } catch (e) { O.bildirim(O.hataMetni(e)); return false; }
  }

  function geriGoster(metin) {
    geri = metin; clearTimeout(geriZ);
    $('#kGeriMetin').textContent = 'Tamamlandı: ' + (metin.length > 60 ? metin.slice(0, 60) + '…' : metin);
    $('#kGeri').hidden = false;
    geriZ = setTimeout(() => { $('#kGeri').hidden = true; geri = null; }, 10000);
  }

  async function ekle() {
    const t = $('#kYeni'), metin = t.value.trim();
    if (!metin) return;
    t.disabled = true; $('#kEkle').disabled = true;
    const ok = await kYaz({ eylem: 'ekle', metin });
    t.disabled = false; $('#kEkle').disabled = false;
    if (ok) { t.value = ''; boyutla(); }
    t.focus();
  }

  // Kutu yazılan metne göre uzar (en çok 50vh; CSS sınırı); sayaç güncellenir
  function boyutla() {
    const t = $('#kYeni');
    t.style.height = 'auto'; t.style.height = t.scrollHeight + 2 + 'px';
    $('#kSayac').textContent = t.value.length + ' / ' + SINIR;
  }
  $('#kYeni').addEventListener('input', boyutla);
  $('#kYeni').addEventListener('keydown', e => {
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    e.preventDefault(); ekle();
  });
  $('#kEkle').addEventListener('click', ekle);
  $('#kAra').addEventListener('input', e => { ara = e.target.value; listeCiz(); });

  async function kopyala(metin) {
    try { await navigator.clipboard.writeText(metin); return true; } catch (_) { /* yerel http: eski yola düş */ }
    const t = document.createElement('textarea');
    t.value = metin; t.style.position = 'fixed'; t.style.opacity = '0';
    document.body.appendChild(t); t.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (_) { /* ok=false */ }
    t.remove();
    return ok;
  }

  $('#kListe').addEventListener('click', async e => {
    const c = e.target.closest('button[data-kopya]');
    if (c) {
      const x = maddeler.find(m => m.id === c.dataset.kopya);
      const ok = await kopyala(x ? x.metin : '');
      const ilk = c.textContent;
      c.textContent = ok ? 'Kopyalandı' : 'Kopyalanamadı';
      setTimeout(() => { c.textContent = ilk; }, 1500);
      return;
    }
    const b = e.target.closest('button[data-id]');
    if (!b) return;
    const x = maddeler.find(m => m.id === b.dataset.id);
    const li = b.closest('li'); li.classList.add('bitti', 'bekler'); b.disabled = true;
    if (await kYaz({ eylem: 'sil', id: b.dataset.id })) { if (x) geriGoster(x.metin); }
    else { li.classList.remove('bitti', 'bekler'); b.disabled = false; }
  });
  $('#kGeriAl').addEventListener('click', async () => {
    if (!geri) return;
    const metin = geri; geri = null; $('#kGeri').hidden = true; clearTimeout(geriZ);
    await kYaz({ eylem: 'ekle', metin });
  });

  window.addEventListener('orkestra:alan', () => { maddeler = []; ara = ''; $('#kAra').value = ''; $('#kGeri').hidden = true; geri = null; });
  function ozetCiz() {
    $('#yOzet').innerHTML = G.karolar([
      G.karo({ etiket: 'Benim yapılacaklarım', deger: String(maddeler.length), alt: maddeler.length ? 'açık madde' : 'açık madde yok', vurgu: maddeler.length ? 'vurgu' : '' }),
    ]);
  }
  O.kabuk({ sayfa: 'yapilacaklar' });
  KK = O.veri(kYol, { ad: 'kullanici-todo', aralik: 5000, cizici: kCiz });
  boyutla();
})();
