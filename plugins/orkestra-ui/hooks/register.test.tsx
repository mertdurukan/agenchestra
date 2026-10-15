import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import type { HamOzet } from '../types'
import { donustur, eylemImzasi, usd } from './register'

const BU = 'oturum-bu'

// Veri yaşı gerçek saate göre sınanır: taze veri 1 dk, eski veri 30 dk önce üretilmiş.
const dkOnce = (dk: number) => new Date(Date.now() - dk * 60000).toISOString()
const HAM: HamOzet = {
  surum: 2, acik: true, uretim: dkOnce(1), proje: 'Ornek',
  kartlar: [
    { id: 'G-001', baslik: 'README satırı', durum: 'onaylandi', basamak: 'T1', isci: 1, denetim: 'onay', usd: 0.01, oturum: BU },
    { id: 'G-002', baslik: 'Kod taraması', durum: 'reddedildi', basamak: 'T2', isci: 1, denetim: 'ret', usd: 0.2, oturum: 'baska' },
    { id: 'G-003', baslik: 'Eski teslim', durum: 'teslim', basamak: 'T1', isci: 1, denetim: 'onay', usd: 0.05, oturum: 'baska', guncelleme: '2026-10-13T11:07:07+03:00' },
    { id: 'G-004', baslik: 'Yeni iş', durum: 'isleniyor', basamak: 'T2', isci: 1, denetim: '-', usd: 0.12, oturum: BU },
  ],
  sayac: { onaylandi: 1, reddedildi: 1 },
  maliyet: {
    bugun: 1.5, toplam: 20,
    surec: { is: 0.3 }, model: { 'sonnet-5-5': 0.3 },
    oturumlar: { [BU]: { usd: 0.42, surec: { is: 0.3, denetim: 0.12 }, model: { 'sonnet-5-5': 0.42 } } },
  },
  sohbetler: [
    { oturum: BU, baslik: 'Orkestrasyon', usd: 39.06, kaynak: 'defter', son: '2026-10-13T10:46+03:00' },
  ],
  defter: [
    { zaman: '2026-10-13T10:00:00+03:00', gorev: 'G-001', surec: 'is', ajan: 'orkestra:isci-t1', metin: '**README** satırı `eklendi`' },
    { zaman: '2026-10-13T10:05:00+03:00', gorev: 'G-001', surec: 'denetim', ajan: 'orkestra:denetci', metin: 'G-001 denetim', olay: true },
    // olay alanı yok (eski ozet.json): mod kısa durum işaretini kendisi sezer
    { zaman: '2026-10-13T10:06:00+03:00', gorev: 'G-002', surec: 'denetim', ajan: 'orkestra:denetci', metin: 'TESLİM' },
  ],
  isler: [
    { id: 'I-001', ad: 'Orkestra açık maddeler', biten: 3, toplam: 5, acik: ['Panel sadeleşsin', 'Test yaz'] },
    { id: 'I-002', ad: 'Langfuse erken uyarı', biten: 1, toplam: 2, acik: ['Alarm e-postası'] },
  ],
  perspektif: { zamani_geldi: false, rapor: true, calisiyor: false },
}

const SAAT = HAM.uretim.slice(11, 16)
const ESKI: HamOzet = { ...HAM, uretim: dkOnce(30) }
const ESKI_SAAT = ESKI.uretim.slice(11, 16)
// Yalnız teslim edilmiş kart, ret/teslim bekleyen yok, rapor yok: bant çizilmemeli, pane "Açık iş yok" demeli.
const SESSIZ: HamOzet = { ...HAM, kartlar: [HAM.kartlar![2]], sayac: {}, perspektif: { zamani_geldi: false, rapor: false, calisiyor: false } }

const PANE_PROPS = {
  title: 'Orkestra', isFocused: false, bodyColumns: 100, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 40 }, view: {},
}
const BANT_PROPS = { hasSurvey: false, isWorking: false, maxRows: 5, bodyColumns: 100, scroll: { offset: 0, bodyRows: 5 }, view: {} }

// Test ortamında dosya sistemi yok: ozet.json'u ve oturumu taklit et.
// `kaynak` değiştirilirse (ham + sürüm) ozet.json'un yeni bir sürümü gelmiş olur: farklı mtime/size.
type Kaynak = { ham: HamOzet | null; surum: number }
function sahte(on: On, ham: HamOzet | null, argv: string[][] = [], kaynak: Kaynak = { ham, surum: 0 }) {
  on('fs.stat', () => (kaynak.ham === null ? { deny: 'yok' } : { value: { kind: 'file' as const, size: 10 + kaynak.surum, mtimeMs: 5 + kaynak.surum, isLink: false } }))
  on('fs.read', () => ({ value: JSON.stringify(kaynak.ham) }))
  on('fs.exists', () => ({ value: true }))
  on('session.id', () => ({ value: BU }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('process.run', ($, e) => {
    argv.push([...e.argv])
    return { value: { exitCode: 0, stdout: 'http://127.0.0.1:8765/', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.render', () => ({ type: 'Box', props: {}, children: [] }))  // motorun kendi (boş) çizimi
}

const metin = (agac: unknown): string => JSON.stringify(agac)

test('para tr-TR biçiminde: $5,73', () => {
  expect(usd(5.73)).toBe('$5,73')
  expect(usd(0.4)).toBe('$0,40')
  expect(usd(999.99)).toBe('$999,99')
  expect(usd(1668.2)).toBe('$1.668')  // ≥ 1000: sıfır ondalık
  expect(usd(-5.65)).toBe('−$5,65')
})

test('donustur: olay satırları elenir, markdown soyulur, teslim yalnız sayı olur', () => {
  const o = donustur(HAM, BU)
  expect(o.defter).toEqual([{ saat: '10:00', gorev: 'G-001', metin: 'README satırı eklendi' }])
  expect(o.teslim).toEqual({ sayi: 1, sonId: 'G-003', sonSaat: '11:07' })
  expect(o.kartlar?.map(k => k.id)).toEqual(['G-001', 'G-002', 'G-004'])
})

test('donustur: isler alanı olduğu gibi geçer; yoksa boş dizi olur', () => {
  expect(donustur(HAM, BU).isler).toEqual(HAM.isler)
  const { isler: _yok, ...islersiz } = HAM
  expect(donustur(islersiz as HamOzet, BU).isler).toEqual([])
})

test('eylemImzasi: yalnız ret/teslim bekleyen/rapor imza üretir; kart değişince imza değişir', () => {
  expect(eylemImzasi(donustur(SESSIZ, BU))).toBe('')
  const bir = eylemImzasi(donustur(HAM, BU))
  expect(bir).not.toBe('')
  // ret sayısı aynı (1), ama reddedilen kart başka: imza farklı olmalı
  const baskaKart = { ...HAM, kartlar: HAM.kartlar!.map(k => (k.id === 'G-002' ? { ...k, durum: 'teslim' } : k.id === 'G-004' ? { ...k, durum: 'reddedildi' } : k)) }
  expect(baskaKart.kartlar.filter(k => k.durum === 'reddedildi').length).toBe(1)
  expect(eylemImzasi(donustur(baskaKart, BU))).not.toBe(bir)
})

for (const surface of ['terminal', 'desktop'] as const) {
  test(`pane yalnız yapılanlar/yapılacaklar gösterir; üstte toplam (${surface})`, async ($, on) => {
    sahte(on, HAM)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'Pane', requestId: 'orkestra', props: PANE_PROPS })
    const t = metin(await ui.drawn())
    for (const parca of ['Yapılan 4 / toplam 7 iş · %57', 'Yapılanlar (4)', '3/5  Orkestra açık maddeler', 'Yapılacaklar (3)',
      'Orkestra açık maddeler · 2 açık', '○ Panel sadeleşsin', 'Langfuse erken uyarı · 1 açık', 'Ayrıntı: /orkestra-web', `veri ${SAAT}`]) {
      expect(t).toContain(parca)
    }
    const sira = ['Yapılan 4', 'Yapılanlar (', 'Yapılacaklar (', 'Ayrıntı:'].map(p => t.indexOf(p))
    expect(sira).toEqual([...sira].sort((a, b) => a - b))
    // eski görünüm kullanıcıya gösterilmez
    for (const yok of ['Kod taraması', 'Reddedildi', 'Bu sohbet', 'bugün $', 'Son olaylar', 'Perspektif raporu', 'kart teslim edildi', 'veri eski']) {
      expect(t).not.toContain(yok)
    }
  })

  test(`veri 10 dk'dan eskiyse uyarı satırı çıkar (${surface})`, async ($, on) => {
    sahte(on, ESKI)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'Pane', requestId: 'orkestra', props: PANE_PROPS })
    expect(metin(await ui.drawn())).toContain(`veri eski (${ESKI_SAAT})`)
  })

  test(`todo'su olmayan işlerde sıfırdan başlar, uretim yoksa veri parçası yazılmaz (${surface})`, async ($, on) => {
    const bos: HamOzet = { ...HAM, uretim: undefined as unknown as string, isler: [] }
    sahte(on, bos)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'Pane', requestId: 'orkestra', props: PANE_PROPS })
    const t = metin(await ui.drawn())
    expect(t).toContain('Yapılan 0 / toplam 0 iş · %0')
    expect(t).toContain('Henüz biten madde yok')
    expect(t).toContain('Açık madde yok')
    expect(t).not.toContain('veri ')
    expect(t).toContain('Ayrıntı: /orkestra-web')
  })

  test(`ozet.json yoksa nedenini gösterir (${surface})`, async ($, on) => {
    sahte(on, null)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'Pane', requestId: 'orkestra', props: PANE_PROPS })
    expect(metin(await ui.drawn())).toContain('ozet.json henüz yok')
  })

  test(`bant eylem gerektirince görünür (maliyet yok), Gizle ile kaybolur (${surface})`, async ($, on) => {
    sahte(on, HAM)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'AbovePrompt', props: BANT_PROPS })
    const once = metin(await ui.drawn())
    expect(once).toContain('1 ret')
    expect(once).toContain('teslime hazır')
    expect(once).toContain('perspektif raporu hazır')
    expect(once).not.toContain('oturum $')  // maliyet bantta yok
    await ui.press({ key: 'gizle' })
    const sonra = await ui.drawn().then(metin, () => '')
    expect(sonra).not.toContain('1 ret')
  })

  test(`Gizle sonrası yeni ret gelince bant geri gelir; sayı aynı, kart farklıysa da (${surface})`, async ($, on) => {
    const kaynak: Kaynak = { ham: HAM, surum: 0 }
    sahte(on, HAM, [], kaynak)
    const saat = mock.clock(on)
    on('command.register', () => ({ value: undefined }))
    on('session.start', ($, e) => ({ cwd: e.cwd }))
    await $.session.start({ cwd: '/proje', surface, isInteractive: true })  // session.start: komutlar, ilk okuma, 3 sn'lik yoklama
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'AbovePrompt', props: BANT_PROPS })
    expect(metin(await ui.drawn())).toContain('1 ret')
    await ui.press({ key: 'gizle' })
    expect(await ui.drawn().then(metin, () => '')).not.toContain('1 ret')
    // aynı veri tekrar gelse de gizli kalır
    await saat.advance(3000)
    expect(await ui.drawn().then(metin, () => '')).not.toContain('1 ret')
    // yeni ret (G-004 de reddedildi): farklı mtime/size, yoklamayla okunur, bant geri gelir
    kaynak.ham = { ...HAM, sayac: { onaylandi: 1, reddedildi: 2 }, kartlar: HAM.kartlar!.map(k => (k.id === 'G-004' ? { ...k, durum: 'reddedildi' } : k)) }
    kaynak.surum++
    await saat.advance(3000)
    expect(metin(await ui.drawn())).toContain('2 ret')
    await ui.press({ key: 'gizle' })
    expect(await ui.drawn().then(metin, () => '')).not.toContain('2 ret')
    // ret sayısı aynı (2): G-002 çözüldü ama G-005 reddedildi; kart değiştiği için bant yine geri gelir
    kaynak.ham = { ...HAM, sayac: { onaylandi: 1, reddedildi: 2 }, kartlar: [
      ...HAM.kartlar!.map(k => (k.id === 'G-004' ? { ...k, durum: 'reddedildi' } : k.id === 'G-002' ? { ...k, durum: 'teslim' } : k)),
      { id: 'G-005', baslik: 'Yeni ret', durum: 'reddedildi', basamak: 'T2', isci: 1, denetim: 'ret', usd: 0.1, oturum: BU },
    ] }
    kaynak.surum++
    await saat.advance(3000)
    expect(metin(await ui.drawn())).toContain('2 ret')
  })

  test(`sayac alanı olmayan eski ozet.json'da bant kartlardan sayar, boş bant çıkmaz (${surface})`, async ($, on) => {
    const { sayac: _yok, ...sayacsiz } = HAM
    sahte(on, sayacsiz as HamOzet)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'AbovePrompt', props: BANT_PROPS })
    const t = metin(await ui.drawn())
    expect(t).toContain('1 ret')
    expect(t).toContain('1 teslime hazır')
  })

  test(`yalnız oturum maliyeti varken bant çizilmez (${surface})`, async ($, on) => {
    sahte(on, SESSIZ)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'AbovePrompt', props: BANT_PROPS })
    const t = await ui.drawn().then(metin, () => '')
    expect(t).not.toContain('Orkestra ·')
    expect(t).not.toContain('oturum')
  })
}

test('/orkestra-web HTML paneli başlatır ve adresi verir', async ($, on) => {
  const argv: string[][] = []
  sahte(on, HAM, argv)
  const r = await $.command.run({ command: 'orkestra-web', args: '' })
  expect(argv.some(a => a.includes('panel'))).toBe(true)
  expect(JSON.stringify(r)).toContain('http://127.0.0.1:8765/')
})
