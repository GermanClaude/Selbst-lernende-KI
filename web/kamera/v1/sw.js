/*
 * Nova-Kamera – Service Worker. Speichert NUR die App-Hülle (diese Seite, Stil, Skripte, Symbole),
 * damit sie sich als App installieren lässt und schnell startet. Immer zuerst das Netz fragen,
 * damit Korrekturen sofort ankommen; der Speicher ist nur Ersatz ohne Netz.
 * Anfragen an andere Server (ntfy.sh) oder an /__relay laufen nie über diesen Speicher.
 */
"use strict";

const SPEICHER = "nova-kamera-v1-1";
const HUELLE = [
  "./",
  "index.html",
  "kamera.css",
  "kamera.js",
  "signal.js",
  "manifest.webmanifest",
  "icons/icon.svg",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/apple-touch-icon.png",
  "icons/icon-maskable-512.png",
  "vendor/jsQR.js",
];

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(SPEICHER).then((c) => c.addAll(HUELLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(
    caches.keys()
      .then((namen) => Promise.all(namen.filter((n) => n.startsWith("nova-kamera-") && n !== SPEICHER).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (ev) => {
  const anfrage = ev.request;
  if (anfrage.method !== "GET") return;
  const url = new URL(anfrage.url);
  const scope = new URL(self.registration.scope);
  if (url.origin !== scope.origin || !url.pathname.startsWith(scope.pathname) || url.pathname.indexOf("/__relay") >= 0) return;
  ev.respondWith(
    fetch(anfrage)
      .then((antwort) => {
        if (antwort.ok && antwort.type === "basic") {
          const kopie = antwort.clone();
          caches.open(SPEICHER).then((c) => c.put(anfrage, kopie)).catch(() => {});
        }
        return antwort;
      })
      .catch(() => caches.match(anfrage, { ignoreSearch: true }).then((treffer) => treffer || caches.match("index.html")))
  );
});
