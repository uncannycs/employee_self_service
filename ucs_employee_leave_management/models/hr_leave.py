# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class HrLeave(models.Model):
    """ Custom extension of hr.leave to automate emails and sync timesheet approval states. """
    _inherit = 'hr.leave'

    cancellation_requested = fields.Boolean(string="Cancellation Requested", default=False)
    cancellation_reason = fields.Text(string="Cancellation Reason")

    @api.model_create_multi
    def create(self, vals_list):
        """ Override create to send leave request email to manager and auto-approve past date leaves. """
        leaves = super(HrLeave, self).create(vals_list)
        today = fields.Date.today()
        now = fields.Datetime.now()
        for leave in leaves:
            leave._send_leave_request_email_to_manager()
            # If leave end date has passed, auto-approve it
            if leave.state in ['confirm', 'draft']:
                is_past = (leave.request_date_to and leave.request_date_to <= today) or (leave.date_to and leave.date_to <= now)
                if is_past:
                    try:
                        leave.sudo().action_approve()
                    except Exception as e:
                        _logger.error("Failed to auto-approve created past leave %s: %s", leave.id, str(e))
        return leaves

    @api.constrains('holiday_status_id', 'number_of_days', 'date_from', 'date_to', 'attachment_ids', 'supported_attachment_ids')
    def _check_mandatory_attachment(self):
        if self.env.context.get('skip_mandatory_attachment_check'):
            return
        for leave in self:
            lt = leave.holiday_status_id
            if not lt:
                continue
            is_sick = 'sick' in (lt.name or '').lower()
            is_mandatory = getattr(lt, 'mandatory_attachment', False) or getattr(lt, 'support_document', False) or is_sick
            raw_min = getattr(lt, 'mandatory_attachment_min_days', 2.0)
            min_days = float(raw_min or 2.0)
            
            calendar_days = 0.5 if (getattr(leave, 'request_unit_half', False) or getattr(leave, 'request_unit_hours', False)) else (
                (leave.request_date_to - leave.request_date_from).days + 1 if (leave.request_date_from and leave.request_date_to) else (
                    (leave.date_to.date() - leave.date_from.date()).days + 1 if (leave.date_from and leave.date_to) else 0.0
                )
            )
            duration = max(leave.number_of_days or 0.0, float(calendar_days))

            if is_mandatory and duration > min_days:
                atts = (
                    (hasattr(leave, 'supported_attachment_ids') and leave.supported_attachment_ids) or
                    (hasattr(leave, 'attachment_ids') and leave.attachment_ids) or
                    self.env['ir.attachment'].sudo().search([
                        ('res_model', '=', 'hr.leave'),
                        ('res_id', '=', leave.id)
                    ], limit=1)
                )
                if not atts:
                    raise ValidationError(_(
                        "Attachment is mandatory for '%s' when leave duration (%g days) exceeds %g days."
                    ) % (lt.name, duration, min_days))

    def action_approve(self, *args, **kwargs):
        """ Override action_approve to send notification email to employee and mark generated timesheets approved. """
        res = super(HrLeave, self).action_approve(*args, **kwargs)
        for leave in self:
            leave._send_leave_approval_email_to_employee()
            timesheets = self.env['account.analytic.line'].sudo().search([('holiday_id', '=', leave.id)])
            if timesheets:
                timesheets.write({'state': 'approved'})
        return res

    def action_validate(self, *args, **kwargs):
        """ Override action_validate to ensure linked timesheets state is set to approved. """
        res = super(HrLeave, self).action_validate(*args, **kwargs) if hasattr(super(HrLeave, self), 'action_validate') else True
        for leave in self:
            timesheets = self.env['account.analytic.line'].sudo().search([('holiday_id', '=', leave.id)])
            if timesheets:
                timesheets.write({'state': 'approved'})
        return res

    def _track_subtype(self, init_values):
        """ Override track subtype to suppress standard chatter tracking when validated. """
        if 'state' in init_values and self.state in ['validate', 'validate1']:
            return False
        return super(HrLeave, self)._track_subtype(init_values)

    def action_refuse(self, *args, **kwargs):
        """ Override action_refuse to send rejection email to employee and remove generated leave timesheets. """
        res = super(HrLeave, self).action_refuse(*args, **kwargs)
        for leave in self:
            leave._send_leave_refuse_email_to_employee()
            timesheets = self.env['account.analytic.line'].sudo().search([('holiday_id', '=', leave.id)])
            if timesheets:
                timesheets.with_context(leave_unlink=True).sudo().unlink()
        return res

    def write(self, vals):
        """ Override write to sync timesheet states when leave state changes. """
        res = super(HrLeave, self).write(vals)
        if 'state' in vals:
            if vals['state'] in ['validate', 'validate1']:
                timesheets = self.env['account.analytic.line'].sudo().search([('holiday_id', 'in', self.ids)])
                if timesheets:
                    timesheets.write({'state': 'approved'})
            elif vals['state'] in ['refuse', 'cancel', 'draft']:
                timesheets = self.env['account.analytic.line'].sudo().search([('holiday_id', 'in', self.ids)])
                if timesheets:
                    timesheets.with_context(leave_unlink=True).sudo().unlink()
        return res

    def unlink(self):
        timesheets = self.env['account.analytic.line'].sudo().search([('holiday_id', 'in', self.ids)])
        if timesheets:
            timesheets.with_context(leave_unlink=True).sudo().unlink()
        return super(HrLeave, self).unlink()

    @api.model
    def _cron_auto_approve_past_leaves(self):
        today = fields.Date.today()
        now = fields.Datetime.now()
        past_pending_leaves = self.search([
            ('state', '=', 'confirm'),
            '|',
            ('request_date_to', '<=', today),
            ('date_to', '<=', now)
        ])
        for leave in past_pending_leaves:
            try:
                leave.sudo().action_approve()
            except Exception as e:
                _logger.error("Failed to auto-approve past leave %s: %s", leave.id, str(e))

    def _get_next_states_by_state(self):
        state_result = super(HrLeave, self)._get_next_states_by_state()
        user = self.env.user
        
        def get_all_subordinates(emp):
            subs = emp.subordinate_ids
            all_subs = subs
            for sub in subs:
                all_subs |= get_all_subordinates(sub)
            return all_subs

        manager_emp = self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        subordinates = get_all_subordinates(manager_emp) if manager_emp else self.env['hr.employee'].sudo().browse()

        is_admin_or_manager = (
            user.has_group('base.group_erp_manager') or
            user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or
            user.has_group('ucs_employee_leave_management.group_portal_leave_approval_manager') or
            user.has_group('hr_holidays.group_hr_holidays_user') or
            user.has_group('hr_holidays.group_hr_holidays_responsible') or
            (self.employee_id and (
                self.employee_id.parent_id.user_id == user or 
                self.employee_id in subordinates
            ))
        )
        if is_admin_or_manager:
            state_result['validate'].add('refuse')
            state_result['validate1'].add('refuse')
            state_result['confirm'].add('refuse')
        return state_result

    def _send_leave_request_email_to_manager(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return
        
        manager = employee.parent_id.user_id
        manager_email = (manager.email if manager else False) or (employee.parent_id.work_email if employee.parent_id else False)
        if not manager_email:
            return

        date_from = self.request_date_from or (self.date_from.date() if self.date_from else '')
        date_to = self.request_date_to or (self.date_to.date() if self.date_to else '')
        leave_type = self.holiday_status_id.name or 'Leave'
        duration = f"{self.number_of_days} Day(s)" if self.number_of_days else f"{self.number_of_hours} Hour(s)"

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        approval_url = f"{base_url}/my/approvals?tab=leave"

        subject = f"[Leave Request] {employee.name} applied for {leave_type}"
        body_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
            <h3 style="color: #6C5CE7;">New Leave Request Received</h3>
            <p>Dear <strong>{manager.name or 'Manager'}</strong>,</p>
            <p>An employee has submitted a new leave request for your review:</p>
            <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin: 15px 0;">
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Employee:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{employee.name}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Leave Type:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{leave_type}</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Duration:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{date_from} to {date_to} ({duration})</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Reason / Description:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{self.name or 'N/A'}</td>
                </tr>
            </table>
            <p style="margin-top: 20px;">
                <a href="{approval_url}" style="background-color: #6C5CE7; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                    View & Approve in Portal
                </a>
            </p>
            <br/>
            <p style="font-size: 12px; color: #777;">This is an automated notification from Employee Self Service Portal.</p>
        </div>
        """

        try:
            mail_values = {
                'subject': subject,
                'email_from': self.env.company.email or self.env.user.email_formatted or 'noreply@company.com',
                'email_to': manager_email,
                'body_html': body_html,
                'state': 'outgoing',
            }
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
        except Exception as e:
            _logger.error("Failed to send Leave Request Email to Manager: %s", str(e))

    def _send_leave_approval_email_to_employee(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return
        
        employee_email = employee.user_id.email or employee.work_email or employee.private_email
        if not employee_email:
            return

        date_from = self.request_date_from or (self.date_from.date() if self.date_from else '')
        date_to = self.request_date_to or (self.date_to.date() if self.date_to else '')
        leave_type = self.holiday_status_id.name or 'Leave'
        duration = f"{self.number_of_days} Day(s)" if self.number_of_days else f"{self.number_of_hours} Hour(s)"

        subject = f"[Leave Approved] Your {leave_type} Request has been Approved"
        body_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
            <h3 style="color: #2ED573;">Leave Request Approved</h3>
            <p>Dear <strong>{employee.name}</strong>,</p>
            <p>Your leave request has been <strong style="color: #2ED573;">APPROVED</strong> by your manager.</p>
            <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin: 15px 0;">
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Leave Type:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{leave_type}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Duration:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{date_from} to {date_to} ({duration})</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Status:</td>
                    <td style="padding: 10px; border: 1px solid #ddd; color: #2ED573; font-weight: bold;">Approved</td>
                </tr>
            </table>
            <br/>
            <p style="font-size: 12px; color: #777;">This is an automated notification from Employee Self Service Portal.</p>
        </div>
        """

        try:
            mail_values = {
                'subject': subject,
                'email_from': self.env.company.email or self.env.user.email_formatted or 'noreply@company.com',
                'email_to': employee_email,
                'body_html': body_html,
                'state': 'outgoing',
            }
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
        except Exception as e:
            _logger.error("Failed to send Leave Approval Email to Employee: %s", str(e))

    def _send_leave_refuse_email_to_employee(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return
        
        employee_email = employee.user_id.email or employee.work_email or employee.private_email
        if not employee_email:
            return

        date_from = self.request_date_from or (self.date_from.date() if self.date_from else '')
        date_to = self.request_date_to or (self.date_to.date() if self.date_to else '')
        leave_type = self.holiday_status_id.name or 'Leave'
        duration = f"{self.number_of_days} Day(s)" if self.number_of_days else f"{self.number_of_hours} Hour(s)"

        subject = f"[Leave Refused] Your {leave_type} Request has been Refused"
        body_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
            <h3 style="color: #FF4757;">Leave Request Refused</h3>
            <p>Dear <strong>{employee.name}</strong>,</p>
            <p>Your leave request has been <strong style="color: #FF4757;">REFUSED / REJECTED</strong> by your manager.</p>
            <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin: 15px 0;">
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Leave Type:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{leave_type}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Duration:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{date_from} to {date_to} ({duration})</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Status:</td>
                    <td style="padding: 10px; border: 1px solid #ddd; color: #FF4757; font-weight: bold;">Refused</td>
                </tr>
            </table>
            <br/>
            <p style="font-size: 12px; color: #777;">This is an automated notification from Employee Self Service Portal.</p>
        </div>
        """

        try:
            mail_values = {
                'subject': subject,
                'email_from': self.env.company.email or self.env.user.email_formatted or 'noreply@company.com',
                'email_to': employee_email,
                'body_html': body_html,
                'state': 'outgoing',
            }
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
        except Exception as e:
            _logger.error("Failed to send Leave Refuse Email to Employee: %s", str(e))

    def action_request_cancellation(self, reason=None):
        for leave in self:
            vals = {'cancellation_requested': True}
            if reason:
                vals['cancellation_reason'] = reason
            leave.sudo().write(vals)
            leave._send_leave_cancellation_request_email_to_manager()

    def _send_leave_cancellation_request_email_to_manager(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return
        
        manager = employee.parent_id.user_id
        manager_email = (manager.email if manager else False) or (employee.parent_id.work_email if employee.parent_id else False)
        if not manager_email:
            return

        date_from = self.request_date_from or (self.date_from.date() if self.date_from else '')
        date_to = self.request_date_to or (self.date_to.date() if self.date_to else '')
        leave_type = self.holiday_status_id.name or 'Leave'
        duration = f"{self.number_of_days} Day(s)" if self.number_of_days else f"{self.number_of_hours} Hour(s)"

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        approval_url = f"{base_url}/my/approvals?tab=leave"

        cancel_reason_str = self.cancellation_reason or 'No reason provided.'

        subject = f"[Leave Cancellation Request] {employee.name} requested cancellation for {leave_type}"
        body_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
            <h3 style="color: #e67e22;">Leave Cancellation Request Received</h3>
            <p>Dear <strong>{manager.name or 'Manager'}</strong>,</p>
            <p>An employee has requested cancellation for an already approved leave request:</p>
            <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin: 15px 0;">
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Employee:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{employee.name}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Leave Type:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{leave_type}</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Duration:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{date_from} to {date_to} ({duration})</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">Original Reason:</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">{self.name or 'N/A'}</td>
                </tr>
                <tr style="background-color: #fff3cd;">
                    <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold; color: #856404;">Cancellation Reason:</td>
                    <td style="padding: 10px; border: 1px solid #ddd; color: #856404; font-weight: bold;">{cancel_reason_str}</td>
                </tr>
            </table>
            <p style="margin-top: 20px;">
                <a href="{approval_url}" style="background-color: #e67e22; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                    View & Approve Cancellation in Portal
                </a>
            </p>
            <br/>
            <p style="font-size: 12px; color: #777;">This is an automated notification from Employee Self Service Portal.</p>
        </div>
        """

        try:
            mail_values = {
                'subject': subject,
                'email_from': self.env.company.email or self.env.user.email_formatted or 'noreply@company.com',
                'email_to': manager_email,
                'body_html': body_html,
                'state': 'outgoing',
            }
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
        except Exception as e:
            _logger.error("Failed to send Leave Cancellation Request Email to Manager: %s", str(e))
