from odoo import api, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.model
    def get_mustashark_org_chart_data(self, department_id=False):
        """Return the data needed by the employee org chart.

        :param department_id: when given, only employees of that department
            (including its sub-departments) are returned, plus the chain of
            their managers up to the root so the tree stays connected.
        :return: dict with ``employees`` and ``departments`` lists.
            Only public directory fields are exposed (no salary or
            private HR data).
        """
        Employee = self.env["hr.employee"].sudo()
        Department = self.env["hr.department"].sudo()

        departments = [
            {"id": dept.id, "name": dept.name}
            for dept in Department.search([], order="name")
        ]

        domain = [("active", "=", True)]
        dept_ids = False
        if department_id:
            dept = Department.browse(int(department_id))
            if dept.exists():
                dept_ids = set(self._mustashark_collect_department_ids(dept))
                domain.append(("department_id", "in", list(dept_ids)))

        employees = Employee.search(domain)

        if dept_ids:
            # Add the managers chain of the filtered employees so the
            # chart is still one connected tree.
            known_ids = set(employees.ids)
            frontier = {
                emp.parent_id.id for emp in employees if emp.parent_id
            } - known_ids
            guard = 0
            extra_ids = set()
            while frontier and guard < 50:
                guard += 1
                extra_ids |= frontier
                known_ids |= frontier
                parents = Employee.browse(list(frontier)).mapped("parent_id")
                frontier = {p.id for p in parents if p} - known_ids
            if extra_ids:
                employees |= Employee.browse(list(extra_ids))

        children_map = {}
        for emp in employees:
            if emp.parent_id:
                children_map.setdefault(emp.parent_id.id, []).append(emp.id)

        result = []
        for emp in employees:
            result.append(
                {
                    "id": emp.id,
                    "name": emp.name,
                    "job_title": emp.job_id.name or "",
                    "department_id": emp.department_id.id or False,
                    "department_name": emp.department_id.name or "",
                    "parent_id": emp.parent_id.id or False,
                    "image_url": "/web/image/hr.employee/%s/image_128" % emp.id,
                    "work_email": emp.work_email or "",
                    "work_phone": emp.work_phone or "",
                    "child_count": len(children_map.get(emp.id, [])),
                    # Manager shown only to keep the tree connected when
                    # a department filter is active.
                    "is_outside_filter": bool(
                        dept_ids
                        and emp.department_id.id not in dept_ids
                    ),
                }
            )
        return {"employees": result, "departments": departments}

    @api.model
    def get_mustashark_department_chart_data(self):
        """Return the department tree (parent departments, managers, sizes)."""
        Department = self.env["hr.department"].sudo()
        result = []
        for dept in Department.search([]):
            result.append(
                {
                    "id": dept.id,
                    "name": dept.name,
                    "parent_id": dept.parent_id.id or False,
                    "manager_id": dept.manager_id.id or False,
                    "manager_name": dept.manager_id.name or "",
                    "member_count": len(dept.member_ids),
                }
            )
        return {"departments": result}

    @api.model
    def _mustashark_collect_department_ids(self, department):
        ids = [department.id]
        for child in department.child_ids:
            ids += self._mustashark_collect_department_ids(child)
        return ids
