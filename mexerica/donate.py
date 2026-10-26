"""Optional Pix donation: the static BR Code (copy-and-paste) and its QR image."""

import io

PIX_KEY = "53c6b7e4-a1fc-4dff-b32d-8fb226309bfb"
PIX_RECEIVER = "Nicolas R de Queiroz"
PIX_BANK = "Banco Inter"
# Static BR Code issued by the bank for the key above, with no fixed amount.
PIX_PAYLOAD = (
    "00020101021126580014br.gov.bcb.pix0136" + PIX_KEY + "5204000053039865802BR"
    "5920NICOLAS R DE QUEIROZ6008BRASILIA62070503***6304EA03"
)
DONATE_URL = "https://github.com/Nicolas-Queiroz/Mexerica#apoie-com-pix"


def crc16_ccitt(data: str) -> str:
    """CRC16-CCITT (0xFFFF, poly 0x1021) as the four hex digits the BR Code ends with."""
    crc = 0xFFFF
    for byte in data.encode():
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def payload_is_valid(payload: str = PIX_PAYLOAD) -> bool:
    return payload[-8:-4] == "6304" and crc16_ccitt(payload[:-4]) == payload[-4:]


def qr_png(payload: str = PIX_PAYLOAD, scale: int = 8) -> bytes:
    import segno

    buffer = io.BytesIO()
    segno.make(payload, error="m", micro=False).save(buffer, kind="png", scale=scale, border=2)
    return buffer.getvalue()
