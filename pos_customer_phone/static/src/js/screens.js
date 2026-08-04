import { patch } from "@web/core/utils/patch";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { useState } from "@odoo/owl";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.posCustomerPhonePopupVisible = useState(false);
        this.posCustomerPhoneInput = useState("");
    },

    openPhonePopup() {
        const order = this.currentOrder;
        const currentPhone = order && order.customer_phone ? String(order.customer_phone) : "";
        this.posCustomerPhoneInput = useState(currentPhone);
        this.posCustomerPhonePopupVisible = true;
    },

    closePhonePopup() {
        this.posCustomerPhonePopupVisible = false;
    },

    saveCustomerPhone() {
        const phone = String(this.posCustomerPhoneInput || "").trim();
        if (!phone) {
            this.closePhonePopup();
            return;
        }
        const order = this.currentOrder;
        if (order) {
            order.customer_phone = phone;
        }
        this.closePhonePopup();
    },
});

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        const phone = vals.customer_phone;
        this.customer_phone = phone ? String(phone) : "";
    },
});
