# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Submitted'),
        ('approved', 'Approved'),
        ('refused', 'Refused')
    ], string='Status', default='draft', required=True, copy=False, tracking=True)
    
    reject_reason = fields.Text(string='Reject Reason', copy=False)

    def action_submit(self):
        for line in self:
            if line.state != 'draft':
                raise UserError(_("Only draft timesheets can be submitted."))
            line.write({'state': 'confirm'})

    def action_approve(self):
        for line in self:
            if line.state != 'confirm':
                raise UserError(_("Only submitted timesheets can be approved."))
            line.write({'state': 'approved', 'reject_reason': False})

    def action_refuse(self, reason=''):
        for line in self:
            if line.state != 'confirm':
                raise UserError(_("Only submitted timesheets can be refused."))
            line.write({'state': 'refused', 'reject_reason': reason})

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
        for line in self:
            if line.state in ['confirm', 'approved'] and not self.env.su:
                raise UserError(_("You cannot delete a submitted or approved timesheet."))
