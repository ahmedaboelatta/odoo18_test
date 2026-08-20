/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";

export class BirdInbox extends Component {
    static template = "bird_connector.BirdInbox";
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ conversations: [], selected: null, filter: "all", draft: "", loading: true, sending: false });
        this.timer = null;
        onMounted(async () => {
            await this.load();
            this.timer = setInterval(() => this.load(true), 5000);
        });
        onWillUnmount(() => { if (this.timer) clearInterval(this.timer); });
    }
    async load(silent=false) {
        if (!silent) this.state.loading = true;
        try {
            const data = await this.orm.call("bird.conversation", "inbox_get_data", [this.state.filter, this.state.selected?.id || false, 100]);
            this.state.conversations = data.conversations || [];
            this.state.selected = data.selected || null;
        } finally { this.state.loading = false; }
    }
    async selectConversation(id) {
        const data = await this.orm.call("bird.conversation", "inbox_get_data", [this.state.filter, id, 100]);
        this.state.conversations = data.conversations || [];
        this.state.selected = data.selected || null;
        this.state.draft = "";
        setTimeout(() => this.scrollBottom(), 0);
    }
    async setFilter(filter) { this.state.filter = filter; this.state.selected = null; await this.load(); }
    async send() {
        const text = (this.state.draft || "").trim();
        if (!text || !this.state.selected || this.state.sending) return;
        this.state.sending = true;
        try {
            const data = await this.orm.call("bird.conversation", "inbox_send", [this.state.selected.id, text]);
            this.state.draft = "";
            this.state.conversations = data.conversations || [];
            this.state.selected = data.selected || null;
            setTimeout(() => this.scrollBottom(), 0);
        } catch (e) { this.notification.add(e.message || "Could not send message", { type: "danger" }); }
        finally { this.state.sending = false; }
    }
    async toggleState() {
        if (!this.state.selected) return;
        const next = this.state.selected.state === "closed" ? "open" : "closed";
        await this.orm.call("bird.conversation", "inbox_set_state", [this.state.selected.id, next]);
        await this.load();
    }
    onKeydown(ev) { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); this.send(); } }
    scrollBottom() { const el = document.querySelector('.o_bird_inbox_messages'); if (el) el.scrollTop = el.scrollHeight; }
    formatTime(value) { return value ? value.replace(' ', ' · ').slice(0,16) : ''; }
}
registry.category("actions").add("bird_connector.inbox", BirdInbox);
