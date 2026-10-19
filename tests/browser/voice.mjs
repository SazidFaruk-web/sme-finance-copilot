// Run against tests/browser/server.py, never the owner database. No real speech or cloud API is used.
import { chromium } from '../../data/ui-review/node_modules/playwright-core/index.mjs';
import assert from 'node:assert/strict';
const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ baseURL: 'http://127.0.0.1:8002', viewport: { width: 360, height: 800 }, colorScheme: 'dark', reducedMotion: 'reduce' });
await context.addInitScript(() => {
  localStorage.setItem('tour_done:nusrat', '1');
  class Speech {
    constructor() { window.reviewSpeech = this; }
    start() {}
    stop() { this.onend?.(); }
  }
  window.SpeechRecognition = Speech;
});
const page = await context.newPage(), errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto('/');
  await page.locator('#auth-username').fill('nusrat');
  await page.locator('#auth-password').fill('owner-demo-2026');
  await page.locator('.auth-submit').click();
  await page.locator('.guided-home').waitFor();
  await page.locator('#nav-chat').click();
  const input = page.locator('.chat-question');
  await input.fill('Paid shop rent');
  let requests = 0;
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/api/chat/stream')) requests++; });
  const before = await (await page.request.get('/api/data/transactions?limit=1')).json();
  await page.getByRole('button', { name: 'Use voice; review the text before sending', exact: true }).click();
  await page.evaluate(() => {
    window.reviewSpeech.onresult({ results: [[{ transcript: '1500 taka cash' }]] });
    window.reviewSpeech.onend();
  });
  assert.equal(await input.inputValue(), 'Paid shop rent 1500 taka cash');
  assert.equal(requests, 0);
  assert.equal(await input.evaluate(node => node === document.activeElement), true);
  const reviewed = await (await page.request.get('/api/data/transactions?limit=1')).json();
  assert.equal(reviewed.total, before.total);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: 'data/ui-review/voice-review-mobile.png', fullPage: true });
  await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/api/chat/stream')),
    page.getByRole('button', { name: 'Send', exact: true }).click(),
  ]);
  await page.waitForFunction(() => !document.querySelector('#chatlog .typing'));
  assert.equal(requests, 1);
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  assert.ok(await page.evaluate(async () => Boolean(await caches.match('/static/voice.js?v=1', { ignoreVary: true }))));
  await context.setOffline(true); await page.reload();
  await page.getByText('Connection unavailable. Only this device’s saved drafts are available.', { exact: true }).waitFor();
  assert.equal(errors.length, 0, errors.join('\n'));
  console.log('PASS voice requires review, preserves typed input, sends only on click, fits mobile, and loads offline.');
} finally { await browser.close(); }
