import logging
from datetime import datetime, time
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    regularize_request_assign = fields.Integer(string='Regularization Requests Assigned', default=3)
    regularize_req_used = fields.Integer(string='Regularization Requests Used', default=0)

    @api.model
    def _cron_reset_regularize_requests(self):
        for company in self.env['res.company'].search([]):
            employees = self.search([('company_id', '=', company.id)])
            employees.write({
                'regularize_request_assign': company.regularize_request_per_month,
                'regularize_req_used': 0
            })

    def _format_float_time(self, hours):
        h = int(hours or 0)
        m = int(round((hours - h) * 60))
        if m >= 60:
            h += 1
            m = 0
        return f"{h:02d}:{m:02d}"

    @api.model
    def _cron_send_attendance_shortfall_notifications(self):
        today = fields.Date.context_today(self)
        weekday = str(today.weekday())

        tz_name = self.env.user.tz or 'UTC'
        try:
            import pytz
            local_tz = pytz.timezone(tz_name)
            start_local = local_tz.localize(datetime.combine(today, time.min))
            end_local = local_tz.localize(datetime.combine(today, time.max))
            start_utc = start_local.astimezone(pytz.utc).replace(tzinfo=None)
            end_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)
        except Exception:
            start_utc = datetime.combine(today, time.min)
            end_utc = datetime.combine(today, time.max)

        active_employees = self.search([('active', '=', True)])
        shortfall_data = []

        for employee in active_employees:
            calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
            if not calendar:
                continue

            # 1. Check if today is a Weekend / Off-day in Working Schedule (excluding lunch breaks)
            attendances_spec = calendar.attendance_ids.filtered(lambda a: a.dayofweek == weekday and getattr(a, 'day_period', '') != 'lunch')
            if not attendances_spec:
                continue
            
            required_hours = sum(a.hour_to - a.hour_from for a in attendances_spec)
            if required_hours <= 0.1:
                continue

            # 2. Check if today is a Public Holiday / Global Leave on Calendar
            public_holiday = self.env['resource.calendar.leaves'].sudo().search([
                '|', ('calendar_id', '=', calendar.id), ('calendar_id', '=', False),
                ('resource_id', '=', False),
                ('date_from', '<=', end_utc),
                ('date_to', '>=', start_utc)
            ], limit=1)
            if public_holiday:
                continue

            # Calculate total approved leave hours for today (Full Day or Partial/Hourly Leave)
            approved_leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'validate'),
                ('request_date_from', '<=', today),
                ('request_date_to', '>=', today)
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
                # Fully covered by leave for today
                continue

            day_attendances = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', start_utc),
                ('check_in', '<=', end_utc)
            ])
            actual_hours = sum(att.worked_hours or 0.0 for att in day_attendances)

            if actual_hours < (net_required_hours - 0.05):
                shortfall_hours = net_required_hours - actual_hours
                shortfall_data.append({
                    'employee': employee,
                    'required_hours': required_hours,
                    'leave_hours': leave_hours,
                    'net_required_hours': net_required_hours,
                    'actual_hours': actual_hours,
                    'shortfall_hours': shortfall_hours,
                    'manager': employee.parent_id,
                    'manager_manager': employee.parent_id.parent_id if employee.parent_id else False,
                })

        if not shortfall_data:
            _logger.info("No attendance shortfall detected for today (%s).", today)
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
                act_str = self._format_float_time(item['actual_hours'])
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

            subject = f"[Attendance Shortfall Alert] Daily Attendance Shortfall Report ({today})"
            body_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
                <div style="background-color: #dc2626; padding: 15px 20px; border-radius: 8px 8px 0 0;">
                    <h3 style="color: #ffffff; margin: 0;">Daily Attendance Shortfall Alert</h3>
                </div>
                <div style="border: 1px solid #e2e8f0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; background: #ffffff;">
                    <p>Dear <strong>{mgr.name}</strong>,</p>
                    <p>The following team members under your reporting hierarchy logged fewer attendance hours than their net required working schedule today (<strong>{today}</strong>):</p>
                    
                    <table style="border-collapse: collapse; width: 100%; margin: 15px 0;">
                        <thead>
                            <tr style="background-color: #f8fafc; color: #1e293b; border-bottom: 2px solid #cbd5e1;">
                                <th style="padding: 10px; text-align: left;">Employee</th>
                                <th style="padding: 10px; text-align: left;">Reporting Type</th>
                                <th style="padding: 10px; text-align: center;">Schedule</th>
                                <th style="padding: 10px; text-align: center;">Approved Leave</th>
                                <th style="padding: 10px; text-align: center;">Net Required</th>
                                <th style="padding: 10px; text-align: center;">Actual Logged</th>
                                <th style="padding: 10px; text-align: center;">Shortfall</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>

                    <br/>
                    <p style="font-size: 12px; color: #777;">This is an automated nightly notification from Employee Self Service System.</p>
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
                _logger.error("Failed to send consolidated attendance shortfall report to %s: %s", mgr_email, str(e))
