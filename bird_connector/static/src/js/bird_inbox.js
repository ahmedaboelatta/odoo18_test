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
            conversations: [], selected: null, channels: [], users: [], teams: [], tags: [], closedCount: 0, currentUserId: 0, filter: "all", channelId: 0, search: "", teamFilterId: 0, tagFilterId: 0, listsMenu: false, draft: "",
            loading: true, sending: false, attachment: null, attachmentMenu: false, previewMedia: null, dragging: false,
            quickReplies: [], quickReplyMenu: false, quickReplySearch: "", msgActionsId: null,
        });
        this.timer = null;
        this.realtimeReloadTimer = null;

        // Close Inbox popovers when the user clicks anywhere outside them.
        // Using capture mode makes this reliable even inside nested Odoo/OWL elements.
        this._onDocumentPointerDown = (ev) => {
            const target = ev.target;
            if (!(target instanceof Element)) return;

            if (
                this.state.quickReplyMenu &&
                !target.closest(".o_bird_quick_reply_picker") &&
                !target.closest(".o_bird_plus_btn")
            ) {
                this.closeQuickReplies();
            }

            if (
                this.state.attachmentMenu &&
                !target.closest(".o_bird_attach_menu_wrap")
            ) {
                this.state.attachmentMenu = false;
            }

            if (
                this.state.listsMenu &&
                !target.closest(".o_bird_lists_wrap")
            ) {
                this.state.listsMenu = false;
            }

            if (
                this.state.msgActionsId &&
                !target.closest(".o_bird_msg_actions_wrap")
            ) {
                this.closeMessageActions();
            }
        };
        useBus(this.env.bus, "bird-inbox-update", () => this.scheduleRealtimeReload());
        useBus(this.env.bus, "bird-status-update", () => this.scheduleRealtimeReload());
        onMounted(async () => {
            document.addEventListener("pointerdown", this._onDocumentPointerDown, true);
            await this.load();
            setTimeout(() => this.scrollBottom(), 0);
            // Bus notifications are the primary realtime path; polling is only a safety fallback.
            this.timer = setInterval(() => this.load(true), 30000);
        });
        onWillUnmount(() => {
            document.removeEventListener("pointerdown", this._onDocumentPointerDown, true);
            if (this.timer) clearInterval(this.timer);
            if (this.realtimeReloadTimer) clearTimeout(this.realtimeReloadTimer);
        });
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
            this.state.closedCount = data.closed_count || 0;
            this.state.currentUserId = data.current_user_id || 0;
            this.state.quickReplies = data.quick_replies || [];
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
        this.state.closedCount = data.closed_count || 0;
        this.state.currentUserId = data.current_user_id || 0;
        this.state.quickReplies = data.quick_replies || [];
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


    async toggleClosedListFilter() {
        // WhatsApp-style list behavior: clicking Closed again clears it.
        this.state.filter = this.state.filter === "closed" ? "all" : "closed";
        this.state.selected = null;
        this.state.attachmentMenu = false;
        this.state.listsMenu = false;
        await this.load();
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
        // "All conversations" is a real reset, not only a team/tag reset.
        this.state.filter = "all";
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
        // Conversation titles may contain the WhatsApp number, e.g.
        // "Ahmed Abo EL-Atta (+966...)" or "(+966...) محمد صالح".
        // WhatsApp-style avatars should use name initials only, never digits or parentheses.
        const raw = String(name || "").trim();
        if (!raw) return "?";

        const cleaned = raw
            .replace(/\([^)]*\d[^)]*\)/g, " ")
            .replace(/\+?\d[\d\s().-]{5,}/g, " ")
            .replace(/[()]+/g, " ")
            .replace(/\s+/g, " ")
            .trim();

        const words = cleaned
            .split(/\s+/)
            .map((word) => (word.match(/[\p{L}]+/gu) || []).join(""))
            .filter(Boolean);

        if (!words.length) return "?";
        if (words.length === 1) {
            return Array.from(words[0]).slice(0, 2).join("").toUpperCase();
        }
        const first = Array.from(words[0])[0] || "";
        const last = Array.from(words[words.length - 1])[0] || "";
        return `${first}${last}`.toUpperCase();
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
            this.state.closedCount = data.closed_count || 0;
            this.state.currentUserId = data.current_user_id || 0;
            this.state.quickReplies = data.quick_replies || [];
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
        this.state.quickReplyMenu = false;
        this.state.msgActionsId = null;
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

    openQuickReplies() {
        this.state.attachmentMenu = false;
        this.state.quickReplySearch = "";
        this.state.quickReplyMenu = true;
    }

    closeQuickReplies() {
        this.state.quickReplyMenu = false;
        this.state.quickReplySearch = "";
    }

    onComposerInput(ev) {
        this.state.draft = ev.target.value || "";
        const trimmed = this.state.draft.trimStart();
        if (trimmed.startsWith("/")) {
            this.state.quickReplySearch = trimmed.slice(1);
            this.state.quickReplyMenu = true;
            this.state.attachmentMenu = false;
        } else if (this.state.quickReplyMenu && this.state.quickReplySearch !== "") {
            this.closeQuickReplies();
        }
    }

    filteredQuickReplies() {
        const q = String(this.state.quickReplySearch || "").trim().toLowerCase();
        const rows = this.state.quickReplies || [];
        if (!q) return rows;
        return rows.filter((r) =>
            String(r.name || "").toLowerCase().includes(q) ||
            String(r.shortcut || "").toLowerCase().includes(q) ||
            String(r.message || "").toLowerCase().includes(q)
        );
    }

    useQuickReply(reply) {
        if (!reply) return;
        this.state.draft = reply.message || "";
        this.closeQuickReplies();
        setTimeout(() => {
            const el = document.querySelector(".o_bird_composer_textarea");
            if (el) {
                el.focus();
                el.selectionStart = el.selectionEnd = el.value.length;
            }
        }, 0);
    }

    async openQuickReplyManager() {
        this.closeQuickReplies();
        await this.action.doAction("bird_connector.action_bird_quick_reply");
    }

    toggleMessageActions(msgId) {
        this.state.msgActionsId = this.state.msgActionsId === msgId ? null : msgId;
    }

    closeMessageActions() {
        this.state.msgActionsId = null;
    }

    async copyMessageText(msg) {
        const text = String(msg?.body || msg?.caption || "");
        if (!text) {
            this.notification.add("There is no text to copy.", { type: "warning" });
            this.closeMessageActions();
            return;
        }
        let copied = false;
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
                copied = true;
            }
        } catch {
            copied = false;
        }
        if (!copied) {
            try {
                const textarea = document.createElement("textarea");
                textarea.value = text;
                textarea.setAttribute("readonly", "");
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";
                textarea.style.pointerEvents = "none";
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                copied = document.execCommand("copy");
                textarea.remove();
            } catch {
                copied = false;
            }
        }
        this.notification.add(
            copied ? "Copied." : "Could not copy this message.",
            { type: copied ? "success" : "warning" }
        );
        this.closeMessageActions();
    }

    async copyImage(msg) {
        if (!msg?.media_url) return;

        let copied = false;
        let objectUrl = null;

        try {
            const response = await fetch(msg.media_url, {
                credentials: "same-origin",
                cache: "force-cache",
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const originalBlob = await response.blob();
            let pngBlob = originalBlob;

            // Chromium is most reliable when clipboard image data is PNG.
            if ((originalBlob.type || "").toLowerCase() !== "image/png") {
                const bitmap = await createImageBitmap(originalBlob);
                const canvas = document.createElement("canvas");
                canvas.width = bitmap.width;
                canvas.height = bitmap.height;
                const ctx = canvas.getContext("2d");
                ctx.drawImage(bitmap, 0, 0);
                bitmap.close?.();
                pngBlob = await new Promise((resolve, reject) => {
                    canvas.toBlob(
                        (blob) => blob ? resolve(blob) : reject(new Error("PNG conversion failed")),
                        "image/png"
                    );
                });
            }

            // Primary modern Clipboard API path.
            try {
                if (navigator.clipboard && typeof ClipboardItem !== "undefined" && window.isSecureContext) {
                    await navigator.clipboard.write([
                        new ClipboardItem({ "image/png": pngBlob })
                    ]);
                    copied = true;
                }
            } catch {
                copied = false;
            }

            // Fallback for browsers that deny ClipboardItem image writes.
            // Copy a real <img> selection as rich clipboard content.
            if (!copied) {
                objectUrl = URL.createObjectURL(pngBlob);
                const holder = document.createElement("div");
                holder.contentEditable = "true";
                holder.style.position = "fixed";
                holder.style.left = "-10000px";
                holder.style.top = "0";
                holder.style.opacity = "0";
                const img = document.createElement("img");
                img.src = objectUrl;
                holder.appendChild(img);
                document.body.appendChild(holder);

                await new Promise((resolve, reject) => {
                    if (img.complete) resolve();
                    else {
                        img.onload = resolve;
                        img.onerror = reject;
                    }
                });

                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNode(img);
                selection.removeAllRanges();
                selection.addRange(range);
                copied = document.execCommand("copy");
                selection.removeAllRanges();
                holder.remove();
            }
        } catch {
            copied = false;
        } finally {
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        }

        this.notification.add(
            copied
                ? "Image copied."
                : "This browser blocked image copying. Download is still available.",
            { type: copied ? "success" : "warning" }
        );
        this.closeMessageActions();
    }

    downloadMedia(msg) {
        if (!msg?.media_url) return;

        const separator = msg.media_url.includes("?") ? "&" : "?";
        const url = `${msg.media_url}${separator}download=1`;

        // A real anchor click respects Content-Disposition: attachment.
        // Hidden iframes can render the response instead of triggering a browser download.
        const link = document.createElement("a");
        link.href = url;
        link.download = msg.media_name || "";
        link.target = "_self";
        link.rel = "noopener";
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        setTimeout(() => link.remove(), 1000);

        this.closeMessageActions();
    }

    onKeydown(ev) {
        if (ev.key === "Escape") {
            this.closeQuickReplies();
            this.state.attachmentMenu = false;
            this.closeMessageActions();
            return;
        }
        if (ev.key === "Enter" && !ev.shiftKey && !this.state.quickReplyMenu) {
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
