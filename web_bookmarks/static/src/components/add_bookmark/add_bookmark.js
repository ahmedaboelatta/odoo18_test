import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

export class addBookmark extends Component {
    static template = "web_bookmarks.AddBookmark";
    static components = { DropdownItem };
    static props = {};

    addBookmark() {
        rpc("/web_bookmarks/bookmark/add", {
            bookmark: {
                name: window.document.title,
                url: window.location.href,
            }
        });
    }
}

registry.category("cogMenu").add("add-bookmark", { Component: addBookmark }, { sequence: 1 });
