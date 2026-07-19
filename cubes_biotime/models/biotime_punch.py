# -*- coding: utf-8 -*-
import logging
from odoo import fields, models, api, _, tools
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class BioTimePunch(models.Model):
    _name = 'biotime.punch'
    _description = 'Biotime Raw Punch'
    _order = 'punch_datetime DESC'

    name = fields.Char(string="Reference", compute='_compute_name', store=True)
    employee_id = fields.Many2one('hr.employee', string="Employee")
    biotime_employee_id = fields.Many2one('biotime.employee', string="Biotime Employee")
    biotime_terminal_id = fields.Many2one('biotime.terminal', string="Terminal")
    
    emp_code = fields.Char(string="Employee Code")
    terminal_sn = fields.Char(string="Terminal SN")
    punch_time = fields.Char(string="Original Punch Time")
    punch_datetime = fields.Datetime(string="Punch Datetime")
    punch_state = fields.Selection([
        ('0', 'Check In'),
        ('1', 'Check Out'),
        ('2', 'Break Out'),
        ('3', 'Break In'),
        ('4', 'Overtime In'),
        ('5', 'Overtime Out'),
        ('unknown', 'Unknown')
    ], string="Punch State", default='unknown')
    
    verify_type = fields.Char(string="Verify Type")
    work_code = fields.Char(string="Work Code")
    
    attendance_id = fields.Many2one('hr.attendance', string="Attendance Record")
    processed = fields.Boolean(string="Processed", default=False, compute="_compute_processed", store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('error', 'Error'),
        ('manual', 'Manually Processed')
    ], string="Status", default='draft')
    
    notes = fields.Text(string="Notes")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company.id)
    
    # For statistics
    needs_attention = fields.Boolean(string="Needs Attention", compute="_compute_needs_attention", store=True)
    
    @api.depends('state', 'punch_state', 'processed')
    def _compute_needs_attention(self):
        for record in self:
            record.needs_attention = (
                record.state in ['error', 'draft'] or 
                (record.punch_state == 'unknown' and not record.processed)
            )
    
    @api.depends('attendance_id', 'state')
    def _compute_processed(self):
        for record in self:
            # Only mark as processed if there's an actual attendance record
            # or it was manually marked as processed
            if record.attendance_id or record.state == 'manual':
                record.processed = True
            else:
                record.processed = False
    
    @api.depends('biotime_employee_id', 'punch_datetime')
    def _compute_name(self):
        for record in self:
            datetime_str = record.punch_datetime.strftime('%Y-%m-%d %H:%M:%S') if record.punch_datetime else ''
            emp_name = record.biotime_employee_id.name or record.emp_code or 'Unknown'
            record.name = f"{emp_name} - {datetime_str}"
    
    def action_mark_check_in(self):
        self.ensure_one()
        self.punch_state = '0'  # Check In
        result = self._process_punch()
        if result:
            self.state = 'manual'
        return True
        
    def action_mark_check_out(self):
        self.ensure_one()
        self.punch_state = '1'  # Check Out
        result = self._process_punch()
        if result:
            self.state = 'manual'
        return True
    
    def _process_punch(self):
        """Process this punch to create/update attendance"""
        self.ensure_one()
        if not self.employee_id:
            self.state = 'error'
            self.notes = "No employee assigned"
            return False
            
        if self.punch_state == '0':  # Check In
            # Look for existing open attendance
            existing_attendance = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('check_in', '!=', False),
                ('check_out', '=', False)
            ], limit=1)
            
            if existing_attendance:
                # Already has an open attendance - log this unusual case
                self.state = 'error'
                self.notes = f"Employee already has an open attendance record (ID: {existing_attendance.id})"
                return False
            else:
                # Create new attendance with check-in
                attendance = self.env['hr.attendance'].sudo().create({
                    'employee_id': self.employee_id.id,
                    'check_in': self.punch_datetime,
                })
                self.attendance_id = attendance.id
                self.state = 'processed'
                return True
                
        elif self.punch_state == '1':  # Check Out
            # Look for an open attendance to close
            open_attendance = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('check_in', '!=', False),
                ('check_out', '=', False)
            ], limit=1, order='check_in ASC')
            
            if open_attendance:
                # Close the attendance
                open_attendance.check_out = self.punch_datetime
                self.attendance_id = open_attendance.id
                self.state = 'processed'
                return True
            else:
                # No open attendance found - log this
                self.state = 'error'
                self.notes = "No open attendance record found to check out"
                return False
        else:
            # Not a check-in or check-out punch - can't process
            self.state = 'error'
            self.notes = f"Cannot process punch with state '{self.punch_state}'"
            return False
        
        return False

    # Batch processing methods
    def action_auto_assign_chronological(self):
        """Auto-assign punches based on chronology for a single employee"""
        # Get all unprocessed punches for this employee in order
        employee = self.employee_id
        if not employee:
            return False

        # Get all unprocessed punches for this employee
        all_punches = self.search([
            ('employee_id', '=', employee.id),
            ('processed', '=', False),
            ('state', 'in', ['draft', 'error']),
        ], order='punch_datetime ASC')

        if not all_punches:
            return False

        # Find the last state of the employee
        last_attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
        ], limit=1, order='check_in DESC')

        # Determine the next expected punch type
        next_punch_state = '0'  # Default to check-in
        if last_attendance and not last_attendance.check_out:
            next_punch_state = '1'  # If last attendance is open, expect check-out
        
        for punch in all_punches:
            punch.punch_state = next_punch_state
            result = punch._process_punch()
            if result:
                # Toggle the expected next state
                next_punch_state = '0' if next_punch_state == '1' else '1'

        return True

    def _reprocess_unprocessed_punches(self):
        """Attempt to reprocess any punches that are not processed but have valid state"""
        unprocessed = self.search([
            ('state', 'in', ['draft', 'error']),
            ('punch_state', 'in', ['0', '1']),  # Only check-in and check-out
            ('employee_id', '!=', False),
        ])
        
        for punch in unprocessed:
            punch._process_punch()
        
        return True

    @api.model
    def action_auto_process_unknown_punches(self):
        """Auto-process unknown state punches in batch"""
        # First try to reprocess any valid but unprocessed punches
        self._reprocess_unprocessed_punches()
        
        # Process by employee to maintain proper order
        employees = self.env['hr.employee'].search([])
        
        for employee in employees:
            # Get unprocessed punches with unknown state for this employee
            unprocessed = self.search([
                ('employee_id', '=', employee.id),
                ('punch_state', '=', 'unknown'),
                ('state', 'in', ['draft', 'error']),
            ])
            
            if unprocessed:
                # Group by day
                punches_by_day = {}
                for punch in unprocessed:
                    day_key = punch.punch_datetime.strftime('%Y-%m-%d')
                    if day_key not in punches_by_day:
                        punches_by_day[day_key] = []
                    punches_by_day[day_key].append(punch)
                
                # Process each day's punches
                for day, day_punches in punches_by_day.items():
                    # Sort by datetime
                    sorted_punches = sorted(day_punches, key=lambda p: p.punch_datetime)
                    
                    # If even number of punches, pair them as in/out
                    if len(sorted_punches) % 2 == 0:
                        for i in range(0, len(sorted_punches), 2):
                            if i < len(sorted_punches):
                                sorted_punches[i].punch_state = '0'  # Check In
                                sorted_punches[i]._process_punch()
                                
                            if i+1 < len(sorted_punches):
                                sorted_punches[i+1].punch_state = '1'  # Check Out
                                sorted_punches[i+1]._process_punch()
                    # If odd number, leave the last one unprocessed
                    else:
                        for i in range(0, len(sorted_punches)-1, 2):
                            if i < len(sorted_punches):
                                sorted_punches[i].punch_state = '0'  # Check In
                                sorted_punches[i]._process_punch()
                                
                            if i+1 < len(sorted_punches):
                                sorted_punches[i+1].punch_state = '1'  # Check Out
                                sorted_punches[i+1]._process_punch()
                                
    @api.model
    def get_problematic_punch_stats(self):
        """Get statistics on problematic punches for notification"""
        # Get counts of problematic punches
        today = fields.Date.today()
        yesterday = today - timedelta(days=1)
        
        domain = ['|', '|', 
            ('state', '=', 'error'), 
            ('state', '=', 'draft'), 
            '&', ('punch_state', '=', 'unknown'), ('processed', '=', False)
        ]
        
        # Today's issues
        today_domain = domain + [
            ('punch_datetime', '>=', fields.Datetime.to_string(datetime.combine(today, datetime.min.time()))),
            ('punch_datetime', '<', fields.Datetime.to_string(datetime.combine(today + timedelta(days=1), datetime.min.time())))
        ]
        today_count = self.search_count(today_domain)
        
        # Yesterday's issues
        yesterday_domain = domain + [
            ('punch_datetime', '>=', fields.Datetime.to_string(datetime.combine(yesterday, datetime.min.time()))),
            ('punch_datetime', '<', fields.Datetime.to_string(datetime.combine(today, datetime.min.time())))
        ]
        yesterday_count = self.search_count(yesterday_domain)
        
        # Group by employee to find top problematic employees
        employee_stats = {}
        problematic_punches = self.search(domain + [
            ('punch_datetime', '>=', fields.Datetime.to_string(datetime.combine(today - timedelta(days=7), datetime.min.time())))
        ])
        
        for punch in problematic_punches:
            emp_name = punch.employee_id.name or punch.biotime_employee_id.name or punch.emp_code or 'Unknown'
            if emp_name not in employee_stats:
                employee_stats[emp_name] = 0
            employee_stats[emp_name] += 1
        
        # Sort by count
        sorted_employees = sorted(employee_stats.items(), key=lambda x: x[1], reverse=True)
        top_employees = sorted_employees[:5] if sorted_employees else []
        
        return {
            'today_count': today_count,
            'yesterday_count': yesterday_count,
            'total_count': self.search_count(domain),
            'top_employees': top_employees
        }
    
    @api.model
    def action_notify_administrators(self):
        """Notify administrators about problematic punches"""
        stats = self.get_problematic_punch_stats()
        
        if not stats['today_count'] and not stats['yesterday_count']:
            return  # No issues to report
            
        # Get administrators to notify
        admin_users = self.env.ref('hr.group_hr_manager').users
        
        if not admin_users:
            return
            
        # Prepare message
        message = f"""
<p>Biotime Attendance Issues Summary:</p>
<ul>
    <li><strong>Today:</strong> {stats['today_count']} issues</li>
    <li><strong>Yesterday:</strong> {stats['yesterday_count']} issues</li>
    <li><strong>Total open issues:</strong> {stats['total_count']} issues</li>
</ul>
"""
        
        if stats['top_employees']:
            message += "<p><strong>Top employees with issues:</strong></p><ul>"
            for employee, count in stats['top_employees']:
                message += f"<li>{employee}: {count} issues</li>"
            message += "</ul>"
            
        message += "<p>Please review and fix these issues in the Attendance Issues menu.</p>"
        
        # Send notification
        self.env['mail.message'].create({
            'subject': f"Biotime Attendance Issues: {stats['today_count']} new issues today",
            'body': message,
            'model': 'biotime.punch',
            'res_id': 0,  # Generic record
            'message_type': 'notification',
            'partner_ids': [(4, user.partner_id.id) for user in admin_users],
            'subtype_id': self.env.ref('mail.mt_comment').id,
        }) 