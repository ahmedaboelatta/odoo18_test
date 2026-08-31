def migrate(cr, version):
    """Remove obsolete Product Mapping UI/access records from prior versions."""
    obsolete_xmlids = (
        'techrar_product_mapping_menu',
        'action_techrar_product_mapping',
        'view_techrar_product_mapping_list',
        'view_techrar_product_mapping_form',
        'access_techrar_mapping_manager',
        'access_techrar_mapping_user',
    )
    cr.execute(
        """
        SELECT model, res_id
          FROM ir_model_data
         WHERE module = 'techrar_connector'
           AND name IN %s
        """,
        [obsolete_xmlids],
    )
    model_tables = {
        'ir.ui.menu': 'ir_ui_menu',
        'ir.actions.act_window': 'ir_act_window',
        'ir.ui.view': 'ir_ui_view',
        'ir.model.access': 'ir_model_access',
    }
    for model, res_id in cr.fetchall():
        table = model_tables.get(model)
        if table:
            cr.execute(f'DELETE FROM {table} WHERE id = %s', [res_id])
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'techrar_connector'
           AND name IN %s
        """,
        [obsolete_xmlids],
    )
