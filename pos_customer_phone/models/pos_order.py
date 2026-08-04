import re
from odoo import models, fields, api

class PosOrder(models.Model):
    _inherit = 'pos.order'

    customer_phone = fields.Char(string='Customer Phone / رقم جوال العميل')

    @api.model
    def _order_fields(self, ui_order):
        fields_clean = super(PosOrder, self)._order_fields(ui_order)
        phone = ui_order.get('customer_phone')
        if phone:
            # Clean and normalize to +966 format
            cleaned_phone = re.sub(r'\D', '', str(phone))
            if cleaned_phone.startswith('05'):
                cleaned_phone = '+966' + cleaned_phone[1:]
            elif cleaned_phone.startswith('009665'):
                cleaned_phone = '+' + cleaned_phone[2:]
            elif cleaned_phone.startswith('9665'):
                cleaned_phone = '+' + cleaned_phone
            elif not cleaned_phone.startswith('+') and cleaned_phone.startswith('5'):
                cleaned_phone = '+966' + cleaned_phone
            fields_clean['customer_phone'] = cleaned_phone
        return fields_clean