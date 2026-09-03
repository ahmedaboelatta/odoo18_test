from num2words import num2words

from odoo import models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _get_voucher_amount_in_words(self, language):
        """Return voucher amount words without requiring an active Odoo language."""
        self.ensure_one()
        language = 'ar' if language == 'ar' else 'en'
        words = num2words(self.amount, lang=language)
        currency_labels = {
            'SAR': {'ar': 'ريال سعودي', 'en': 'Saudi Riyal'},
            'USD': {'ar': 'دولار أمريكي', 'en': 'US Dollar'},
            'EUR': {'ar': 'يورو', 'en': 'Euro'},
            'AED': {'ar': 'درهم إماراتي', 'en': 'UAE Dirham'},
            'EGP': {'ar': 'جنيه مصري', 'en': 'Egyptian Pound'},
        }
        currency = currency_labels.get(self.currency_id.name, {})
        currency_name = currency.get(language) or self.currency_id.name or ''
        return '%s %s' % (words, currency_name)
