/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";

export class BirdInbox extends Component {
    static template = "bird_connector.BirdInbox";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            conversations: [], selected: null, channels: [], filter: "all", channelId: 0, draft: "",
            loading: true, sending: false,
        });
        this.timer = null;
        onMounted(async () => {
            await this.load();
            setTimeout(() => this.scrollBottom(), 0);
            this.timer = setInterval(() => this.load(true), 5000);
        });
        onWillUnmount(() => { if (this.timer) clearInterval(this.timer); });
    }

    async load(silent=false) {
        if (!silent) this.state.loading = true;
        const wasNearBottom = this.isNearBottom();
        try {
            const data = await this.orm.call(
                "bird.conversation", "inbox_get_data",
                [this.state.filter, this.state.selected?.id || false, 100, this.state.channelId || false]
            );
            this.state.conversations = data.conversations || [];
            this.state.channels = data.channels || [];
            this.state.selected = data.selected || null;
            if (!silent || wasNearBottom) setTimeout(() => this.scrollBottom(), 0);
        } finally {
            this.state.loading = false;
        }
    }

    async selectConversation(id) {
        const data = await this.orm.call("bird.conversation", "inbox_get_data", [this.state.filter, id, 100, this.state.channelId || false]);
        this.state.conversations = data.conversations || [];
        this.state.channels = data.channels || [];
        this.state.selected = data.selected || null;
        this.state.draft = "";
        setTimeout(() => this.scrollBottom(), 0);
    }

    async setFilter(filter) {
        this.state.filter = filter;
        this.state.selected = null;
        await this.load();
    }

    async setChannelFilter(ev) {
        const value = parseInt(ev.target.value || "0", 10);
        this.state.channelId = Number.isNaN(value) ? 0 : value;
        this.state.selected = null;
        await this.load();
    }

    async send() {
        const text = (this.state.draft || "").trim();
        if (!text || !this.state.selected || this.state.sending) return;

        const selectedId = this.state.selected.id;
        const optimistic = {
            id: `pending-${Date.now()}`,
            direction: "outbound",
            type: "text",
            body: text,
            status: "sending…",
            message_at: new Date().toISOString().slice(0, 19).replace("T", " "),
            sent_by: "You",
            pending: true,
        };
        this.state.selected.messages.push(optimistic);
        this.state.draft = "";
        this.state.selected.needs_reply = false;
        setTimeout(() => this.scrollBottom(), 0);

        this.state.sending = true;
        try {
            const data = await this.orm.call(
                "bird.conversation", "inbox_send", [selectedId, text, this.state.filter, this.state.channelId || false]
            );
            this.state.conversations = data.conversations || [];
            this.state.channels = data.channels || [];
            this.state.selected = data.selected || null;
            setTimeout(() => this.scrollBottom(), 0);
        } catch (e) {
            this.notification.add(e.message || "Could not send message", { type: "danger" });
            await this.selectConversation(selectedId);
        } finally {
            this.state.sending = false;
        }
    }

    async toggleState() {
        if (!this.state.selected) return;
        const next = this.state.selected.state === "closed" ? "open" : "closed";
        await this.orm.call("bird.conversation", "inbox_set_state", [this.state.selected.id, next]);
        this.state.selected = null;
        await this.load();
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    scrollBottom() {
        const el = document.querySelector(".o_bird_inbox_messages");
        if (el) el.scrollTop = el.scrollHeight;
    }

    isNearBottom() {
        const el = document.querySelector(".o_bird_inbox_messages");
        return !el || (el.scrollHeight - el.scrollTop - el.clientHeight) < 100;
    }

    _parseDate(value) {
        if (!value) return null;
        // Odoo RPC datetime strings are UTC without a timezone suffix.
        const parsed = new Date(value.replace(" ", "T") + (value.includes("Z") ? "" : "Z"));
        return Number.isNaN(parsed.getTime()) ? null : parsed;
    }

    formatTime(value) {
        const date = this._parseDate(value);
        if (!date) return "";
        const now = new Date();
        const sameDay = date.toDateString() === now.toDateString();
        const yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);
        const time = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
        if (sameDay) return time;
        if (date.toDateString() === yesterday.toDateString()) return `Yesterday ${time}`;
        return new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", hour: "numeric", minute: "2-digit" }).format(date);
    }

    statusLabel(status) {
        const value = (status || "").toLowerCase();
        if (!value) return "";
        return value.replaceAll("_", " ");
    }

    onMediaError(ev) {
        const img = ev.currentTarget;
        if (img && !img.dataset.birdMediaFailed) {
            img.dataset.birdMediaFailed = "1";
            img.style.display = "none";
            this.notification.add("Could not load this Bird media item.", { type: "warning" });
        }
    }

    fileLabel(msg) {
        return msg.media_name || msg.caption || msg.body || "Open document";
    }
}

registry.category("actions").add("bird_connector.inbox", BirdInbox);
