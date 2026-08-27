from odoo import fields


def post_init_hook(env):
    """Migrate the legacy configuration and product links without deleting data."""
    Config = env['techrar.config'].sudo()
    if not Config.search([], limit=1):
        params = env['ir.config_parameter'].sudo()
        token = params.get_param('techrar.api_token')
        if token:
            Config.create({
                'name': 'Techrar Main',
                'techrar_api_url': params.get_param('techrar.api_base_url', 'https://api.techrar.com'),
                'techrar_api_token': token,
                'techrar_app_id': params.get_param('techrar.app_id', '3'),
            })

    Mapping = env['techrar.product.mapping'].sudo()
    templates = env['product.template'].sudo().search([
        ('techrar_subs_id', '!=', False), ('is_techrar_subscription', '=', True)
    ], order='id')
    for template in templates:
        external_id = str(template.techrar_subs_id).strip()
        if not external_id or Mapping.search_count([('techrar_external_id', '=', external_id)]):
            continue
        Mapping.create({
            'techrar_external_id': external_id,
            'techrar_name': template.name,
            'product_id': template.product_variant_id.id,
            'last_seen_at': fields.Datetime.now(),
        })
