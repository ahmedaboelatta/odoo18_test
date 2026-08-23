/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class BirdCampaignDashboard extends Component {
    static template = "bird_connector.BirdCampaignDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, period: "30", data: {} });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("bird.bulk.send", "campaign_dashboard_data", [this.state.period]);
        } finally {
            this.state.loading = false;
        }
    }

    async setPeriod(ev) {
        this.state.period = ev.target.value;
        await this.load();
    }

    openCampaigns(domain = []) {
        this.action.doAction({ type: "ir.actions.act_window", name: "Bulk Sends", res_model: "bird.bulk.send", views: [[false, "list"], [false, "form"]], domain });
    }

    openRecipients(domain = []) {
        this.action.doAction({ type: "ir.actions.act_window", name: "Campaign Analytics", res_model: "bird.bulk.send.line", views: [[false, "list"], [false, "pivot"], [false, "graph"]], domain, context: { create: false } });
    }
}

registry.category("actions").add("bird_campaign_dashboard", BirdCampaignDashboard);
