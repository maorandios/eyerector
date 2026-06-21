"use client";

import { useEffect } from "react";

export function RegisterSW() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    if (process.env.NODE_ENV !== "production") {
      Promise.all([
        navigator.serviceWorker.getRegistrations().then((registrations) =>
          Promise.all(registrations.map((registration) => registration.unregister())),
        ),
        "caches" in window
          ? caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
          : Promise.resolve([]),
      ])
        .then(() => {
          if (navigator.serviceWorker.controller) {
            window.location.reload();
          }
        })
        .catch(() => undefined);
      return;
    }

    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);

  return null;
}
