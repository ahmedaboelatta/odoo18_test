/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";

export class CpanelMailboxListRenderer extends ListRenderer {
    async onCellClicked(record, column, event) {
        if (
            record.selected &&
            column.type === "field" &&
            column.name === "tag_ids"
        ) {
            // Force the standard Odoo multi-save flow for the selected Tags cell.
            this.props.list.model.multiEdit = true;
        }
        return super.onCellClicked(record, column, event);
    }
}

registry.category("views").add("cpanel_mailbox_list", {
    ...listView,
    Renderer: CpanelMailboxListRenderer,
});
