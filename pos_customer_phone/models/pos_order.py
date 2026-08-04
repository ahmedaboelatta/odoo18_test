import re

from odoo import fields, models, api


class PosOrder(models.Model):
    _inherit = "pos.order"

    customer_phone = fields.Char(string="Customer Phone")

    def _normalize_phone(self, phone):
        if not phone:
            return False
        digits = re.sub(r"\D", "", phone)
        if digits.startswith("00"):
            digits = digits[2:]
        if digits.startswith("966"):
            digits = "0" + digits[3:]
        if digits.startswith("5") and len(digits) == 9:
            return "+966" + digits
        if digits.startswith("05") and len(digits) == 10:
            return "+966" + digits[1:]
        if digits.startswith("009665"):
            digits = "0" + digits[6:]
            return "+966" + digits[1:]
        if digits.startswith("+9665") and len(digits) == 13:
            return "+966" + digits[5:]
        if digits.startswith("9665") and len(digits) == 12:
            return "+966" + digits[3:]
        return "+966" + digits if digits.startswith("5") and len(digits) == 9 else False

    def name_search(self, name="", args=None, operator="ilike", limit=100):
        if name and any(c.isdigit() for c in name):
            normalized = self._normalize_phone(name)
            if normalized:
                domain = [("customer_phone", operator, normalized)]
                records = self.search(domain + (args or []), limit=limit)
                return [(record.id, record.display_name) for record in records.sudo()]
        return super().name_search(name, args=args, operator=operator, limit=limit)
