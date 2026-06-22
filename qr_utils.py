from __future__ import annotations

import io
import qrcode


def qr_png(value: str) -> bytes:
    image = qrcode.make(value)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
