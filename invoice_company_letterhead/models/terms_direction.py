import re

from odoo.tools import html2plaintext


_ARABIC_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]')


def get_terms_direction(value):
    """Return the natural direction of an HTML terms-and-conditions value."""
    text = html2plaintext(value or '').strip()
    return 'rtl' if _ARABIC_RE.search(text) else 'ltr'
