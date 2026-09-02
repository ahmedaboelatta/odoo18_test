/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import {
    Many2ManyTagsField,
    many2ManyTagsField,
} from "@web/views/fields/many2many_tags/many2many_tags_field";

export class CpanelMailboxTagsField extends Many2ManyTagsField {
    static template = "cpanel_manager.MailboxTagsField";

    async onMailboxTagClick(event) {
        if (!this.props.readonly || !this.props.record.selected) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        this.props.record.model.multiEdit = true;
        await this.props.record.model.root.enterEditMode(this.props.record);
    }
}

registry.category("fields").add("cpanel_mailbox_tags", {
    ...many2ManyTagsField,
    component: CpanelMailboxTagsField,
});

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
