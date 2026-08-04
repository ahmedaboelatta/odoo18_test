/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { PosPhonePopup } from "./pos_phone_popup";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        // Trigger phone popup before finalizing validation
        const { confirmed, payload } = await this.popup.add(PosPhonePopup, {
            title: "Customer Phone Number / رقم جوال العميل",
        });

        if (confirmed && payload) {
            this.currentOrder.customer_phone = payload;
        }

        return super.validateOrder(...arguments);
    }
});