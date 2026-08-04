import { patch } from "@web/core/utils/patch";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosPhonePopup } from "pos_customer_phone.PosPhonePopup";

patch(ReceiptScreen.prototype, {
    openPhonePopup() {
        const order = this.currentOrder;
        const currentPhone = order && order.customer_phone ? String(order.customer_phone) : "";
        this.showPopup(PosPhonePopup, {
            phone: currentPhone,
        }).then((phone) => {
            if (phone) {
                this.currentOrder.customer_phone = phone;
            }
        });
    },
});

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        const phone = vals.customer_phone;
        this.customer_phone = phone ? String(phone) : "";
    },
});
