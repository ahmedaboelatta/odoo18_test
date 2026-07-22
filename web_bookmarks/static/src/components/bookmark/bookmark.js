import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted } from "@odoo/owl";
import { Deferred } from "@web/core/utils/concurrency";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";

export class Bookmark extends Component {
    static template = "web_bookmarks.Bookmark";
    static components = { Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.action = useService("action");
        this.dropdown = useDropdownState();
        this.fetchDeferred = new Deferred();
        this.bookmarks = [];

        onMounted(() => {
            this.fetchBookmarks();
        });
    }

    openMyBookmarks() {
        this.dropdown.close();
        this.action.doAction("web_bookmarks.bookmark_action_my_bookmarks", { clearBreadcrumbs: true });
    }

    openBookmark(bookmark) {
        window.open(bookmark.url, bookmark.target);
    }

    onBeforeOpen() {
        const fetchDeferred = this.fetchDeferred;
        this.fetchBookmarks();
        return fetchDeferred;
    }

    async fetchBookmarks() {
        const fetchDeferred = this.fetchDeferred;
        try {
            const result = await rpc("/web_bookmarks/bookmark");
            this.bookmarks = result;
            fetchDeferred.resolve(result);
        } catch (error) {
            fetchDeferred.reject(error);
        }
        this.fetchDeferred = new Deferred();
    }
}

registry.category("systray").add("web_bookmarks.bookmark", { Component: Bookmark }, { sequence: 10 });
