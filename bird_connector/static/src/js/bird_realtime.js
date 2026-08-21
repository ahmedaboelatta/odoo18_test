/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { FormController } from "@web/views/form/form_controller";

const LIVE_MODELS = new Set(["bird.message.log", "bird.bulk.send", "bird.contact"]);

registry.category("services").add("bird_realtime_status", {
    dependencies: ["bus_service"],
    start(env, { bus_service }) {
        bus_service.addChannel("bird_status_updates");
        bus_service.addEventListener("notification", ({ detail: notifications }) => {
            for (const notification of notifications || []) {
                if (notification.type === "bird_status_update") {
                    env.bus.trigger("bird-status-update", notification.payload || {});
                }
            }
        });
        return {};
    },
});

async function reloadBirdController(controller) {
    if (!LIVE_MODELS.has(controller.props?.resModel)) {
        return;
    }
    try {
        if (controller.model?.root?.load) {
            await controller.model.root.load();
        } else if (controller.model?.load) {
            await controller.model.load();
        }
    } catch {
        // A realtime refresh is best-effort; the fallback cron/manual refresh remains available.
    }
}

patch(ListController.prototype, {
    setup() {
        super.setup();
        useBus(this.env.bus, "bird-status-update", () => reloadBirdController(this));
    },
});

patch(FormController.prototype, {
    setup() {
        super.setup();
        useBus(this.env.bus, "bird-status-update", () => reloadBirdController(this));
    },
});
