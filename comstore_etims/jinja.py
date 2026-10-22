"""Print helpers: the eTIMS QR code on a receipt."""

import base64
import io

import pyqrcode


def comstore_qr(link: str | None, scale: int = 3) -> str:
	"""An <img> of the QR code for the invoice's eTIMS verification link, or "" if unsigned.

	Usage in a print format: {{ comstore_qr(doc.comstore_signature_link) }}
	"""
	if not link:
		return ""
	buffer = io.BytesIO()
	pyqrcode.create(link).svg(buffer, scale=scale, xmldecl=False)
	data = base64.b64encode(buffer.getvalue()).decode()
	return f'<img class="comstore-qr" src="data:image/svg+xml;base64,{data}" alt="eTIMS QR">'
