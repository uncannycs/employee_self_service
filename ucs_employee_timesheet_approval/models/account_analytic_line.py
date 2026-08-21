# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountAnalyticLine(models.Model):
    """ Extension of analytic line to introduce timesheet approval workflow states (draft, confirm, approved, refused). """
    _inherit = 'account.analytic.line'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Submitted'),
        ('approved', 'Approved'),
        ('refused', 'Refused')
    ], string='Status', default='draft', required=True, copy=False)
    
    reject_reason = fields.Text(string='Reject Reason', copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        """ Override create to set approved state for leave-generated timesheet entries automatically. """
        for vals in vals_list:
            if vals.get('holiday_id'):
                vals['state'] = 'approved'
        lines = super(AccountAnalyticLine, self).create(vals_list)
        for line in lines:
            if line.holiday_id and line.state != 'approved':
                line.write({'state': 'approved'})
        return lines

    def action_submit(self):
        """ Submit draft timesheet entries for manager approval and trigger email notifications. """
        submittable_lines = self.filtered(lambda l: not getattr(l, 'holiday_id', False))
        for line in submittable_lines:
            if line.state != 'draft':
                raise UserError(_("Only draft timesheets can be submitted."))
            line.write({'state': 'confirm'})
        
        if submittable_lines:
            submittable_lines._send_timesheet_submit_email_to_manager()

    def _send_timesheet_submit_email_to_manager(self):
        """ Send consolidated email notification to the direct manager for submitted timesheets. """
        from itertools import groupby as py_groupby
        for employee, lines in py_groupby(self.sorted(key=lambda l: l.employee_id.id or 0), key=lambda l: l.employee_id):
            line_list = list(lines)
            if not employee:
                continue
            
            # Always use Direct Manager (parent_id)
            manager_user = employee.parent_id.user_id
            manager_email = (manager_user.email if manager_user else False) or (employee.parent_id.work_email if employee.parent_id else False)
            manager_name = (manager_user.name if manager_user else False) or (employee.parent_id.name if employee.parent_id else 'Manager')
            if not manager_email:
                continue

            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
            approval_url = f"{base_url}/my/approvals?tab=timesheet"

            rows_html = ""
            for line in line_list:
                rows_html += f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">{line.date}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{line.project_id.name or ''}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{line.task_id.name or '-'}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{line.name or ''}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{line.unit_amount:.2f} hrs</td>
                </tr>
                """

            subject = f"[Timesheet Approval Required] {employee.name} submitted timesheets for approval"
            body_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
                <h3 style="color: #6C5CE7;">Timesheet Approval Request</h3>
                <p>Dear <strong>{manager_name}</strong>,</p>
                <p><strong>{employee.name}</strong> has submitted the following timesheet(s) for your approval:</p>
                <table style="border-collapse: collapse; width: 100%; margin: 15px 0;">
                    <thead>
                        <tr style="background-color: #6C5CE7; color: white;">
                            <th style="padding: 8px; border: 1px solid #ddd;">Date</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">Project</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">Task</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">Description</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">Time Spent</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                <p style="margin-top: 20px;">
                    <a href="{approval_url}" style="background-color: #6C5CE7; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Review & Approve Timesheets in Portal
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
                import logging
                logging.getLogger(__name__).error("Failed to send Timesheet Submission Email to Manager: %s", str(e))

    def action_approve(self):
        for line in self.filtered(lambda l: not getattr(l, 'holiday_id', False)):
            line.write({'state': 'approved', 'reject_reason': False})

    def action_refuse(self, reason=''):
        for line in self.filtered(lambda l: not getattr(l, 'holiday_id', False)):
            line.write({'state': 'refused', 'reject_reason': reason})

    def action_reset_draft(self):
        for line in self.filtered(lambda l: not getattr(l, 'holiday_id', False)):
            line.write({'state': 'draft', 'reject_reason': False})

    # Prevent editing/deleting if not in draft
    def write(self, vals):
        # Allow state change regardless of state
        if len(vals) == 1 and ('state' in vals or 'reject_reason' in vals):
            return super(AccountAnalyticLine, self).write(vals)
            
        for line in self:
            if line.state in ['approved', 'refused'] and not self.env.su:
                raise UserError(_("You cannot modify an approved or refused timesheet."))
        return super(AccountAnalyticLine, self).write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approved(self):
        if self.env.context.get('leave_unlink'):
            return
        for line in self:
            if line.state in ['confirm', 'approved'] and not self.env.su:
                raise UserError(_("You cannot delete a submitted or approved timesheet."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_leave(self):
        if self.env.context.get('leave_unlink') or self.env.su:
            return
        return super(AccountAnalyticLine, self)._unlink_except_linked_leave()
