/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy } from "@odoo/owl";

export class AxsyncDeliveryDashboard extends Component {
    static template = "axsync_purchase_delivery_tracker.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ days: 90, data: null });
        this.periods = [
            { value: 30, label: "Last 30 days" },
            { value: 90, label: "Last 90 days" },
            { value: 180, label: "Last 6 months" },
            { value: 365, label: "Last 12 months" },
            { value: 0, label: "All time" },
        ];
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call(
            "axsync.delivery.order", "get_dashboard_data", [this.state.days]
        );
    }

    async onPeriodChange(ev) {
        this.state.days = parseInt(ev.target.value, 10);
        await this.load();
    }

    formatValue(tile) {
        const num = Number(tile.value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
        return `${num}${tile.suffix || ""}`;
    }

    openTile(tile) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: tile.label,
            res_model: tile.model,
            views: [[false, "list"], [false, "pivot"], [false, "graph"]],
            domain: tile.domain,
        });
    }

    openOrder(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.order",
            res_id: id,
            views: [[false, "form"]],
        });
    }

    openSupplier(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Deliveries",
            res_model: "axsync.delivery.order",
            views: [[false, "list"], [false, "pivot"], [false, "graph"]],
            domain: [["partner_id", "=", id]],
        });
    }

    openAllSuppliers() {
        this.action.doAction("axsync_purchase_delivery_tracker.axsync_delivery_supplier_action");
    }
}

registry.category("actions").add("axsync_delivery_dashboard", AxsyncDeliveryDashboard);
