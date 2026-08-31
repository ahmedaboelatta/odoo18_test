from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _get_letterhead_address_values(self):
        """Return structured Saudi national-address values without requiring EDI."""
        self.ensure_one()

        def value(*field_names):
            for field_name in field_names:
                if field_name in self._fields and self[field_name]:
                    field_value = self[field_name]
                    return field_value.display_name if hasattr(field_value, 'display_name') else field_value
            return ''

        scheme = value(
            'l10n_sa_edi_additional_identification_scheme',
            'l10n_sa_additional_identification_scheme',
        )
        additional_id = value(
            'l10n_sa_edi_additional_identification_number',
            'l10n_sa_additional_identification_number',
        )
        crn = additional_id if scheme == 'CRN' else value('company_registry')

        return {
            'street': value('street'),
            'building_no': value('l10n_sa_edi_building_number'),
            'additional_no': value('l10n_sa_edi_plot_identification'),
            'postal_code': value('zip'),
            'city': value('city', 'city_id'),
            'district': value('street2'),
            'country': value('country_id'),
            'vat': value('vat'),
            'crn': crn,
        }
