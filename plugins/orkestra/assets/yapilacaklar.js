'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { esc } = O;
  let KK;

  const kYol = () => '/api/kullanici-todo?alan=' + encodeURIComponent(O.alan);

  function kCiz(v) {
    if (!v.acik) {
      $('#kListe').innerHTML = '<li class="bos">' + esc(v.hata || 'Bu çalışma alanında orkestra açık değil.') + '</li>';
      $('#kSayi').textContent = '';
      $('#kYeni').disabled = true;
      return;
    }
    $('#kYeni').disabled = false;
    const m = v.maddeler || [];
    $('#kSayi').textContent = m.length + ' madde';
    $('#kListe').innerHTML = m.length ? m.map(x =>
      `<li><button type="button" data-id="${esc(x.id)}" aria-label="Sil: ${esc(x.metin)}">Sil</button><span>${esc(x.metin)}</span></li>`).join('')
      : '<li class="bos">Madde yok.</li>';
  }

  async function kYaz(govde) {
    try {
      await O.gonder(kYol(), govde);
      kCiz(await fetch(kYol()).then(r => r.json()));
      return true;
    } catch (e) { O.bildirim(O.hataMetni(e)); return false; }
  }

  $('#kYeni').addEventListener('keydown', async e => {
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    const metin = e.target.value.trim();
    if (!metin) return;
    e.target.disabled = true;
    const ok = await kYaz({ eylem: 'ekle', metin });
    e.target.disabled = false;
    if (ok) { e.target.value = ''; boyutla(); }
    e.target.focus();
  });
  // Kutu yazılan metne göre uzar (en çok 50vh; CSS sınırı)
  function boyutla() { const t = $('#kYeni'); t.style.height = 'auto'; t.style.height = t.scrollHeight + 2 + 'px'; }
  $('#kYeni').addEventListener('input', boyutla);
  $('#kListe').addEventListener('click', async e => {
    const b = e.target.closest('button[data-id]');
    if (!b) return;
    b.disabled = true;
    if (!await kYaz({ eylem: 'sil', id: b.dataset.id })) b.disabled = false;
  });
  O.kabuk({ sayfa: 'yapilacaklar' });
  KK = O.veri(kYol, { ad: 'kullanici-todo', aralik: 5000, cizici: kCiz });
})();
