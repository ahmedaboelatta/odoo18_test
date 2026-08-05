/** @odoo-module **/

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        if (this.state) {
            this.state.customerPhone = this.currentOrder?.customer_phone || "";
        }
    },

    // 1. تنظيف الحقل فورياً لمنع الحروف وتقييده بـ 10 أرقام كحد أقصى
    onPhoneInput(ev) {
        const cleaned = ev.target.value.replace(/\D/g, "").slice(0, 10);
        if (this.state) {
            this.state.customerPhone = cleaned;
        }
        ev.target.value = cleaned;
    },

    async onSavePhone() {
        const raw = String(this.state?.customerPhone || "").trim();
        if (!raw) {
            return;
        }

        const currentOrder = this.currentOrder;
        if (!currentOrder) {
            return;
        }

        let normalized = raw;
        const digits = raw.replace(/\D/g, "");
        if (digits.startsWith("05")) {
            normalized = "+966" + digits.slice(1);
        } else if (digits.startsWith("009665")) {
            normalized = "+" + digits.slice(2);
        } else if (digits.startsWith("9665")) {
            normalized = "+966" + digits.slice(3);
        } else if (!digits.startsWith("+") && digits.startsWith("5")) {
            normalized = "+966" + digits;
        }

        currentOrder.customer_phone = normalized;

        const backendId = currentOrder.backendId || currentOrder.server_id || currentOrder.id;
        if (backendId && this.orm) {
            try {
                await this.orm.write("pos.order", [backendId], {
                    customer_phone: normalized,
                });
                this.notification?.add?.("تم حفظ رقم الجوال بنجاح", { type: "success" });
            } catch (e) {
                console.warn("PosCustomerPhone: failed to save phone", e);
                this.notification?.add?.("حدث خطأ أثناء حفظ الرقم", { type: "danger" });
            }
        }
    },
});