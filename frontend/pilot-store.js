// Only explicit drafts and guided progress are cached; never cookies, passwords or API responses.
const DB = "sme-pilot-drafts-v1";
let profile = null;
const request = req => new Promise((resolve, reject) => { req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error); });
async function database() {
  const req = indexedDB.open(DB, 1);
  req.onupgradeneeded = () => req.result.createObjectStore("drafts", { keyPath: "key" });
  return request(req);
}
export function setDraftOwner(user) {
  profile = user ? `${user.business_id}:${user.username}` : null;
}
export async function saveLocal(id, value) {
  if (!profile) throw new Error("Sign in first");
  const db = await database(), tx = db.transaction("drafts", "readwrite");
  const done = new Promise((resolve, reject) => { tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); });
  tx.objectStore("drafts").put({ key: `${profile}:${id}`, owner: profile, id, value, saved_at: new Date().toISOString() });
  await done; db.close();
}
export async function localDrafts() {
  if (!profile) return [];
  const db = await database(), rows = await request(db.transaction("drafts").objectStore("drafts").getAll());
  db.close(); return rows.filter(r => r.owner === profile);
}
export async function removeLocal(id) {
  if (!profile) return;
  const db = await database(), tx = db.transaction("drafts", "readwrite");
  const done = new Promise((resolve, reject) => { tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); });
  tx.objectStore("drafts").delete(`${profile}:${id}`); await done; db.close();
}
export async function clearLocalOwner() {
  const rows = await localDrafts();
  await Promise.all(rows.map(r => removeLocal(r.id)));
  profile = null;
}
export const numericInput = value => String(value).replace(/[০-৯]/g, x => "০১২৩৪৫৬৭৮৯".indexOf(x)).replaceAll(",", "").trim();

export function registerOffline() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch(() => {});
}
