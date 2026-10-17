'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const { esc } = O;
  const { yerlestir } = O;

  // Durum: veri sunucudan gelir; taslaklar, açık düzenleme/kaldırma satırı, hata ve yoldaki istekler yeniden çizimde korunur.
  const S = { veri: null, duzen: null, kaldir: null, taslak: {}, yeni: { metin: '', neden: '', katman: 'proje' }, hata: {}, yolda: new Set(), acik: new Set() };
  let K = null;

  const dizi = ad => (S.veri && Array.isArray(S.veri[ad])) ? S.veri[ad] : [];
  const YENI = 'yeni';   // hata/yolda anahtarı: yeni kural formu

  // <details> açık/kapalı durumu yeniden çizimde korunur
  const yerlestirAcik = (kap, html) => yerlestir(kap, html, k => k.querySelectorAll('details[data-d]').forEach(d => { d.open = S.acik.has(d.dataset.d); }));
  const tarih = k => O.B.tarih(k.guncelleme || k.olusturma);
  const hataSatir = id => `<p class="hata-satir" role="status" aria-live="polite" data-hata="${esc(id)}">${esc(S.hata[id] || '')}</p>`;
  const kilit = id => (S.yolda.has(id) ? ' disabled' : '');

  // ------------------------------------------------------------ bölümler
  const KATMAN_AD = { plugin: 'Eklenti (her projede)', proje: 'Proje' };
  function kuralMeta(r) {
    const neden = r.neden ? `Neden: ${esc(r.neden)} · ` : '';
    const katman = `<span class="katman" data-katman="${esc(r.katman || 'proje')}">${esc(KATMAN_AD[r.katman || 'proje'])}</span>`;
    const kapali = r.devre_disi ? ' · <strong>bu projede kapalı</strong>' : '';
    return `<span class="meta">${katman}${kapali} · ${neden}<code>${esc(r.id)}</code> · ${esc(tarih(r))}</span>`;
  }
  function etkinSatir(r) {
    const id = r.id, t = S.taslak[id] || { metin: r.metin, neden: r.neden || '' };
    if (S.duzen === id) {
      return `<li class="kural-satir"><form class="kural-form" data-duzen-form="${esc(id)}">
        <label>Kural metni<textarea rows="3" data-alan="metin" data-id="${esc(id)}" data-anahtar="dm-${esc(id)}" required${kilit(id)}>${esc(t.metin)}</textarea></label>
        <label>Neden (isteğe bağlı)<input type="text" data-alan="neden" data-id="${esc(id)}" data-anahtar="dn-${esc(id)}" value="${esc(t.neden)}"${kilit(id)}></label>
        <div class="dugmeler"><button type="submit" class="onayla"${kilit(id)}>Kaydet</button>
          <button type="button" data-iptal="${esc(id)}"${kilit(id)}>Vazgeç</button></div>
        ${hataSatir(id)}</form></li>`;
    }
    if (S.kaldir === id) {
      const n = (S.taslak[id] && S.taslak[id].not) || '';
      return `<li class="kural-satir"><p class="kural-metin">${esc(r.metin)}</p>
        <form class="kural-form" data-kaldir-form="${esc(id)}">
          <label>Bu kural kaldırılsın mı? Kısa neden (isteğe bağlı)
            <input type="text" data-alan="not" data-id="${esc(id)}" data-anahtar="kn-${esc(id)}" value="${esc(n)}"${kilit(id)}></label>
          <div class="dugmeler"><button type="submit" class="reddet" data-anahtar="kk-${esc(id)}"${kilit(id)}>Kaldır</button>
            <button type="button" data-iptal="${esc(id)}"${kilit(id)}>Vazgeç</button></div>
          ${hataSatir(id)}</form></li>`;
    }
    return `<li class="kural-satir"><p class="kural-metin">${esc(r.metin)}</p>${kuralMeta(r)}
      <div class="dugmeler">
        <button type="button" data-duzenle="${esc(id)}" data-anahtar="d-${esc(id)}">Düzenle</button>
        <button type="button" data-kaldira="${esc(id)}" data-anahtar="k-${esc(id)}">Kaldır</button>
        <button type="button" data-tasi="${esc(id)}" data-hedef="${r.katman === 'plugin' ? 'proje' : 'plugin'}" data-anahtar="t-${esc(id)}"${kilit(id)}>${r.katman === 'plugin' ? 'Yalnız projeye al' : 'Eklentiye taşı (her projede geçsin)'}</button>
      </div>${hataSatir(id)}</li>`;
  }
  function oneriSatir(r) {
    const id = r.id, oid = r.onay_id;
    const ok = !!oid, k = oid || id;
    const t = S.taslak['o:' + id] || {};
    return `<li class="kural-satir"><p class="kural-metin">${esc(r.metin)}</p>${kuralMeta(r)}
      ${ok ? `<div class="onay-eylem"><label class="meta" for="on-${esc(id)}">Not (isteğe bağlı)</label>
      <input type="text" id="on-${esc(id)}" data-alan="not" data-id="o:${esc(id)}" data-anahtar="on-${esc(id)}" value="${esc(t.not || '')}"${kilit(k)}>
      <div class="dugmeler">
        <button type="button" class="onayla" data-karar="onay" data-oid="${esc(oid)}" data-kid="${esc(id)}" data-anahtar="oy-${esc(id)}"${kilit(k)}>Onayla</button>
        <button type="button" class="reddet" data-karar="ret" data-oid="${esc(oid)}" data-kid="${esc(id)}" data-anahtar="or-${esc(id)}"${kilit(k)}>Reddet</button>
      </div></div>` : '<p class="meta">Onay kaydı henüz oluşmadı; birkaç saniye sonra yenilenir.</p>'}
      ${hataSatir(k)}</li>`;
  }
  const DURUM_AD = { reddedildi: 'Reddedildi', kaldirildi: 'Kaldırıldı' };
  function gecmisSatir(r) {
    const son = (Array.isArray(r.gecmis) ? r.gecmis : []).filter(g => g.olay === 'kaldirildi' || g.olay === 'reddedildi').pop();
    const not = son && son.not ? ` · not: ${esc(son.not)}` : '';
    return `<li class="kural-satir sonuk"><p class="kural-metin">${esc(r.metin)}</p>
      <span class="meta">${esc(DURUM_AD[r.durum] || r.durum)} · ${esc(tarih(r))} · <code>${esc(r.id)}</code>${not}</span></li>`;
  }
  function yeniForm() {
    return `<form class="kural-form" data-yeni-form="1">
      <label>Kural metni (zorunlu)<textarea rows="3" data-alan="metin" data-id="${YENI}" data-anahtar="ym" required${kilit(YENI)}>${esc(S.yeni.metin)}</textarea></label>
      <label>Neden (isteğe bağlı)<input type="text" data-alan="neden" data-id="${YENI}" data-anahtar="yn" value="${esc(S.yeni.neden)}"${kilit(YENI)}></label>
      <label>Katman<select data-alan="katman" data-id="${YENI}" data-anahtar="yk"${kilit(YENI)}>
        <option value="proje"${S.yeni.katman === 'plugin' ? '' : ' selected'}>Proje: yalnız bu projede geçerli</option>
        <option value="plugin"${S.yeni.katman === 'plugin' ? ' selected' : ''}>Eklenti: orkestra eklentisinde saklanır, her projede geçerli</option></select></label>
      <div class="dugmeler"><button type="submit" class="onayla" data-anahtar="ye"${kilit(YENI)}>Kuralı ekle</button></div>
      ${hataSatir(YENI)}</form>`;
  }
  function liste(satirlar, bos) {
    return satirlar.length ? `<ul class="kural-liste">${satirlar.join('')}</ul>` : `<p class="bos">${bos}</p>`;
  }
  // ------------------------------------------------------------ kural dosyaları (düzenleyici)
  // Dosya metni taslağı yoklamayla ezilmez: liste yalnız açılışta, kayıtta ve alan değişince yüklenir.
  const D = { liste: null, hata: '', sec: null, dosya: null, taslak: '', yuk: false, kayit: false, mesaj: '', bilgi: '', filtre: '' };
  const kirli = () => !!(D.dosya && D.taslak !== D.dosya.metin);
  const boyutYaz = b => b < 1024 ? b + ' B' : (b / 1024).toFixed(1) + ' KB';
  function dosyaCiz() {
    const kap = $('#dosyaIcerik');
    if (D.hata && !D.liste) return yerlestirAcik(kap, `<p class="bos">Dosyalar alınamadı: ${esc(O.yolGizle(D.hata))}</p>`);
    if (!D.liste) return yerlestirAcik(kap, '<p class="bos">Yükleniyor…</p>');
    $('#kaynakSayi').textContent = String(D.liste.length);
    const f = D.filtre.trim().toLowerCase();
    const gruplar = {};
    D.liste.filter(x => !f || x.ad.toLowerCase().includes(f)).forEach(x => { (gruplar[x.grup_ad] = gruplar[x.grup_ad] || []).push(x); });
    const sol = `<nav class="dosya-liste" aria-label="Kural dosyaları">
      <input type="search" placeholder="Dosya ara" value="${esc(D.filtre)}" data-filtre="1" data-anahtar="df" aria-label="Dosya ara">
      ${Object.entries(gruplar).map(([g, l]) => `<h3>${esc(g)}</h3><ul>${l.map(x =>
        `<li><button type="button" data-dosya="${esc(x.id)}" title="${esc(x.ad)} · ${esc(boyutYaz(x.boyut))}"${D.sec === x.id ? ' aria-current="true"' : ''}>${esc(x.ad)}${x.yazilabilir ? '' : ' (salt okuma)'}</button></li>`).join('')}</ul>`).join('') || '<p class="bos">Eşleşen dosya yok.</p>'}
    </nav>`;
    let sag = '<div class="dosya-editor"><p class="bos">Soldan bir dosya seç.</p></div>';
    if (D.sec) {
      if (D.yuk) sag = '<div class="dosya-editor"><p class="bos">Açılıyor…</p></div>';
      else if (!D.dosya) sag = `<div class="dosya-editor"><p class="hata-satir" role="status">${esc(D.mesaj)}</p></div>`;
      else {
        const meta = D.liste.find(x => x.id === D.sec) || {};
        const yaz = meta.yazilabilir !== false;
        sag = `<div class="dosya-editor"><form data-dosya-form="1">
          <div class="ust"><strong>${esc(D.dosya.ad)}</strong>
            <span class="meta" title="${esc(D.dosya.yol)}">${esc(meta.grup_ad || '')}${kirli() ? ' · kaydedilmemiş değişiklik' : ''}</span></div>
          <textarea data-metin="1" data-anahtar="dt" spellcheck="false" aria-label="${esc(D.dosya.ad)} içeriği"${yaz ? '' : ' readonly'}>${esc(D.taslak)}</textarea>
          <div class="dugmeler">${yaz ? `<button type="submit" class="onayla" data-anahtar="dk"${D.kayit || !kirli() ? ' disabled' : ''}>Kaydet</button>
            <button type="button" data-geri="1"${D.kayit || !kirli() ? ' disabled' : ''}>Değişikliği at</button>` : ''}
            <button type="button" data-yenile="1"${D.kayit ? ' disabled' : ''}>Diskten yeniden oku</button></div>
          <p class="${D.mesaj ? 'hata-satir' : 'meta'}" role="status" aria-live="polite">${esc(D.mesaj || D.bilgi)}</p></form></div>`;
      }
    }
    yerlestirAcik(kap, sol + sag);
  }
  async function jsonGet(url) {
    const r = await fetch(url, { cache: 'no-store' });
    let v = null; try { v = await r.json(); } catch (e) { /* JSON değil */ }
    if (!r.ok || !v || v.tamam === false || v.acik === false) throw new Error((v && v.hata) || ('HTTP ' + r.status));
    return v;
  }
  async function dosyaListeYukle() {
    if (O.tumAlan()) return;   // 'Tüm çalışma alanları': sayfa gizli, tek alan isteyen çağrı yapılmaz
    try { D.liste = (await jsonGet('/api/kural-dosyalar?alan=' + encodeURIComponent(O.alan))).dosyalar; D.hata = ''; }
    catch (e) { D.hata = e.message || String(e); }
    dosyaCiz();
  }
  async function dosyaAc(id, zorla) {
    if (!zorla && kirli() && !confirm('Kaydedilmemiş değişiklikler atılsın mı?')) return;
    D.sec = id; D.yuk = true; D.dosya = null; D.mesaj = ''; D.bilgi = ''; dosyaCiz();
    try { D.dosya = await jsonGet('/api/kural-dosya?alan=' + encodeURIComponent(O.alan) + '&id=' + encodeURIComponent(id)); D.taslak = D.dosya.metin; }
    catch (e) { D.mesaj = 'Açılamadı: ' + O.yolGizle(e.message || String(e)); }
    D.yuk = false; dosyaCiz();
  }
  async function dosyaKaydet() {
    if (!kirli() || D.kayit) return;
    D.kayit = true; D.mesaj = ''; dosyaCiz();
    try {
      const v = await O.gonder('/api/kural-dosya?alan=' + encodeURIComponent(O.alan), { id: D.dosya.id, metin: D.taslak, taban: D.dosya.taban });
      D.dosya = { ...D.dosya, metin: D.taslak, taban: v.kayit.taban };
      D.bilgi = 'Kaydedildi.';
      O.bildirim('Dosya kaydedildi.');
      dosyaListeYukle();
    } catch (e) { D.mesaj = 'Kaydedilemedi: ' + O.yolGizle(e && e.message ? e.message : String(e)); }
    D.kayit = false; dosyaCiz();
  }
  window.addEventListener('beforeunload', e => { if (kirli()) { e.preventDefault(); e.returnValue = ''; } });

  function sayfaCiz() {
    if (!S.veri) {
      let m = '<p class="bos">Yükleniyor…</p>';
      if (K && K.durum === 'hata') m = `<p class="bos">Kurallar alınamadı: ${esc(O.yolGizle(K.hata))}</p>`;
      for (const k of ['etkin', 'oneri', 'gecmis']) yerlestirAcik($('#' + k + 'Icerik'), m);
      for (const k of ['etkin', 'oneri', 'gecmis']) $('#' + k + 'Sayi').textContent = '';
      yerlestirAcik($('#yeniIcerik'), K && K.durum === 'hata' ? '' : yeniForm());
      return;
    }
    const et = dizi('etkin'), on = dizi('oneriler'), ge = dizi('gecmis');
    $('#etkinSayi').textContent = et.length ? String(et.length) : '';
    $('#oneriSayi').textContent = on.length ? on.length + ' bekliyor' : '';
    $('#gecmisSayi').textContent = ge.length ? String(ge.length) : '';
    yerlestirAcik($('#etkinIcerik'), liste(et.map(etkinSatir), 'Etkin kural yok. Aşağıdan ekleyebilirsin.'));
    yerlestirAcik($('#oneriIcerik'), liste(on.map(oneriSatir), 'Önerilen kural yok.'));
    yerlestirAcik($('#yeniIcerik'), yeniForm());
    yerlestirAcik($('#gecmisIcerik'), ge.length
      ? `<details class="nasil" data-d="gecmis"><summary>Kaldırılan ve reddedilen kurallar (${ge.length})</summary>${liste(ge.map(gecmisSatir), '')}</details>`
      : '<p class="bos">Geçmişte kural yok.</p>');
  }

  // ------------------------------------------------------------ gönderme
  const ana = $('main');
  function hataYaz(id, metin) {
    S.hata[id] = metin || '';
    ana.querySelectorAll(`[data-hata="${CSS.escape(id)}"]`).forEach(el => { el.textContent = S.hata[id]; });
    ['etkinIcerik', 'oneriIcerik', 'yeniIcerik'].forEach(k => { $('#' + k).__html = null; });   // DOM değişti; sonraki çizim yeniden kursun
  }
  function kilitle(id, acik) {
    const kapsa = id === YENI ? ana.querySelector('[data-yeni-form]')
      : ana.querySelector(`[data-duzen-form="${CSS.escape(id)}"], [data-kaldir-form="${CSS.escape(id)}"]`)
        || (ana.querySelector(`[data-oid="${CSS.escape(id)}"]`) || {}).parentNode?.parentNode;   // öneri satırı (li)
    if (kapsa) kapsa.querySelectorAll('button, input, textarea').forEach(el => { el.disabled = acik; });
    ['etkinIcerik', 'oneriIcerik', 'yeniIcerik'].forEach(k => { $('#' + k).__html = null; });
  }
  // Ortak gönderici: id yoldaki anahtarı, govde sunucuya giden gövdeyi, bitti başarı sonrası temizliği yapar.
  async function gonder(id, govde, bildirim, bitti) {
    if (S.yolda.has(id)) return;
    S.yolda.add(id); hataYaz(id, ''); kilitle(id, true);
    try {
      await O.gonder('/onay?alan=' + encodeURIComponent(O.alan), govde);
      S.yolda.delete(id); delete S.hata[id];
      if (bitti) bitti();
      O.bildirim(bildirim);
      if (K) await K.zorla();
      sayfaCiz();
    } catch (e) {
      S.yolda.delete(id); kilitle(id, false);
      hataYaz(id, 'Kaydedilemedi: ' + O.yolGizle(e && e.message ? e.message : String(e)));
    }
  }

  ana.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.dosya) return dosyaAc(b.dataset.dosya);
    if (b.dataset.geri) { D.taslak = D.dosya.metin; D.mesaj = ''; return dosyaCiz(); }
    if (b.dataset.yenile) { if (kirli() && !confirm('Kaydedilmemiş değişiklikler atılsın mı?')) return; return dosyaAc(D.sec, true); }
    if (b.dataset.duzenle) { const r = dizi('etkin').find(x => x.id === b.dataset.duzenle); S.duzen = b.dataset.duzenle; S.kaldir = null; S.taslak[S.duzen] = { metin: r ? r.metin : '', neden: r ? r.neden || '' : '' }; return sayfaCiz(); }
    if (b.dataset.tasi) {
      const id = b.dataset.tasi, hedef = b.dataset.hedef;
      if (!confirm(hedef === 'plugin' ? id + ' orkestra eklentisine taşınsın mı? Eklentiyi kullanan her projede geçerli olur.' : id + ' yalnız bu projeye alınsın mı? Eklenti deposundan çıkar.')) return;
      return gonder(id, { islem: 'kural-tasi', id, katman: hedef }, 'Kural taşındı.');
    }
    if (b.dataset.kaldira) { S.kaldir = b.dataset.kaldira; S.duzen = null; S.taslak[S.kaldir] = { not: '' }; return sayfaCiz(); }
    if (b.dataset.iptal) { const id = b.dataset.iptal; S.duzen = S.kaldir = null; delete S.taslak[id]; delete S.hata[id]; return sayfaCiz(); }
    if (b.dataset.karar) {
      const oid = b.dataset.oid, kid = b.dataset.kid, t = S.taslak['o:' + kid] || {};
      return gonder(oid, { islem: 'karar', id: oid, sonuc: b.dataset.karar, secim: null, not: (t.not || '').trim() },
        b.dataset.karar === 'onay' ? 'Kural etkinleştirildi.' : 'Kural reddedildi.', () => { delete S.taslak['o:' + kid]; });
    }
  });
  ana.addEventListener('input', e => {
    const el = e.target, a = el.dataset && el.dataset.alan;
    if (el.dataset && el.dataset.filtre) { D.filtre = el.value; return dosyaCiz(); }
    if (el.dataset && el.dataset.metin) {
      const once = kirli(); D.taslak = el.value; D.bilgi = '';
      if (once !== kirli()) dosyaCiz();   // yalnız kirli durumu değişince yeniden çiz (imleç korunur)
      return;
    }
    if (!a) return;
    if (el.dataset.id === YENI) S.yeni[a] = el.value;
    else (S.taslak[el.dataset.id] = S.taslak[el.dataset.id] || {})[a] = el.value;
  });
  ana.addEventListener('submit', e => {
    e.preventDefault();
    const f = e.target;
    if (f.dataset.dosyaForm) return dosyaKaydet();
    if (f.dataset.yeniForm) {
      const metin = S.yeni.metin.trim();
      if (!metin) return hataYaz(YENI, 'Kural metni boş olamaz.');
      return gonder(YENI, { islem: 'kural-ekle', metin, neden: S.yeni.neden.trim(), katman: S.yeni.katman }, 'Kural eklendi.', () => { S.yeni = { metin: '', neden: '', katman: S.yeni.katman }; });
    }
    if (f.dataset.duzenForm) {
      const id = f.dataset.duzenForm, t = S.taslak[id] || {};
      const metin = (t.metin || '').trim();
      if (!metin) return hataYaz(id, 'Kural metni boş olamaz.');
      return gonder(id, { islem: 'kural-duzenle', id, metin, neden: (t.neden || '').trim() }, 'Kural güncellendi.', () => { S.duzen = null; delete S.taslak[id]; });
    }
    if (f.dataset.kaldirForm) {
      const id = f.dataset.kaldirForm, t = S.taslak[id] || {};
      return gonder(id, { islem: 'kural-kaldir', id, not: (t.not || '').trim() }, 'Kural kaldırıldı.', () => { S.kaldir = null; delete S.taslak[id]; });
    }
  });
  ana.addEventListener('toggle', e => {
    const d = e.target;
    if (d.dataset && d.dataset.d) { d.open ? S.acik.add(d.dataset.d) : S.acik.delete(d.dataset.d); }
  }, true);

  // ------------------------------------------------------------ veri
  if (!O.sayfa) O.kabuk({ sayfa: 'kurallar' });   // Onaylar sayfasında kabuğu onaylar.js kurar
  K = O.veri(() => '/kurallar.json?alan=' + encodeURIComponent(O.alan), {
    ad: 'Kurallar', aralik: 4000,
    gecerli: v => Array.isArray(v.etkin) && (!v.alan || !v.alan.id || v.alan.id === O.alan),
    cizici: v => { S.veri = v; sayfaCiz(); },
    durum: () => { yerlestirAcik($('#kBayat'), O.bayatIsaret(K)); if (!S.veri) sayfaCiz(); },
  });
  dosyaListeYukle();
  window.addEventListener('orkestra:alan', () => { D.liste = D.dosya = D.sec = null; D.taslak = ''; D.mesaj = D.bilgi = ''; dosyaListeYukle(); S.veri = null; S.duzen = S.kaldir = null; S.taslak = {}; S.hata = {}; S.acik.clear(); sayfaCiz(); });
  sayfaCiz();
})();
