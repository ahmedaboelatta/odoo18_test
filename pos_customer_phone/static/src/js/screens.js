/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { PosPhonePopup } from "./pos_phone_popup";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const popupService = this.env.services.popup;

        if (popupService) {
            const { confirmed, payload } = await popupService.add(PosPhonePopup, {
                title: "رقم جوال العميل / Customer Phone",
            });

            if (confirmed && payload) {
                this.currentOrder.customer_phone = payload;
            }
        }

        return super.validateOrder(...arguments);
    }
});
