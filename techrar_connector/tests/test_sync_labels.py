from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestTechrarSyncLabels(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.general_product = cls.env['product.product'].create({
            'name': 'General Techrar Product',
            'type': 'service',
            'invoice_policy': 'order',
        })
        config = cls.env['techrar.config'].create({
            'name': 'Test',
            'techrar_api_token': 'test-token',
            'general_product_id': cls.general_product.id,
        })
        cls.wizard = cls.env['techrar.sync.wizard'].create({
            'config_id': config.id,
            'from_date': '2026-08-31',
            'to_date': '2026-08-31',
        })
        cls.order_data = {
            'id': 1001,
            'subscription': {
                'id': 7003,
                'name_en': 'Test Subscription',
                'num_of_days': 20,
            },
            'total_amount': 90.0,
        }

    def test_subscription_uses_configured_product_without_creating_products(self):
        product_count = self.env['product.product'].search_count([])
        lines = self.wizard._build_order_lines(self.order_data, self.wizard.config_id)
        financial_values = lines[0][2]
        note_values = lines[1][2]
        self.assertEqual(financial_values['product_id'], self.general_product.id)
        self.assertEqual(financial_values['price_unit'], 90.0)
        self.assertEqual(note_values['display_type'], 'line_note')
        self.assertIn('Test Subscription', note_values['name'])
        self.assertIn('7003', note_values['name'])
        self.assertEqual(self.env['product.product'].search_count([]), product_count)
