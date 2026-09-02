/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

patch(ListRenderer.prototype, {
    async onCellClicked(record, column, event) {
        if (
            record.resModel === "cpanel.mailbox" &&
            record.selected &&
            column.type === "field" &&
            column.name === "tag_ids"
        ) {
            // Some list/action combinations do not propagate multi_edit to the
            // relational model. Force it only for the selected mailbox Tags cell
            // so the standard Odoo multi-save confirmation remains in charge.
            this.props.list.model.multiEdit = true;
        }
        return super.onCellClicked(record, column, event);
    },
});
