import test from 'node:test';
import assert from 'node:assert/strict';
import { AUTH_COPY, validateAuth, authErrorKey } from '../../frontend/auth-copy.js';

test('each authentication message exists in both languages, with no mixed-language copy', () => {
  assert.deepEqual(Object.keys(AUTH_COPY.en).sort(), Object.keys(AUTH_COPY.bn).sort());
  for (const message of Object.values(AUTH_COPY.en)) {
    assert.ok(message.trim()); assert.doesNotMatch(message, /[\u0980-\u09ff]/);
  }
  for (const message of Object.values(AUTH_COPY.bn)) {
    assert.ok(message.trim()); assert.doesNotMatch(message, /[A-Za-z]/);
  }
});

test('login checks missing credentials without applying signup password rules', () => {
  assert.deepEqual(validateAuth('login', { username: '   ', password: '' }), { username: 'requiredUsername', password: 'requiredPassword' });
  assert.deepEqual(validateAuth('login', { username: ' Nusrat ', password: 'legacy' }), {});
});

test('signup validates business, owner, username and matching passwords before calling the API', () => {
  const values = { business: 'রিনার দোকান', name: 'রিনা', username: 'Rina.shop', password: 'strong-pass-123', confirm: 'strong-pass-123' };
  assert.deepEqual(validateAuth('signup', values), {});
  const errors = validateAuth('signup', { ...values, business: ' ', name: ' ', username: 'রিনা', password: 'short', confirm: 'different' });
  assert.deepEqual(errors, { business: 'requiredBusiness', name: 'requiredName', username: 'usernameFormat', password: 'shortPassword', confirm: 'mismatch' });
  assert.equal(validateAuth('signup', { ...values, business: 'A' }).business, 'shortBusiness');
});

test('Unicode password length follows the server character count instead of UTF-16 units', () => {
  const errors = validateAuth('signup', { business: 'Shop', name: 'Rina', username: 'rina', password: '😀😀😀😀', confirm: '😀😀😀😀' });
  assert.equal(errors.password, 'shortPassword');
});

test('authentication failures map to localized messages without exposing raw API text', () => {
  const cases = [
    [{ status: 401, message: 'invalid username or password' }, 'invalidCredentials'],
    [{ status: 401, message: 'account temporarily locked after repeated failed logins' }, 'locked'],
    [{ status: 409, message: 'that username is taken' }, 'usernameTaken'],
    [{ status: 403, message: 'sign-up is turned off on this server' }, 'signupDisabled'],
    [{ status: 422, message: '[{"loc":["body","password"],"type":"string_too_short"}]' }, 'invalidDetails'],
    [{ status: 429, message: 'too many requests' }, 'rateLimited'],
    [{ status: 503, message: 'internal details' }, 'unavailable'],
    [new TypeError('Failed to fetch'), 'network'],
    ['Please log in again.', 'expired'],
  ];
  for (const [error, key] of cases) {
    assert.equal(authErrorKey(error), key);
    assert.ok(AUTH_COPY.en[key] && AUTH_COPY.bn[key]);
  }
});
