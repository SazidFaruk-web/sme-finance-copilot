import test from 'node:test';
import assert from 'node:assert/strict';
import { numericInput } from '../../frontend/pilot-store.js';

test('Bangla numerals and grouping preserve a reviewable amount', () => {
  assert.equal(numericInput(' ১,২০৩.৫০ '), '1203.50');
  assert.equal(numericInput('0'), '0');
  assert.equal(numericInput(''), '');
  assert.equal(numericInput('unknown'), 'unknown'); // never coerce missing facts to zero
});
