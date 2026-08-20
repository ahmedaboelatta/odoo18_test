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
            loading: true, sending: false, attachment: null, previewMedia: null,
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
        this.clearAttachment();
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
        const attachment = this.state.attachment;
        if ((!text && !attachment) || !this.state.selected || this.state.sending) return;

        const selectedId = this.state.selected.id;
        const optimistic = {
            id: `pending-${Date.now()}`,
            direction: "outbound",
            type: attachment ? (attachment.type.startsWith("image/") ? "image" : "file") : "text",
            body: text || (attachment?.type.startsWith("image/") ? "[Image]" : `[Document] ${attachment?.name || ""}`),
            caption: text,
            media_url: attachment?.preview || "",
            media_name: attachment?.name || "",
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
            let data;
            if (attachment) {
                data = await this.orm.call(
                    "bird.conversation", "inbox_send_media",
                    [selectedId, attachment.name, attachment.type, attachment.base64, text, this.state.filter, this.state.channelId || false]
                );
            } else {
                data = await this.orm.call(
                    "bird.conversation", "inbox_send", [selectedId, text, this.state.filter, this.state.channelId || false]
                );
            }
            this.state.conversations = data.conversations || [];
            this.state.channels = data.channels || [];
            this.state.selected = data.selected || null;
            this.clearAttachment();
            setTimeout(() => this.scrollBottom(), 0);
        } catch (e) {
            this.notification.add(e.message || "Could not send message", { type: "danger" });
            await this.selectConversation(selectedId);
        } finally {
            this.state.sending = false;
        }
    }

    triggerAttach() {
        const input = document.querySelector(".o_bird_attachment_input");
        if (input) input.click();
    }

    async onAttachmentChange(ev) {
        const file = ev.target.files?.[0];
        ev.target.value = "";
        if (!file) return;
        const maxBytes = 16 * 1024 * 1024;
        if (file.size > maxBytes) {
            this.notification.add("Attachments are limited to 16 MB.", { type: "warning" });
            return;
        }
        try {
            const dataUrl = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            const base64 = String(dataUrl || "").split(",", 2)[1] || "";
            if (!base64) throw new Error("Could not read file");
            this.clearAttachment();
            this.state.attachment = {
                name: file.name,
                type: file.type || "application/octet-stream",
                size: file.size,
                base64,
                preview: file.type?.startsWith("image/") ? String(dataUrl) : "",
            };
        } catch (e) {
            this.notification.add("Could not read the selected file.", { type: "danger" });
        }
    }

    clearAttachment() {
        this.state.attachment = null;
    }

    openMedia(msg) {
        if (msg?.media_url) this.state.previewMedia = msg;
    }

    closeMedia() {
        this.state.previewMedia = null;
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
