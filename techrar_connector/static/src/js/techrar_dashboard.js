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
            chartType: "bar",
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

    chartHeight(value, type) {
        const values = (this.state.data?.daily_series || []).map((item) => item[type] || 0);
        const maximum = Math.max(...values, 0);
        return maximum ? `${Math.max((value / maximum) * 100, value ? 4 : 0)}%` : "0%";
    }

    setChartType(chartType) {
        this.state.chartType = chartType;
    }

    linePoints(type) {
        const series = this.state.data?.daily_series || [];
        if (!series.length) {
            return "";
        }
        const maximum = Math.max(...series.map((item) => item[type] || 0), 1);
        return series.map((item, index) => {
            const x = series.length === 1 ? 50 : (index / (series.length - 1)) * 100;
            const y = 92 - ((item[type] || 0) / maximum) * 82;
            return `${x},${y}`;
        }).join(" ");
    }

    paymentDonutStyle() {
        const payments = this.state.data?.payments || {};
        const paid = payments.paid || 0;
        const partial = payments.partial || 0;
        const unpaid = (payments.not_paid || 0) + (payments.no_invoice || 0);
        const total = paid + partial + unpaid || 1;
        const paidEnd = (paid / total) * 100;
        const partialEnd = paidEnd + (partial / total) * 100;
        return `background: conic-gradient(#35a86b 0 ${paidEnd}%, #d6a000 ${paidEnd}% ${partialEnd}%, #dc3545 ${partialEnd}% 100%)`;
    }

    webhookDonutStyle() {
        const queue = this.state.data?.queue || {};
        const done = queue.done || 0;
        const failed = queue.failed || 0;
        const total = done + failed || 1;
        const doneEnd = (done / total) * 100;
        return `background: conic-gradient(#35a86b 0 ${doneEnd}%, #dc3545 ${doneEnd}% 100%)`;
    }

    formatTrend(value) {
        if (value === null || value === undefined) {
            return "New";
        }
        const prefix = value > 0 ? "+" : "";
        return `${prefix}${value}%`;
    }

    trendClass(value) {
        if (value === null || value > 0) {
            return "o_techrar_trend_up";
        }
        if (value < 0) {
            return "o_techrar_trend_down";
        }
        return "o_techrar_trend_flat";
    }

    openOrder(orderId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "sale.order",
            res_id: orderId,
            views: [[false, "form"]],
        });
    }

    openWebhook(eventId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "techrar.webhook.event",
            res_id: eventId,
            views: [[false, "form"]],
        });
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
        const domain = [...(this.state.data.queue_date_domain || [])];
        if (state) {
            domain.push(["state", "=", state]);
        }
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
