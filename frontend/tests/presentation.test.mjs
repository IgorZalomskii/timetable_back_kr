import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validationMessage, lessonCount } from '../src/presentation.ts';

test('server validation retains the useful reason without the framework prefix', () => {
  assert.equal(validationMessage('Value error, Дата вне периода'), 'Дата вне периода');
  assert.equal(validationMessage('Нет связи с сервером'), 'Нет связи с сервером');
});

test('lesson counts use Russian singular, plural and teen forms', () => {
  for (const [count, word] of [[0,'занятий'],[1,'занятие'],[2,'занятия'],[5,'занятий'],[11,'занятий'],[14,'занятий'],[21,'занятие'],[22,'занятия'],[111,'занятий']]) {
    assert.equal(lessonCount(count), `${count} ${word} на неделе`);
  }
});
