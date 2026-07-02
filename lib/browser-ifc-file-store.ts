"use client";

const DB_NAME = "eyerector-ifc-file";
const DB_VERSION = 2;
const STORE_NAME = "files";
const CURRENT_FILE_KEY = "current";

type StoredIfcFile = {
  name: string;
  type: string;
  lastModified: number;
  bytes: ArrayBuffer;
};

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (db.objectStoreNames.contains(STORE_NAME)) {
        db.deleteObjectStore(STORE_NAME);
      }
      db.createObjectStore(STORE_NAME);
    };
    req.onerror = () => reject(req.error ?? new Error("Failed to open IFC storage."));
    req.onsuccess = () => resolve(req.result);
  });
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/** iOS often exposes iCloud files as size=0 until arrayBuffer() finishes downloading. */
export async function readIfcFileBytes(
  file: File,
  onProgress?: (message: string) => void,
): Promise<ArrayBuffer> {
  const attempts = 40;
  let lastError: unknown = null;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    onProgress?.(
      file.size > 0
        ? `Reading ${file.name} (${file.size.toLocaleString()} bytes)...`
        : `Waiting for iPhone to download ${file.name || "IFC"}... (${attempt}/${attempts})`,
    );
    try {
      const bytes = await file.arrayBuffer();
      if (bytes.byteLength > 0) return bytes;
      lastError = new Error("File read returned 0 bytes.");
    } catch (err) {
      lastError = err;
    }
    await wait(500);
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("Could not read IFC file from this device. Download it from iCloud/Files first.");
}

export async function saveIfcBytesForViewer(
  file: File,
  bytes: ArrayBuffer,
): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      const stored: StoredIfcFile = {
        name: file.name || "model.ifc",
        type: file.type || "application/octet-stream",
        lastModified: file.lastModified || Date.now(),
        bytes,
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

export async function readAndSaveIfcFile(
  file: File,
  onProgress?: (message: string) => void,
): Promise<File> {
  onProgress?.("Reading IFC from phone...");
  const bytes = await readIfcFileBytes(file, onProgress);
  onProgress?.(`Saving ${bytes.byteLength.toLocaleString()} bytes...`);
  await saveIfcBytesForViewer(file, bytes);
  return new File([bytes], file.name || "model.ifc", {
    type: file.type || "application/octet-stream",
    lastModified: file.lastModified || Date.now(),
  });
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
    if (!stored?.bytes || stored.bytes.byteLength === 0) return null;
    return new File([stored.bytes], stored.name || "model.ifc", {
      type: stored.type || "application/octet-stream",
      lastModified: stored.lastModified || Date.now(),
    });
  } finally {
    db.close();
  }
}
