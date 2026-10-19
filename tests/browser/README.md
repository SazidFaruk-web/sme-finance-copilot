# Guided pilot browser checks

These optional rendered checks use Microsoft Edge on Windows and an isolated demo database under ignored `data/ui-review/runtime/`. They never use the real app database, shared model or SMS provider. Run from the project root.

```powershell
npm install --prefix data/ui-review --no-save --package-lock=false playwright-core
.\.venv\Scripts\python.exe tests/browser/server.py
```

In another terminal:

```powershell
node tests/browser/pilot.mjs
```

The focused voice regression uses the same isolated server:

```powershell
node tests/browser/voice.mjs
```

It mocks speech recognition and verifies that the text remains editable, no request or record is created before Send, existing typed text survives, the composer fits a narrow dark screen, and the updated application shell opens offline. It does not contact a speech provider or a cloud model.

Stop the review server with Ctrl+C when finished. Port 8002 must be free. The script checks the two-card Home, three-choice task menu, confirmed record, Bangla numerals, input preservation across language changes, six-answer checkpoints, product test, complete loan schedule, 320px dark layout, reminder settings, actual offline reload and manual draft sync. Screenshots remain under ignored `data/ui-review/`. It intentionally disconnects the browser; a failed `/api/auth/me` request during that phase is expected. A fresh browser context isolates local drafts between runs.

The dependency-free unit checks remain `node --experimental-default-type=module --test tests/ui/*.test.mjs`. Backend rules, permissions, stale previews, duplicates, SMS failure handling and documents are covered by `tests/test_pilot.py`. Real-model tests use the existing `slow` marker and need the separate model service.
