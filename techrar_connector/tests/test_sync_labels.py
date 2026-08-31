from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestTechrarSyncLabels(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config = cls.env['techrar.config'].create({
            'name': 'Test', 'techrar_api_token': 'test-token'
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

    def test_subscription_creates_label_without_product(self):
        product_count = self.env['product.product'].search_count([])
        lines = self.wizard._build_order_lines(self.order_data)
        values = lines[0][2]
        self.assertEqual(values['display_type'], 'line_note')
        self.assertNotIn('product_id', values)
        self.assertIn('Test Subscription', values['name'])
        self.assertIn('7003', values['name'])
        self.assertEqual(self.env['product.product'].search_count([]), product_count)
