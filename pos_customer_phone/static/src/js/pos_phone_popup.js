/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

export class PosPhonePopup extends Component {
    static template = "pos_customer_phone.PosPhonePopup";

    setup() {
        this.state = useState({ phone: this.props.phone || "" });
    }

    confirm() {
        this.props.resolve(String(this.state.phone || "").trim());
    }

    cancel() {
        this.props.resolve(false);
    }
}
