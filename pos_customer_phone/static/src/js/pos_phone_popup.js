/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { useState } from "@odoo/owl";

export class PosPhonePopup extends AbstractAwaitablePopup {
    static template = "pos_customer_phone.PosPhonePopup";
    static defaultProps = {
        confirmText: "Save / حفظ",
        cancelText: "Skip / تخطي",
        title: "Customer Phone Number",
    };

    setup() {
        super.setup();
        this.state = useState({ phone: "" });
    }

    getPayload() {
        return this.state.phone;
    }
}