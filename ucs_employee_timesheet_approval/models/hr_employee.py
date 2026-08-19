# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _format_float_time(self, hours):
        h = int(hours or 0)
        m = int(round((hours - h) * 60))
        if m >= 60:
            h += 1
            m = 0
        return f"{h:02d}:{m:02d}"

    @api.model
    def _cron_send_timesheet_shortfall_notifications(self):
        today = fields.Date.context_today(self)
        target_date = today - timedelta(days=1)
        weekday = str(target_date.weekday())

        active_employees = self.search([('active', '=', True)])
        shortfall_data = []

        for employee in active_employees:
            calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
            if not calendar:
                continue

            # 1. Check if target_date is a Weekend / Off-day in Working Schedule (excluding lunch breaks)
            attendances_spec = calendar.attendance_ids.filtered(lambda a: a.dayofweek == weekday and getattr(a, 'day_period', '') != 'lunch')
            if not attendances_spec:
                continue
            
            required_hours = sum(a.hour_to - a.hour_from for a in attendances_spec)
            if required_hours <= 0.1:
                continue

            # 2. Check if target_date is a Public Holiday / Global Leave on Calendar
            public_holiday = self.env['resource.calendar.leaves'].sudo().search([
                '|', ('calendar_id', '=', calendar.id), ('calendar_id', '=', False),
                ('resource_id', '=', False),
                ('date_from', '<=', target_date),
                ('date_to', '>=', target_date)
            ], limit=1)
            if public_holiday:
                continue

            # 3. Calculate total approved leave hours for target_date (Full Day or Partial/Hourly Leave)
            approved_leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'validate'),
                ('request_date_from', '<=', target_date),
                ('request_date_to', '>=', target_date)
            ])
            
            leave_hours = 0.0
            for l in approved_leaves:
                if getattr(l, 'number_of_hours', 0.0):
                    leave_hours += l.number_of_hours
                elif getattr(l, 'number_of_days', 0.0):
                    day_hrs = calendar.hours_per_day if hasattr(calendar, 'hours_per_day') and calendar.hours_per_day else 8.0
                    leave_hours += l.number_of_days * day_hrs

            net_required_hours = max(0.0, required_hours - leave_hours)
            if net_required_hours <= 0.05:
                # Fully covered by leave for target_date
                continue

            # 4. Calculate actual logged timesheet hours for target_date (ALL statuses included)
            timesheet_lines = self.env['account.analytic.line'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date', '=', target_date)
            ])
            actual_timesheet_hours = sum(line.unit_amount or 0.0 for line in timesheet_lines)

            if actual_timesheet_hours < (net_required_hours - 0.05):
                shortfall_hours = net_required_hours - actual_timesheet_hours
                shortfall_data.append({
                    'employee': employee,
                    'required_hours': required_hours,
                    'leave_hours': leave_hours,
                    'net_required_hours': net_required_hours,
                    'actual_timesheet_hours': actual_timesheet_hours,
                    'shortfall_hours': shortfall_hours,
                    'manager': employee.parent_id,
                    'manager_manager': employee.parent_id.parent_id if employee.parent_id else False,
                })

        if not shortfall_data:
            _logger.info("No timesheet shortfall detected for yesterday (%s).", target_date)
            return

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        company_email = self.env.company.email or self.env.user.email_formatted or 'noreply@company.com'

        # Collect unique managers (direct managers and manager's managers)
        all_recipient_managers = self.env['hr.employee']
        for item in shortfall_data:
            if item['manager']:
                all_recipient_managers |= item['manager']
            if item['manager_manager']:
                all_recipient_managers |= item['manager_manager']

        for mgr in all_recipient_managers:
            mgr_email = mgr.work_email or (mgr.user_id.email if mgr.user_id else False)
            if not mgr_email:
                continue

            mgr_items = []
            for item in shortfall_data:
                is_direct = (item['manager'].id == mgr.id) if item['manager'] else False
                is_indirect = (item['manager_manager'].id == mgr.id) if item['manager_manager'] else False
                
                if is_direct or is_indirect:
                    rel_type = "Direct Report" if is_direct else f"Indirect Report ({item['manager'].name if item['manager'] else '-'})"
                    mgr_items.append({
                        'item': item,
                        'rel_type': rel_type
                    })

            if not mgr_items:
                continue

            rows_html = ""
            for entry in mgr_items:
                item = entry['item']
                emp = item['employee']
                rel_type = entry['rel_type']
                req_str = self._format_float_time(item['required_hours'])
                lve_str = self._format_float_time(item['leave_hours'])
                net_str = self._format_float_time(item['net_required_hours'])
                act_str = self._format_float_time(item['actual_timesheet_hours'])
                sht_str = self._format_float_time(item['shortfall_hours'])
                rows_html += f"""
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #1e293b;">{emp.name}</td>
                    <td style="padding: 10px; color: #64748b; font-size: 13px;">{rel_type}</td>
                    <td style="padding: 10px; text-align: center; color: #475569;">{req_str} Hrs</td>
                    <td style="padding: 10px; text-align: center; color: #65a30d;">{lve_str} Hrs</td>
                    <td style="padding: 10px; text-align: center; color: #2563eb; font-weight: bold;">{net_str} Hrs</td>
                    <td style="padding: 10px; text-align: center; color: #475569;">{act_str} Hrs</td>
                    <td style="padding: 10px; text-align: center; font-weight: bold; color: #dc2626;">-{sht_str} Hrs</td>
                </tr>
                """

            subject = f"[Timesheet Shortfall Alert] Daily Timesheet Shortfall Report ({target_date})"
            body_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
                <div style="background-color: #6C5CE7; padding: 15px 20px; border-radius: 8px 8px 0 0;">
                    <h3 style="color: #ffffff; margin: 0;">Daily Timesheet Shortfall Alert</h3>
                </div>
                <div style="border: 1px solid #e2e8f0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; background: #ffffff;">
                    <p>Dear <strong>{mgr.name}</strong>,</p>
                    <p>The following team members under your reporting hierarchy logged fewer timesheet hours than their net required working schedule yesterday (<strong>{target_date}</strong>):</p>
                    
                    <table style="border-collapse: collapse; width: 100%; margin: 15px 0;">
                        <thead>
                            <tr style="background-color: #f8fafc; color: #1e293b; border-bottom: 2px solid #cbd5e1;">
                                <th style="padding: 10px; text-align: left;">Employee</th>
                                <th style="padding: 10px; text-align: left;">Reporting Type</th>
                                <th style="padding: 10px; text-align: center;">Schedule</th>
                                <th style="padding: 10px; text-align: center;">Approved Leave</th>
                                <th style="padding: 10px; text-align: center;">Net Required</th>
                                <th style="padding: 10px; text-align: center;">Timesheet Logged</th>
                                <th style="padding: 10px; text-align: center;">Shortfall</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>

                    <br/>
                    <p style="font-size: 12px; color: #777;">This is an automated daily notification from Employee Self Service System.</p>
                </div>
            </div>
            """
            try:
                mail = self.env['mail.mail'].sudo().create({
                    'subject': subject,
                    'email_from': company_email,
                    'email_to': mgr_email,
                    'body_html': body_html,
                    'state': 'outgoing',
                })
                mail.send()
            except Exception as e:
                _logger.error("Failed to send consolidated timesheet shortfall report to %s: %s", mgr_email, str(e))
