# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AttendanceRegularize(models.Model):
    _name = 'attendance.regularize'
    _description = 'Attendance Regularization Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New', tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, tracking=True, default=lambda self: self.env.user.employee_id)
    attendance_id = fields.Many2one('hr.attendance', string='Attendance', tracking=True)
    regularize_type = fields.Selection([
        ('check_in', 'Check-In'),
        ('check_out', 'Check-Out')
    ], string='Regularize Type', required=True, tracking=True)

    check_in_old = fields.Datetime(string='Old Check-In Time', tracking=True)
    check_in_new = fields.Datetime(string='New Check-In Time', tracking=True)
    
    check_out_old = fields.Datetime(string='Old Check-Out Time', tracking=True)
    check_out_new = fields.Datetime(string='New Check-Out Time', tracking=True)

    reason = fields.Text(string="Reason", required=True)

    manager_id = fields.Many2one('hr.employee', string="Manager", readonly=True)
    hr_id = fields.Many2one('res.users', string="HR Responsible", readonly=True)
    
    is_approve_manager = fields.Boolean(string="Is Manager Approved", copy=False)
    is_approve_hr = fields.Boolean(string="Is HR Approved", copy=False)
    
    manager_approved_time = fields.Datetime(string="Manager Approved Time", readonly=True, copy=False)
    hr_approved_time = fields.Datetime(string="HR Approved Time", readonly=True, copy=False)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('manager_approve', 'Manager Approved'),
        ('hr_approve', 'HR Approved'),
        ('reject', 'Rejected')
    ], string='Status', default='draft', tracking=True)

    manager_email = fields.Char(string='Manager Email', compute='_compute_manager_email')
    hr_admin_emails = fields.Char(string='HR Admin Emails', compute='_compute_hr_admin_emails')

    def _compute_manager_email(self):
        for rec in self:
            if rec.manager_id:
                rec.manager_email = rec.manager_id.work_email or (rec.manager_id.user_id.email if rec.manager_id.user_id else '')
            else:
                rec.manager_email = ''

    def _compute_hr_admin_emails(self):
        for rec in self:
            rec.hr_admin_emails = ''
            if rec.hr_id:
                hr_employee = self.env['hr.employee'].search([('user_id', '=', rec.hr_id.id)], limit=1)

                if hr_employee and hr_employee.work_email:
                    rec.hr_admin_emails = hr_employee.work_email
                elif rec.hr_id.email:
                    rec.hr_admin_emails = rec.hr_id.email
                elif rec.hr_id.login:
                    rec.hr_admin_emails = rec.hr_id.login

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('attendance.regularize') or 'New'
            
            if vals.get('employee_id'):
                employee = self.env['hr.employee'].browse(vals['employee_id'])
                if employee:
                    vals['manager_id'] = employee.parent_id.id
                    vals['hr_id'] = employee.hr_responsible_id.id

        return super(AttendanceRegularize, self).create(vals_list)
