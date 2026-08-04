import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { useState } from "@odoo/owl";

export class PosPhonePopup extends AbstractAwaitablePopup {
    static template = "pos_customer_phone.PosPhonePopup";

    setup() {
        super.setup();
        this.state = useState({ phone: this.props.phone || "" });
    }

    confirm() {
        this.props.resolve(String(this.state.phone || "").trim());
    }
}
