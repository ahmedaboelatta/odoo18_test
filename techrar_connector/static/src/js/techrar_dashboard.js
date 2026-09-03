/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class TechrarDashboard extends Component {
    static template = "techrar_connector.TechrarDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: false,
            data: null,
            fromDate: "",
            toDate: "",
        });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call(
                "sale.order",
                "get_techrar_dashboard_data",
                [],
                {
                    from_date: this.state.fromDate || false,
                    to_date: this.state.toDate || false,
                },
            );
            this.state.data = data;
            this.state.fromDate = data.from_date;
            this.state.toDate = data.to_date;
        } catch (error) {
            this.state.error = error.message || "Could not load dashboard data.";
        } finally {
            this.state.loading = false;
        }
    }

    applyDateFilter() {
        if (this.state.fromDate && this.state.toDate && this.state.fromDate > this.state.toDate) {
            this.state.error = "From Date cannot be later than To Date.";
            return;
        }
        return this.loadData();
    }

    showToday() {
        const today = new Date();
        const localToday = [
            today.getFullYear(),
            String(today.getMonth() + 1).padStart(2, "0"),
            String(today.getDate()).padStart(2, "0"),
        ].join("-");
        this.state.fromDate = localToday;
        this.state.toDate = localToday;
        return this.loadData();
    }

    formatMoney(value) {
        const currency = this.state.data?.currency || "SAR";
        return new Intl.NumberFormat(undefined, {
            style: "currency",
            currency,
            maximumFractionDigits: 2,
        }).format(value || 0);
    }

    openOrders(paymentState = false) {
        const domain = [...this.state.data.date_domain];
        if (paymentState) {
            domain.push(["techrar_payment_state", "=", paymentState]);
        }
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: "Techrar Orders",
            res_model: "sale.order",
            views: [[false, "list"], [false, "form"]],
            domain,
        });
    }

    openQueue(state = false) {
        const domain = state ? [["state", "=", state]] : [];
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: "Webhook Queue",
            res_model: "techrar.webhook.event",
            views: [[false, "list"], [false, "form"]],
            domain,
            context: { techrar_force_latest_webhooks: true },
        });
    }
}

registry.category("actions").add("techrar_connector.dashboard", TechrarDashboard);
