/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const CARD = {
    employees: { w: 216, h: 92 },
    departments: { w: 232, h: 86 },
};
const H_GAP = 28;
const V_GAP = 64;
const MIN_ZOOM = 0.15;
const MAX_ZOOM = 2;

const DEPT_COLORS = [
    "#7C3AED",
    "#2563EB",
    "#0891B2",
    "#059669",
    "#D97706",
    "#DC2626",
    "#DB2777",
    "#4D7C0F",
];

export class OrgChart extends Component {
    static template = "hr_org_chart.OrgChart";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.viewportRef = useRef("viewport");
        this.state = useState({
            mode: "employees", // 'employees' | 'departments'
            employees: [],
            departments: [],
            deptNodes: [],
            deptLoaded: false,
            selectedDept: 0,
            search: "",
            matchedIds: [],
            collapsed: {},
            zoom: 1,
            panX: 0,
            panY: 0,
            selectedId: null,
            loading: true,
        });
        this._drag = null;
        this._suppressClick = false;

        onWillStart(async () => {
            await this.loadEmployees();
        });
        onMounted(() => {
            const viewport = this.viewportRef.el;
            if (viewport) {
                viewport.addEventListener("wheel", this._onWheel.bind(this), {
                    passive: false,
                });
                viewport.addEventListener("pointerdown", this._onPointerDown.bind(this));
            }
            requestAnimationFrame(() => this.fitView());
        });
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------

    async loadEmployees() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("hr.employee", "get_org_chart_data", [], {
                department_id: this.state.selectedDept || false,
            });
            this.state.employees = data.employees;
            this.state.departments = data.departments;
        } finally {
            this.state.loading = false;
        }
    }

    async loadDepartments() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "hr.employee",
                "get_department_chart_data",
                [],
                {}
            );
            this.state.deptNodes = data.departments;
            this.state.deptLoaded = true;
        } finally {
            this.state.loading = false;
        }
    }

    async setMode(mode) {
        if (this.state.mode === mode) {
            return;
        }
        this.state.mode = mode;
        this.state.selectedId = null;
        this.state.collapsed = {};
        this.state.search = "";
        this.state.matchedIds = [];
        if (mode === "departments" && !this.state.deptLoaded) {
            await this.loadDepartments();
        }
        setTimeout(() => this.fitView(), 60);
    }

    async onDepartmentChange(ev) {
        this.state.selectedDept = parseInt(ev.target.value, 10) || 0;
        this.state.selectedId = null;
        this.state.collapsed = {};
        await this.loadEmployees();
        setTimeout(() => this.fitView(), 60);
    }

    // ------------------------------------------------------------------
    // Tree building + layout (tidy tree: parents centered over children)
    // ------------------------------------------------------------------

    get currentNodes() {
        return this.state.mode === "departments"
            ? this.state.deptNodes
            : this.state.employees;
    }

    get cardSize() {
        return CARD[this.state.mode];
    }

    get layout() {
        const nodes = this.currentNodes;
        const { w: CW, h: CH } = this.cardSize;
        const byId = {};
        nodes.forEach((n) => {
            byId[n.id] = n;
        });

        const children = {};
        const roots = [];
        nodes.forEach((n) => {
            const pid = n.parent_id;
            if (pid && byId[pid]) {
                (children[pid] = children[pid] || []).push(n.id);
            } else {
                roots.push(n.id);
            }
        });
        const byName = (a, b) => (byId[a].name || "").localeCompare(byId[b].name || "");
        Object.values(children).forEach((list) => list.sort(byName));
        roots.sort(byName);

        const collapsed = this.state.collapsed;
        const visibleChildren = (id) => (collapsed[id] ? [] : children[id] || []);

        const widthMemo = {};
        const measure = (id) => {
            if (widthMemo[id] !== undefined) {
                return widthMemo[id];
            }
            const kids = visibleChildren(id);
            let w = CW;
            if (kids.length) {
                const total =
                    kids.reduce((s, k) => s + measure(k), 0) + H_GAP * (kids.length - 1);
                w = Math.max(CW, total);
            }
            widthMemo[id] = w;
            return w;
        };

        const positions = {};
        const assign = (id, left, depth) => {
            const w = measure(id);
            positions[id] = { x: left + w / 2, y: depth * (CH + V_GAP) };
            const kids = visibleChildren(id);
            if (kids.length) {
                const kidsTotal =
                    kids.reduce((s, k) => s + measure(k), 0) + H_GAP * (kids.length - 1);
                let cursor = left + (w - kidsTotal) / 2;
                kids.forEach((k) => {
                    assign(k, cursor, depth + 1);
                    cursor += measure(k) + H_GAP;
                });
            }
        };
        let cursor = 0;
        roots.forEach((r) => {
            assign(r, cursor, 0);
            cursor += measure(r) + H_GAP;
        });
        const rootsTotal = Math.max(cursor - H_GAP, 0);

        // Fallback for cyclic / broken manager chains: any node that could
        // not be placed (no path to a root) is shown flat in an extra row.
        let maxDepth = 0;
        Object.values(positions).forEach((p) => {
            const d = Math.round(p.y / (CH + V_GAP));
            if (d > maxDepth) {
                maxDepth = d;
            }
        });
        const unplaced = nodes.filter((n) => !positions[n.id]);
        let extraX = 0;
        unplaced.forEach((n) => {
            positions[n.id] = {
                x: extraX + CW / 2,
                y: (maxDepth + 1) * (CH + V_GAP),
            };
            extraX += CW + H_GAP;
        });
        if (unplaced.length) {
            maxDepth += 1;
        }

        const width = Math.max(rootsTotal, Math.max(extraX - H_GAP, 0), CW);
        const height = nodes.length ? (maxDepth + 1) * CH + maxDepth * V_GAP : CH;

        const edges = [];
        Object.keys(children).forEach((pid) => {
            const p = positions[pid];
            if (!p) {
                return;
            }
            visibleChildren(pid).forEach((cid) => {
                const c = positions[cid];
                if (!c) {
                    return;
                }
                const x1 = p.x;
                const y1 = p.y + CH;
                const x2 = c.x;
                const y2 = c.y;
                const my = (y1 + y2) / 2;
                edges.push({
                    id: pid + "-" + cid,
                    d: `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`,
                });
            });
        });

        return {
            positions,
            edges,
            width,
            height,
            roots,
            children,
            byId,
            nodes: nodes.filter((n) => positions[n.id]),
        };
    }

    get canvasStyle() {
        const layout = this.layout;
        return (
            `width:${layout.width}px;height:${layout.height}px;` +
            `transform:translate(${this.state.panX}px, ${this.state.panY}px) scale(${this.state.zoom});`
        );
    }

    nodeStyle(node) {
        const pos = this.layout.positions[node.id];
        const { w } = this.cardSize;
        if (!pos) {
            return "display:none;";
        }
        return `left:${pos.x - w / 2}px;top:${pos.y}px;width:${w}px;`;
    }

    nodeClass(node) {
        return {
            o_org_node_selected: this.state.selectedId === node.id,
            o_org_node_matched: this.state.matchedIds.includes(node.id),
            o_org_node_outside: !!node.is_outside_filter,
        };
    }

    childCount(node) {
        return (this.layout.children[node.id] || []).length;
    }

    hasChildren(node) {
        return this.childCount(node) > 0;
    }

    isCollapsed(id) {
        return !!this.state.collapsed[id];
    }

    get statsText() {
        if (this.state.mode === "departments") {
            return `${this.state.deptNodes.length} قسم`;
        }
        const total = this.state.employees.length;
        const managers = this.state.employees.filter((e) => e.child_count > 0).length;
        return `${total} موظف • ${managers} مدير`;
    }

    // ------------------------------------------------------------------
    // Selection + detail panel
    // ------------------------------------------------------------------

    selectNode(id) {
        if (this._suppressClick) {
            return;
        }
        this.state.selectedId = this.state.selectedId === id ? null : id;
    }

    get selectedNode() {
        if (!this.state.selectedId) {
            return null;
        }
        return this.currentNodes.find((n) => n.id === this.state.selectedId) || null;
    }

    get selectedChildren() {
        const node = this.selectedNode;
        if (!node) {
            return [];
        }
        const kids = this.layout.children[node.id] || [];
        return kids.map((id) => this.layout.byId[id]).filter(Boolean);
    }

    get selectedManager() {
        const node = this.selectedNode;
        if (!node || !node.parent_id) {
            return null;
        }
        return this.layout.byId[node.parent_id] || null;
    }

    selectAndCenter(id) {
        this.state.selectedId = id;
        this.centerOnNode(id);
    }

    async openRecord(node) {
        const model = this.state.mode === "departments" ? "hr.department" : "hr.employee";
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: node.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ------------------------------------------------------------------
    // Expand / collapse
    // ------------------------------------------------------------------

    toggleCollapse(id) {
        if (this.state.collapsed[id]) {
            delete this.state.collapsed[id];
        } else {
            this.state.collapsed[id] = true;
        }
    }

    expandAll() {
        this.state.collapsed = {};
    }

    collapseAll() {
        const collapsed = {};
        const { children, roots } = this.layout;
        Object.keys(children).forEach((pid) => {
            if (!roots.includes(Number(pid))) {
                collapsed[pid] = true;
            }
        });
        this.state.collapsed = collapsed;
    }

    // ------------------------------------------------------------------
    // Search
    // ------------------------------------------------------------------

    onSearchInput(ev) {
        const raw = ev.target.value;
        this.state.search = raw;
        const q = raw.trim().toLowerCase();
        if (!q) {
            this.state.matchedIds = [];
            return;
        }
        const nodes = this.currentNodes;
        const matches = nodes.filter((n) => {
            const hay = `${n.name || ""} ${n.job_title || ""} ${
                n.department_name || ""
            } ${n.manager_name || ""}`.toLowerCase();
            return hay.includes(q);
        });
        // Expand the ancestors of every match so matches are visible.
        const byId = {};
        nodes.forEach((n) => {
            byId[n.id] = n;
        });
        const collapsed = { ...this.state.collapsed };
        let changed = false;
        matches.forEach((m) => {
            let pid = m.parent_id;
            const guard = new Set();
            while (pid && byId[pid] && !guard.has(pid)) {
                guard.add(pid);
                if (collapsed[pid]) {
                    delete collapsed[pid];
                    changed = true;
                }
                pid = byId[pid].parent_id;
            }
        });
        if (changed) {
            this.state.collapsed = collapsed;
        }
        this.state.matchedIds = matches.map((m) => m.id);
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter" && this.state.matchedIds.length) {
            this.selectAndCenter(this.state.matchedIds[0]);
        }
    }

    // ------------------------------------------------------------------
    // Pan & zoom
    // ------------------------------------------------------------------

    _onWheel(ev) {
        ev.preventDefault();
        const viewport = this.viewportRef.el;
        if (!viewport) {
            return;
        }
        const rect = viewport.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;
        const factor = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
        const newZoom = Math.min(
            MAX_ZOOM,
            Math.max(MIN_ZOOM, this.state.zoom * factor)
        );
        const scale = newZoom / this.state.zoom;
        this.state.panX = mx - (mx - this.state.panX) * scale;
        this.state.panY = my - (my - this.state.panY) * scale;
        this.state.zoom = newZoom;
    }

    _onPointerDown(ev) {
        if (ev.button !== 0) {
            return;
        }
        this._drag = {
            x: ev.clientX,
            y: ev.clientY,
            panX: this.state.panX,
            panY: this.state.panY,
            moved: false,
        };
        const move = (e) => {
            if (!this._drag) {
                return;
            }
            const dx = e.clientX - this._drag.x;
            const dy = e.clientY - this._drag.y;
            if (Math.abs(dx) + Math.abs(dy) > 3) {
                this._drag.moved = true;
            }
            this.state.panX = this._drag.panX + dx;
            this.state.panY = this._drag.panY + dy;
        };
        const up = () => {
            if (this._drag && this._drag.moved) {
                // A drag also fires a click on release; ignore that click
                // so dragging never selects a node by accident.
                this._suppressClick = true;
                setTimeout(() => {
                    this._suppressClick = false;
                }, 60);
            }
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
            this._drag = null;
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }

    zoomBy(factor) {
        const viewport = this.viewportRef.el;
        if (!viewport) {
            return;
        }
        const cx = viewport.clientWidth / 2;
        const cy = viewport.clientHeight / 2;
        const newZoom = Math.min(
            MAX_ZOOM,
            Math.max(MIN_ZOOM, this.state.zoom * factor)
        );
        const scale = newZoom / this.state.zoom;
        this.state.panX = cx - (cx - this.state.panX) * scale;
        this.state.panY = cy - (cy - this.state.panY) * scale;
        this.state.zoom = newZoom;
    }

    fitView() {
        const viewport = this.viewportRef.el;
        if (!viewport) {
            return;
        }
        const layout = this.layout;
        if (!layout.width || !layout.nodes.length) {
            return;
        }
        const pad = 48;
        const scale = Math.min(
            (viewport.clientWidth - pad * 2) / layout.width,
            (viewport.clientHeight - pad * 2) / layout.height,
            1.1
        );
        const zoom = Math.max(MIN_ZOOM, scale);
        this.state.zoom = zoom;
        this.state.panX = (viewport.clientWidth - layout.width * zoom) / 2;
        this.state.panY = Math.max(
            24,
            (viewport.clientHeight - layout.height * zoom) / 2
        );
    }

    centerOnNode(id) {
        const pos = this.layout.positions[id];
        const viewport = this.viewportRef.el;
        if (!pos || !viewport) {
            return;
        }
        const zoom = Math.max(this.state.zoom, 0.9);
        this.state.zoom = zoom;
        this.state.panX = viewport.clientWidth / 2 - pos.x * zoom;
        this.state.panY = Math.max(24, viewport.clientHeight / 3 - pos.y * zoom);
    }

    printChart() {
        window.print();
    }

    // ------------------------------------------------------------------
    // Small helpers
    // ------------------------------------------------------------------

    deptColor(deptId) {
        if (!deptId) {
            return "#94A3B8";
        }
        return DEPT_COLORS[deptId % DEPT_COLORS.length];
    }

    initials(name) {
        if (!name) {
            return "?";
        }
        const parts = name.trim().split(/\s+/);
        const first = parts[0][0] || "";
        const second = parts.length > 1 ? parts[1][0] || "" : "";
        return (first + second).toUpperCase();
    }

    onImageError(ev) {
        ev.target.style.display = "none";
    }
}

registry.category("actions").add("hr_org_chart", OrgChart);
