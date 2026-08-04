/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { PosPhonePopup } from "./pos_phone_popup";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const dialog = this.dialog || this.env?.services?.dialog;
        if (dialog) {
            try {
                const phone = await dialog.add(PosPhonePopup, {
                    title: "رقم جوال العميل / Customer Phone",
                });

                if (phone) {
                    this.currentOrder.customer_phone = phone;
                }
            } catch (e) {
                console.warn("PosCustomerPhone: dialog add failed", e);
            }
        }

        return super.validateOrder(...arguments);
    }
});
