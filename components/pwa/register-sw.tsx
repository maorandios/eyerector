"use client";

import { useEffect } from "react";

const SW_CLEAR_KEY = "eyerector-sw-cleared-v3";

export function RegisterSW() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    if (sessionStorage.getItem(SW_CLEAR_KEY) === "1") return;

    void Promise.all([
      navigator.serviceWorker.getRegistrations().then((registrations) =>
        Promise.all(registrations.map((registration) => registration.unregister())),
      ),
      "caches" in window
        ? caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
        : Promise.resolve([]),
    ])
      .then(() => {
        sessionStorage.setItem(SW_CLEAR_KEY, "1");
        if (navigator.serviceWorker.controller) {
          window.location.reload();
        }
      })
      .catch(() => undefined);
  }, []);

  return null;
}
