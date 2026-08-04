/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { PosPhonePopup } from "./pos_phone_popup";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        // Show popup to capture phone before confirming payment
        const { confirmed, payload } = await this.popup.add(PosPhonePopup, {
            title: "رقم جوال العميل / Customer Phone",
        });

        if (confirmed && payload) {
            this.currentOrder.customer_phone = payload;
        }

        return super.validateOrder(...arguments);
    }
});