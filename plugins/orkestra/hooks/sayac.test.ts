import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

function sahte(on: On, argv: string[][], orkestraAcik: boolean) {
  on('process.run', ($, e) => {
    argv.push([...e.argv])
    return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('fs.exists', () => ({ value: orkestraAcik }))
  on('session.id', () => ({ value: 'oturum-1' }))
  on('turn.complete', ($, e) => ({ text: e.answer }))
}

const USAGE = { model: 'claude-sonnet-5-5', input_tokens: 12, output_tokens: 3456, cache_read_input_tokens: 9000, cache_creation_input_tokens: 400 }

test('alt ajan turunun kesin kullanımını agent id ile kaydeder', async ($, on) => {
  const argv: string[][] = []
  sahte(on, argv, true)
  await $.turn.complete({ answer: 'bitti', durationMs: 4200, isAborted: false, turnId: 't1', agentId: 'ajan-9', reason: 'answer', usage: USAGE })
  expect(argv.length).toBe(1)
  const a = argv[0] ?? []
  expect(a.slice(2, 4)).toEqual(['maliyet', 'tur'])
  expect(a).toContain('--agent-id')
  expect(a[a.indexOf('--agent-id') + 1]).toBe('ajan-9')
  expect(a[a.indexOf('--cikis') + 1]).toBe('3456')
  expect(a[a.indexOf('--model') + 1]).toBe('claude-sonnet-5-5')
  expect(a[a.indexOf('--oturum') + 1]).toBe('oturum-1')
})

test('ana döngü turunda agent id yok', async ($, on) => {
  const argv: string[][] = []
  sahte(on, argv, true)
  await $.turn.complete({ answer: 'tamam', durationMs: 1000, isAborted: false, turnId: 't2', reason: 'answer', usage: USAGE })
  expect(argv.length).toBe(1)
  expect(argv[0]).not.toContain('--agent-id')
})

test('orkestra kapalı projede hiçbir şey çalıştırmaz', async ($, on) => {
  const argv: string[][] = []
  sahte(on, argv, false)
  await $.turn.complete({ answer: 'x', durationMs: 10, isAborted: false, turnId: 't3', reason: 'answer', usage: USAGE })
  expect(argv.length).toBe(0)
})

test('kullanım yoksa (kesinti) kayıt yok', async ($, on) => {
  const argv: string[][] = []
  sahte(on, argv, true)
  await $.turn.complete({ answer: '', durationMs: 10, isAborted: true, turnId: 't4', reason: 'aborted' })
  expect(argv.length).toBe(0)
})
