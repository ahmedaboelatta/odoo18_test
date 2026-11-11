from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HaderMobileTask(models.Model):
    _name = "hader.mobile.task"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Employee Daily Task & Activity (المهام والأنشطة اليومية)"
    _order = "state asc, due_date asc, priority desc, id desc"

    name = fields.Char(
        string="رقم المهمة / Reference",
        required=True,
        readonly=True,
        default="New",
        copy=False,
    )
    title = fields.Char(
        string="عنوان المهمة / Task Title",
        required=True,
        tracking=True,
    )
    description = fields.Text(string="تفاصيل المهمة / Task Details")
    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف المكلف / Assigned Employee",
        required=True,
        index=True,
        tracking=True,
    )
    assigned_by_employee_id = fields.Many2one(
        "hr.employee",
        string="مُسندة بواسطة (المدير) / Assigned By Employee",
        index=True,
        tracking=True,
    )
    assigned_by_user_id = fields.Many2one(
        "res.users",
        string="مُسندة من مستخدم النظام / Assigned By User",
        default=lambda self: self.env.user,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="employee_id.company_id",
        store=True,
        index=True,
    )
    priority = fields.Selection(
        [
            ("low", "منخفضة / Low"),
            ("normal", "عادية / Normal"),
            ("high", "عالية / High"),
            ("urgent", "عاجلة جداً / Urgent"),
        ],
        string="الأولوية / Priority",
        default="normal",
        required=True,
        tracking=True,
    )
    due_date = fields.Date(
        string="تاريخ الاستحقاق / Due Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("todo", "جديدة / To Do"),
            ("in_progress", "قيد التنفيذ / In Progress"),
            ("done", "مكتملة / Completed"),
            ("cancelled", "ملغاة / Cancelled"),
        ],
        string="الحالة / Status",
        default="todo",
        required=True,
        index=True,
        tracking=True,
    )
    completion_note = fields.Text(
        string="ملاحظات الإنجاز من الموظف / Completion Note",
        tracking=True,
    )
    completed_at = fields.Datetime(
        string="تاريخ الإنجاز / Completed At",
        readonly=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "hader_mobile_task_ir_attachment_rel",
        "task_id",
        "attachment_id",
        string="مرفقات وصور الإنجاز / Task Attachments",
    )
    attachment_count = fields.Integer(
        string="عدد المرفقات",
        compute="_compute_attachment_count",
    )
    active = fields.Boolean(default=True)

    @api.depends("attachment_ids")
    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.attachment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        ym = fields.Date.context_today(self).strftime("%Y/%m")
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                seq = self.env["ir.sequence"].next_by_code("hader.mobile.task") or "00001"
                num = seq.split("-")[-1].split("/")[-1]
                vals["name"] = f"TSK/{ym}/{num}"
        records = super().create(vals_list)
        if "hader.mobile.notification.inbox" in self.env:
            Inbox = self.env["hader.mobile.notification.inbox"].sudo()
            for rec in records:
                # Notify employee if assigned by manager or backend admin
                if not rec.assigned_by_employee_id or rec.assigned_by_employee_id.id != rec.employee_id.id:
                    assigner_name = (
                        rec.assigned_by_employee_id.name
                        or (rec.assigned_by_user_id.name if rec.assigned_by_user_id else "الإدارة")
                    )
                    Inbox.notify_employee(
                        rec.employee_id,
                        "مهمة عمل جديدة",
                        f"أسند إليك {assigner_name} مهمة جديدة: ({rec.title}) — تاريخ الاستحقاق: {rec.due_date}.",
                        "task_assigned",
                        title_en="New work task assigned",
                        body_en=f"{assigner_name} assigned you a task: ({rec.title}) — Due: {rec.due_date}.",
                    )
        return records

    def action_start(self):
        self.write({"state": "in_progress"})
        return True

    def action_done(self):
        self.write({
            "state": "done",
            "completed_at": fields.Datetime.now(),
        })
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

    def action_reset_todo(self):
        self.write({"state": "todo", "completed_at": False})
        return True

    def mobile_update_status(self, actor_employee, new_state, note=""):
        self.ensure_one()
        is_owner = self.employee_id.id == actor_employee.id
        is_assigner = bool(
            self.assigned_by_employee_id and self.assigned_by_employee_id.id == actor_employee.id
        )
        is_manager = bool(
            (hasattr(self.employee_id, "_is_mobile_approver") and self.employee_id._is_mobile_approver(actor_employee))
            or (self.employee_id.parent_id and self.employee_id.parent_id.id == actor_employee.id)
        )
        if not (is_owner or is_assigner or is_manager):
            raise ValidationError(_("You are not allowed to update this task."))
        if new_state not in ("todo", "in_progress", "done", "cancelled"):
            raise ValidationError(_("Invalid task state."))

        vals = {"state": new_state}
        clean_note = (note or "").strip()
        if clean_note:
            vals["completion_note"] = clean_note
        if new_state == "done":
            vals["completed_at"] = fields.Datetime.now()
        self.sudo().write(vals)
        self.sudo().message_post(
            body=_("تم تحديث حالة المهمة إلى (%s) بواسطة %s. ملاحظة: %s")
            % (new_state, actor_employee.name, clean_note or "—"),
            subtype_xmlid="mail.mt_note",
        )

        if new_state == "done" and "hader.mobile.notification.inbox" in self.env:
            target = self.assigned_by_employee_id or self.employee_id.parent_id
            if target and target.id != actor_employee.id:
                self.env["hader.mobile.notification.inbox"].sudo().notify_employee(
                    target,
                    "تم إنجاز مهمة عمل",
                    f"أتمّ {self.employee_id.name} المهمة ({self.title}) برقم {self.name}.",
                    "task_completed",
                    title_en="Task completed",
                    body_en=f"{self.employee_id.name} completed task ({self.title}) {self.name}.",
                )
        return True

    def mobile_dto(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        is_overdue = bool(
            self.due_date
            and self.due_date < today
            and self.state in ("todo", "in_progress")
        )
        assigner_name = (
            self.assigned_by_employee_id.name
            if self.assigned_by_employee_id
            else (self.assigned_by_user_id.name if self.assigned_by_user_id else "")
        )
        return {
            "id": self.id,
            "reference": self.name,
            "title": self.title or "",
            "description": self.description or "",
            "employee_id": self.employee_id.id,
            "employee_name": self.employee_id.name or "",
            "assigned_by_name": assigner_name or "",
            "priority": self.priority or "normal",
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "state": self.state,
            "is_overdue": is_overdue,
            "completion_note": self.completion_note or "",
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.create_date.isoformat() if self.create_date else None,
            "attachments": [
                {
                    "id": att.id,
                    "name": att.name,
                    "mimetype": att.mimetype or "application/octet-stream",
                    "size": att.file_size or 0,
                }
                for att in self.attachment_ids.sudo()
            ],
        }
