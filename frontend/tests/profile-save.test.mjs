import { test } from 'node:test';
import assert from 'node:assert/strict';
import { saveProfile } from '../src/profile-save.ts';
import { requestJson } from '../src/request.ts';

const profile = { role: 'admin', name: 'Гость' };
const session = { user: { id: 42, ...profile, group_id: null, teacher_id: null }, csrf: 'test' };
const failure = (status = 0) => Object.assign(new Error('lost response'), { status });

test('successful save makes no extra request', async () => {
  const result = await saveProfile(42, profile, async () => session,
    async () => assert.fail('unexpected read'), () => assert.fail('unexpected recovery'));
  assert.equal(result, session);
});

test('lost PUT response is recovered by a single read, never by another write', async () => {
  const order = [];
  const result = await saveProfile(42, profile, async () => { order.push('write'); throw failure(); },
    async () => { order.push('read'); return session; }, () => order.push('checking'));
  assert.deepEqual(order, ['write', 'checking', 'read']);
  assert.equal(result, session);
});

test('server failure can be reconciled when the profile is already saved', async () => {
  assert.equal(await saveProfile(42, profile, async () => { throw failure(503); },
    async () => session, () => {}), session);
});

test('different role, name or account never produces a false success', async () => {
  for (const changed of [{ role: 'teacher' }, { name: 'Other' }, { id: 43 }]) {
    await assert.rejects(saveProfile(42, profile, async () => { throw failure(); },
      async () => ({ ...session, user: { ...session.user, ...changed } }), () => {}),
      /Сохранение не подтверждено/);
  }
});

test('teacher and student recovery verifies the selected directory ID too', async () => {
  for (const [role, field] of [['teacher', 'teacher_id'], ['student', 'group_id']]) {
    const wanted = { role, name: 'Гость', [field]: 12 };
    const actual = { user: { ...session.user, ...wanted } };
    assert.equal(await saveProfile(42, wanted, async () => { throw failure(); }, async () => actual, () => {}), actual);
    await assert.rejects(saveProfile(42, wanted, async () => { throw failure(); },
      async () => ({ user: { ...actual.user, [field]: 13 } }), () => {}), /Сохранение не подтверждено/);
  }
});

test('validation, CSRF, session and rate-limit errors are not disguised as saved', async () => {
  for (const status of [401, 403, 404, 409, 422, 429]) {
    const error = failure(status);
    await assert.rejects(saveProfile(42, profile, async () => { throw error; },
      async () => assert.fail('unexpected read'), () => assert.fail('unexpected recovery')), e => e === error);
  }
});

test('failed reconciliation preserves the original transport failure', async () => {
  const error = failure();
  await assert.rejects(saveProfile(42, profile, async () => { throw error; },
    async () => { throw failure(503); }, () => {}), e => e === error);
});

test('session expiry during reconciliation is surfaced as 401', async () => {
  await assert.rejects(saveProfile(42, profile, async () => { throw failure(); },
    async () => { throw failure(401); }, () => {}), e => e.status === 401);
});

test('real request deadline followed by readback recovers a committed role', async (t) => {
  const methods = [];
  t.mock.method(globalThis, 'fetch', async (_, init) => {
    methods.push(init.method);
    return init.method === 'PUT' ? new Promise(() => {}) : new Response(JSON.stringify(session));
  });
  const result = await saveProfile(42, profile,
    async () => {
      try { return (await requestJson('/auth/profile', { method: 'PUT' }, 25)).data; }
      catch (e) { throw Object.assign(e, { status: 0 }); }
    }, async () => (await requestJson('/auth/me', { method: 'GET' }, 25)).data, () => {});
  assert.deepEqual(methods, ['PUT', 'GET']);
  assert.deepEqual(result, session);
});
