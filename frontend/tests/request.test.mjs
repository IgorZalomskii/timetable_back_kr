import { test } from 'node:test';
import assert from 'node:assert/strict';
import { requestJson, RequestFailure } from '../src/request.ts';

test('request deadline covers missing headers and aborts without replay', async (t) => {
  let calls = 0, signal;
  t.mock.method(globalThis, 'fetch', async (_, init) => { calls++; signal = init.signal; return new Promise(() => {}); });
  await assert.rejects(requestJson('/test', {method:'PUT'}, 25), e => e instanceof RequestFailure && e.kind === 'timeout');
  assert.equal(calls, 1); assert.equal(signal.aborted, true);
});
test('request deadline also covers a body that never finishes', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ok:true,json:()=>new Promise(()=>{})}));
  await assert.rejects(requestJson('/test', {}, 25), e => e.kind === 'timeout');
});
test('connection failure is readable and is not retried', async (t) => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => {calls++; throw new TypeError('offline');});
  await assert.rejects(requestJson('/test', {}), e => e.kind === 'network');
  assert.equal(calls,1);
});
test('malformed success is not accepted as application data', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<html>proxy</html>'));
  await assert.rejects(requestJson('/test', {}), e => e.kind === 'invalid');
});
test('HTML rate limit preserves status and understandable message', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('rate limit',{status:429}));
  const result = await requestJson('/test', {});
  assert.equal(result.response.status,429); assert.match(result.data.detail,/Слишком много/);
});
test('a later request succeeds after a timeout', async (t) => {
  let calls=0;
  t.mock.method(globalThis, 'fetch', async () => ++calls===1 ? new Promise(()=>{}) : new Response('{"ok":true}'));
  await assert.rejects(requestJson('/test', {},25));
  assert.deepEqual((await requestJson('/test', {})).data,{ok:true});
  assert.equal(calls,2);
});
