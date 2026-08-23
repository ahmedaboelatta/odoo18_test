/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";

export class BirdInbox extends Component {
    static template = "bird_connector.BirdInbox";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = useState({
            conversations: [], selected: null, channels: [], users: [], teams: [], tags: [], currentUserId: 0, filter: "all", channelId: 0, search: "", teamFilterId: 0, tagFilterId: 0, listsMenu: false, draft: "",
            loading: true, sending: false, attachment: null, attachmentMenu: false, previewMedia: null, dragging: false,
        });
        this.timer = null;
        this.realtimeReloadTimer = null;
        useBus(this.env.bus, "bird-inbox-update", () => this.scheduleRealtimeReload());
        useBus(this.env.bus, "bird-status-update", () => this.scheduleRealtimeReload());
        onMounted(async () => {
            await this.load();
            setTimeout(() => this.scrollBottom(), 0);
            // Bus notifications are the primary realtime path; polling is only a safety fallback.
            this.timer = setInterval(() => this.load(true), 30000);
        });
        onWillUnmount(() => { if (this.timer) clearInterval(this.timer); if (this.realtimeReloadTimer) clearTimeout(this.realtimeReloadTimer); });
    }

    scheduleRealtimeReload() {
        if (this.realtimeReloadTimer) clearTimeout(this.realtimeReloadTimer);
        this.realtimeReloadTimer = setTimeout(() => {
            this.realtimeReloadTimer = null;
            this.load(true);
        }, 150);
    }

    async load(silent=false) {
        if (!silent) this.state.loading = true;
        const wasNearBottom = this.isNearBottom();
        try {
            const data = await this.orm.call(
                "bird.conversation", "inbox_get_data",
                [this.state.filter, this.state.selected?.id || false, 100, this.state.channelId || false, this.state.search || false, this.state.teamFilterId || false, this.state.tagFilterId || false]
            );
            this.state.conversations = data.conversations || [];
            this.state.channels = data.channels || [];
            this.state.users = data.users || [];
            this.state.teams = data.teams || [];
            this.state.tags = data.tags || [];
            this.state.currentUserId = data.current_user_id || 0;
            this.state.selected = data.selected || null;
            if (!silent || wasNearBottom) setTimeout(() => this.scrollBottom(), 0);
        } finally {
            this.state.loading = false;
        }
    }

    async selectConversation(id) {
        const data = await this.orm.call("bird.conversation", "inbox_get_data", [this.state.filter, id, 100, this.state.channelId || false, this.state.search || false, this.state.teamFilterId || false, this.state.tagFilterId || false]);
        this.state.conversations = data.conversations || [];
        this.state.channels = data.channels || [];
        this.state.users = data.users || [];
        this.state.teams = data.teams || [];
        this.state.tags = data.tags || [];
        this.state.currentUserId = data.current_user_id || 0;
        this.state.selected = data.selected || null;
        this.state.draft = "";
        this.clearAttachment();
        this.state.attachmentMenu = false;
        setTimeout(() => this.scrollBottom(), 0);
    }

    async setFilter(filter) {
        this.state.filter = filter;
        this.state.selected = null;
        this.state.attachmentMenu = false;
        this.state.listsMenu = false;
        await this.load();
    }

    async setChannelFilter(ev) {
        const value = parseInt(ev.target.value || "0", 10);
        this.state.channelId = Number.isNaN(value) ? 0 : value;
        this.state.selected = null;
        this.state.attachmentMenu = false;
        await this.load();
    }

    async onSearchInput(ev) {
        this.state.search = ev.target.value || "";
        this.state.selected = null;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.load(true), 250);
    }

    async clearSearch() {
        this.state.search = "";
        this.state.selected = null;
        await this.load();
    }

    toggleListsMenu() {
        this.state.listsMenu = !this.state.listsMenu;
        this.state.attachmentMenu = false;
    }

    async setTeamListFilter(teamId) {
        this.state.teamFilterId = Number(teamId || 0);
        this.state.tagFilterId = 0;
        this.state.selected = null;
        this.state.listsMenu = false;
        await this.load();
    }

    async setTagListFilter(tagId) {
        this.state.tagFilterId = Number(tagId || 0);
        this.state.teamFilterId = 0;
        this.state.selected = null;
        this.state.listsMenu = false;
        await this.load();
    }

    async clearListFilter() {
        this.state.teamFilterId = 0;
        this.state.tagFilterId = 0;
        this.state.selected = null;
        this.state.listsMenu = false;
        await this.load();
    }

    listFilterLabel() {
        if (this.state.teamFilterId) return (this.state.teams || []).find((t) => t.id === this.state.teamFilterId)?.name || "Queue";
        if (this.state.tagFilterId) return (this.state.tags || []).find((t) => t.id === this.state.tagFilterId)?.name || "Tag";
        return "Lists";
    }

    async openListManager() {
        this.state.listsMenu = false;
        await this.action.doAction("bird_connector.action_bird_contact_tag");
    }

    async setTeam(ev) {
        if (!this.state.selected) return;
        const value = parseInt(ev.target.value || "0", 10);
        await this.orm.call("bird.conversation", "inbox_set_team", [this.state.selected.id, value || false]);
        await this.selectConversation(this.state.selected.id);
    }

    eligibleUsers() {
        const selected = this.state.selected;
        if (!selected?.team_id) return this.state.users || [];
        const team = (this.state.teams || []).find((t) => t.id === selected.team_id);
        if (!team) return this.state.users || [];
        const allowed = new Set([...(team.member_ids || []), ...(team.manager_id ? [team.manager_id] : [])]);
        return (this.state.users || []).filter((u) => allowed.has(u.id));
    }

    contactInitials(name) {
        const value = String(name || "").trim();
        if (!value) return "?";
        const words = value.split(/\s+/).filter(Boolean);
        if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
        return `${words[0][0] || ""}${words[words.length - 1][0] || ""}`.toUpperCase();
    }

    tagStyle(tag) {
        const palette = [
            [108,117,125], [240,96,80], [244,164,96], [247,205,31],
            [108,193,237], [129,73,104], [235,126,127], [44,131,151],
            [71,85,119], [214,20,95], [48,195,129], [147,101,184],
        ];
        const rgb = palette[Number(tag?.color || 0) % palette.length];
        return `background-color: rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]}); color: white;`;
    }

    async assignConversation(ev) {
        if (!this.state.selected) return;
        const value = parseInt(ev.target.value || "0", 10);
        await this.orm.call("bird.conversation", "inbox_assign", [this.state.selected.id, value || false]);
        await this.selectConversation(this.state.selected.id);
    }

    async takeConversation() {
        if (!this.state.selected) return;
        await this.orm.call("bird.conversation", "inbox_take", [this.state.selected.id]);
        await this.selectConversation(this.state.selected.id);
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
                    [selectedId, attachment.name, attachment.type, attachment.base64, text, this.state.filter, this.state.channelId || false, this.state.search || false, this.state.teamFilterId || false, this.state.tagFilterId || false]
                );
            } else {
                data = await this.orm.call(
                    "bird.conversation", "inbox_send", [selectedId, text, this.state.filter, this.state.channelId || false, this.state.search || false, this.state.teamFilterId || false, this.state.tagFilterId || false]
                );
            }
            this.state.conversations = data.conversations || [];
            this.state.channels = data.channels || [];
            this.state.users = data.users || [];
            this.state.teams = data.teams || [];
            this.state.tags = data.tags || [];
            this.state.currentUserId = data.current_user_id || 0;
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

    toggleAttachmentMenu() {
        this.state.attachmentMenu = !this.state.attachmentMenu;
    }

    triggerPhoto() {
        this.state.attachmentMenu = false;
        const input = document.querySelector(".o_bird_photo_input");
        if (input) input.click();
    }

    triggerDocument() {
        this.state.attachmentMenu = false;
        const input = document.querySelector(".o_bird_document_input");
        if (input) input.click();
    }

    onDragOver(ev) {
        if (!this.state.selected || this.state.selected.state === "closed") return;
        ev.preventDefault();
        this.state.dragging = true;
    }

    onDragLeave(ev) {
        if (!ev.currentTarget.contains(ev.relatedTarget)) this.state.dragging = false;
    }

    async onDrop(ev) {
        ev.preventDefault();
        this.state.dragging = false;
        if (!this.state.selected || this.state.selected.state === "closed") return;
        const file = ev.dataTransfer?.files?.[0];
        if (file) await this.processAttachmentFile(file);
    }

    async onAttachmentChange(ev) {
        const file = ev.target.files?.[0];
        ev.target.value = "";
        if (!file) return;
        await this.processAttachmentFile(file);
    }

    async processAttachmentFile(file) {
        const allowedDoc = /\.(pdf|doc|docx|xls|xlsx|txt|csv|ppt|pptx)$/i.test(file.name || "");
        if (!file.type?.startsWith("image/") && !allowedDoc) {
            this.notification.add("Drop a photo or supported document (PDF, Office, TXT or CSV).", { type: "warning" });
            return;
        }
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
