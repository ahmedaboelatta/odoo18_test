from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestTechrarSyncMapping(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env['techrar.config'].create({
            'name': 'Test', 'techrar_api_token': 'test-token'
        })
        cls.wizard = cls.env['techrar.sync.wizard'].create({
            'config_id': cls.config.id,
            'from_date': '2026-08-28',
            'to_date': '2026-08-28',
        })
        cls.order_data = {
            'id': 1001,
            'subscription': {'id': 7003, 'name_en': 'Test Subscription'},
            'cart_amount': 100.0,
            'total_amount': 90.0,
        }

    def test_missing_mapping_does_not_create_product(self):
        product_count = self.env['product.product'].search_count([])
        lines, mapping = self.wizard._build_order_lines(self.order_data)
        self.assertFalse(lines)
        self.assertFalse(mapping.product_id)
        self.assertEqual(mapping.mapping_state, 'unmapped')
        self.assertEqual(self.env['product.product'].search_count([]), product_count)

    def test_mapped_subscription_builds_one_financial_line(self):
        product = self.env['product.product'].create({'name': 'Mapped Product', 'type': 'service'})
        mapping = self.env['techrar.product.mapping'].create({
            'techrar_external_id': '7003',
            'techrar_name': 'Test Subscription',
            'product_id': product.id,
        })
        lines, returned_mapping = self.wizard._build_order_lines(self.order_data)
        self.assertEqual(returned_mapping, mapping)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][2]['product_id'], product.id)
        self.assertEqual(lines[0][2]['price_unit'], 90.0)

    def test_payment_automation_requires_invoice_automation(self):
        with self.assertRaises(UserError):
            self.config.write({'auto_register_payments': True})
