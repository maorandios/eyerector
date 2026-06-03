"""Quick smoke test for POST /upload-pdf."""
from __future__ import annotations

import json
import sys

import fitz
import urllib.request

def main() -> int:
    doc = fitz.open()
    doc.new_page(width=400, height=300)
    pdf_bytes = doc.tobytes()
    doc.close()

    boundary = "----eyesteelboundary"
    parts: list[bytes] = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="test.pdf"\r\n',
        b"Content-Type: application/pdf\r\n\r\n",
        pdf_bytes,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    req = urllib.request.Request(
        "http://127.0.0.1:8013/upload-pdf",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode())
    print(json.dumps(data, indent=2))
    assert data.get("page_count", 0) >= 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
