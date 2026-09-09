# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from datetime import date

class PortalEmployeeDirectory(CustomerPortal):

    @http.route(['/my/directory'], type='http', auth="user", website=True)
    def portal_my_directory(self, **kw):
        user = request.env.user
        
        # Ensure the user has an employee record to view the directory (basic check)
        current_emp = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not current_emp and user.login:
            current_emp = request.env['hr.employee'].sudo().search([('work_email', '=', user.login)], limit=1)
            
        if not current_emp:
            return request.redirect('/my/dashboard')

        # Get the manager to start the chart from, or self if no manager
        top_employee = current_emp.parent_id if current_emp.parent_id else current_emp
        
        # Fetch employee IDs on approved leave today
        today = date.today()
        leaves_today = request.env['hr.leave'].sudo().search([
            ('state', '=', 'validate'),
            ('request_date_from', '<=', today),
            ('request_date_to', '>=', today)
        ])
        employees_on_leave_ids = set(leaves_today.mapped('employee_id').ids)

        values = {
            'top_employee': top_employee,
            'current_employee': current_emp,
            'employees_on_leave_ids': employees_on_leave_ids,
            'page_name': 'directory',
        }
        return request.render("ucs_portal_self_service.portal_employee_directory", values)
