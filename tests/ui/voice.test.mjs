import test from 'node:test';
import assert from 'node:assert/strict';
import { createVoiceButton } from '../../frontend/voice.js';

function fixture() {
  let recognition, click;
  const classes = new Set();
  const button = { classList: { add: x => classes.add(x), remove: x => classes.delete(x) }, addEventListener: (_, fn) => { click = fn; } };
  const h = (_tag, attrs) => Object.assign(button, attrs);
  class Speech { constructor() { recognition = this; } start() {} stop() { this.onend(); } }
  const events = [], input = { value: 'From Rahman:', dispatchEvent: e => events.push(e.type), focus() { this.focused = true; } };
  return { h, Speech, input, events, classes, get recognition() { return recognition; }, click: () => click() };
}

test('recognised speech stays editable and never submits the field', () => {
  const f = fixture();
  const button = createVoiceButton({ ...f, language: 'en' });
  f.click();
  assert.equal(button.type, 'button');
  f.recognition.onresult({ results: [[{ transcript: 'received 1000 taka' }]] });
  assert.equal(f.input.value, 'From Rahman: received 1000 taka');
  assert.deepEqual(f.events, ['input']); // no submit, send or change action
  assert.equal(f.input.focused, true);
  assert.match(button['aria-label'], /review/i);
});

test('Bangla recognition errors preserve the draft and end the listening state', () => {
  const f = fixture();
  createVoiceButton({ ...f, language: 'bn' });
  f.click(); assert.equal(f.recognition.lang, 'bn-BD');
  f.recognition.onerror();
  assert.equal(f.input.value, 'From Rahman:');
  assert.equal(f.classes.has('on'), false);
  assert.deepEqual(f.events, []);
});

test('unsupported speech leaves typing available', () => {
  const f = fixture();
  const button = createVoiceButton({ ...f, Speech: null });
  assert.equal(button.disabled, true);
  assert.match(button.title, /type instead/);
});
