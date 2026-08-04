import { patch } from "@web/core/utils/patch";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { useState } from "@odoo/owl";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.phonePopupVisible = useState(false);
        this.phoneInput = "";
    },

    openPhonePopup() {
        this.phoneInput = this.currentOrder?.customer_phone || "";
        this.phonePopupVisible = true;
    },

    closePhonePopup() {
        this.phonePopupVisible = false;
    },

    saveCustomerPhone() {
        const phone = this.phoneInput.trim();
        if (!phone) {
            this.closePhonePopup();
            return;
        }
        if (this.currentOrder) {
            this.currentOrder.customer_phone = phone;
        }
        this.closePhonePopup();
    },
});

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        this.customer_phone = vals.customer_phone || "";
    },
});
