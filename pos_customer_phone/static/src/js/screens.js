/** @odoo-module **/

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.customerPhone = useState(this.currentOrder?.customer_phone || "");
    },

    saveCustomerPhone() {
        const phone = String(this.customerPhone || "").trim();
        if (!phone) {
            return;
        }
        if (this.currentOrder) {
            this.currentOrder.customer_phone = phone;
        }
    },
});
