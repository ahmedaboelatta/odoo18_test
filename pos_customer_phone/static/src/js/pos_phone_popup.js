/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

export class PosPhonePopup extends Component {
    static template = "pos_customer_phone.PosPhonePopup";

    setup() {
        this.state = useState({ phone: this.props.phone || "" });
    }

    confirm() {
        if (this.props.close) {
            this.props.close(String(this.state.phone || "").trim());
        }
    }

    cancel() {
        if (this.props.close) {
            this.props.close(false);
        }
    }
}
