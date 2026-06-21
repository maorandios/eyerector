"use client";

import { useEffect } from "react";

export function RegisterSW() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

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
  }, []);

  return null;
}
