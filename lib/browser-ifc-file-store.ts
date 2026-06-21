"use client";

const DB_NAME = "eyerector-ifc-file";
const DB_VERSION = 1;
const STORE_NAME = "files";
const CURRENT_FILE_KEY = "current";

type StoredIfcFile = {
  name: string;
  type: string;
  lastModified: number;
  data: Blob;
};

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onerror = () => reject(req.error ?? new Error("Failed to open IFC storage."));
    req.onsuccess = () => resolve(req.result);
  });
}

export async function saveIfcFileForViewer(file: File): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      const stored: StoredIfcFile = {
        name: file.name || "model.ifc",
        type: file.type || "application/octet-stream",
        lastModified: file.lastModified || Date.now(),
        data: file,
      };
      store.put(stored, CURRENT_FILE_KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error ?? new Error("Failed to save IFC file."));
      tx.onabort = () => reject(tx.error ?? new Error("Saving IFC file was aborted."));
    });
  } finally {
    db.close();
  }
}

export async function loadIfcFileForViewer(): Promise<File | null> {
  const db = await openDb();
  try {
    const stored = await new Promise<StoredIfcFile | undefined>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).get(CURRENT_FILE_KEY);
      req.onsuccess = () => resolve(req.result as StoredIfcFile | undefined);
      req.onerror = () => reject(req.error ?? new Error("Failed to load IFC file."));
    });
    if (!stored?.data) return null;
    return new File([stored.data], stored.name || "model.ifc", {
      type: stored.type || "application/octet-stream",
      lastModified: stored.lastModified || Date.now(),
    });
  } finally {
    db.close();
  }
}
