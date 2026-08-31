from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


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
            'invoice_partner_id': cls.env.user.partner_id.id,
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
                'paused_days': 2,
                'status': 'confirmed',
                'start_date': '2026-09-02',
                'end_date': '2026-09-29',
            },
            'total_amount': 90.0,
            'customer_profile': {
                'id': 55,
                'name': 'Reference Customer',
                'mobile_number': '0500000000',
                'email': 'reference@example.com',
            },
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

    def test_subscription_dates_and_status_come_from_nested_subscription(self):
        values = self.wizard._prepare_order_values(
            self.order_data, self.env.user.partner_id, False
        )
        self.assertEqual(values['techrar_start_date'], '2026-09-02')
        self.assertEqual(values['techrar_end_date'], '2026-09-29')
        self.assertEqual(values['techrar_subscription_status'], 'confirmed')
        self.assertEqual(values['techrar_subscription_days'], 20)
        self.assertEqual(values['techrar_paused_days'], 2)
        self.assertEqual(values['partner_id'], self.wizard.config_id.invoice_partner_id.id)
        self.assertEqual(values['techrar_customer_id'], '55')
        self.assertEqual(values['techrar_customer_name'], 'Reference Customer')
        self.assertEqual(values['techrar_customer_mobile'], '0500000000')
        self.assertEqual(values['techrar_customer_email'], 'reference@example.com')

    def test_payment_memo_contains_invoice_number_and_techrar_method(self):
        invoice = self.env['account.move'].new({'name': 'INV/2026/00562'})
        memo = self.wizard._get_payment_memo(invoice, 'Apple Pay')
        self.assertEqual(memo, 'INV/2026/00562 - Apple Pay')

    def test_large_manual_date_range_is_rejected(self):
        wizard = self.env['techrar.sync.wizard'].create({
            'config_id': self.wizard.config_id.id,
            'from_date': '2026-08-01',
            'to_date': '2026-08-31',
        })
        with self.assertRaisesRegex(UserError, 'one day at a time'):
            wizard.action_sync_orders()

    def test_existing_financial_order_is_complete(self):
        order = self.env['sale.order'].create({
            'partner_id': self.env.user.partner_id.id,
            'order_line': [(0, 0, {
                'product_id': self.general_product.id,
                'product_uom_qty': 1,
                'price_unit': 90,
            })],
        })
        self.assertTrue(self.wizard._is_fully_imported(order))
