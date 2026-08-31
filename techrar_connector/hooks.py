def post_init_hook(env):
    """Migrate the legacy configuration without deleting existing data."""
    Config = env['techrar.config'].sudo()
    if not Config.with_context(active_test=False).search([], limit=1):
        params = env['ir.config_parameter'].sudo()
        token = params.get_param('techrar.api_token')
        if token:
            Config.create({
                'name': 'Techrar Main',
                'techrar_api_url': params.get_param('techrar.api_base_url', 'https://api.techrar.com'),
                'techrar_api_token': token,
                'techrar_app_id': params.get_param('techrar.app_id', '3'),
            })
