from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Remove V6 multi-design UI records after returning to one letterhead."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    legacy_designs = env['invoice.letterhead.design'].search([], order='is_default desc, sequence, id')
    for company in legacy_designs.company_id:
        design = legacy_designs.filtered(lambda item: item.company_id == company)[:1]
        if design and design.letterhead_pdf and not company.invoice_letterhead_pdf:
            company.write({
                'invoice_letterhead_enabled': True,
                'invoice_letterhead_pdf': design.letterhead_pdf,
                'invoice_letterhead_filename': design.letterhead_filename,
                'invoice_letterhead_top_offset': design.top_offset or 35.0,
                'invoice_letterhead_bottom_offset': design.bottom_offset or 20.0,
            })
    legacy_designs.unlink()

    legacy_xmlids = (
        'invoice_company_letterhead.menu_invoice_letterhead_design',
        'invoice_company_letterhead.action_invoice_letterhead_design',
        'invoice_company_letterhead.action_report_invoice_design_preview',
        'invoice_company_letterhead.view_invoice_letterhead_design_form',
        'invoice_company_letterhead.view_invoice_letterhead_design_list',
        'invoice_company_letterhead.view_invoice_print_wizard_form',
        'invoice_company_letterhead.view_move_form_invoice_design',
        'invoice_company_letterhead.access_invoice_letterhead_design_user',
        'invoice_company_letterhead.access_invoice_letterhead_design_manager',
        'invoice_company_letterhead.access_invoice_print_wizard_internal',
        'invoice_company_letterhead.access_invoice_print_wizard_user',
    )
    for xmlid in legacy_xmlids:
        record = env.ref(xmlid, raise_if_not_found=False)
        if record:
            record.unlink()
