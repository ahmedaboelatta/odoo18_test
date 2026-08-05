/** @odoo-module **/

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        if (this.state) {
            this.state.customerPhone = this.currentOrder?.customer_phone || "";
        }
    },

    saveCustomerPhone() {
        const phone = String(this.state?.customerPhone || "").trim();
        if (!phone) {
            return;
        }
        if (this.currentOrder) {
            this.currentOrder.customer_phone = phone;
        }
    },
});
