# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal

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
        
        values = {
            'top_employee': top_employee,
            'current_employee': current_emp,
            'page_name': 'directory',
        }
        return request.render("ucs_portal_self_service.portal_employee_directory", values)
