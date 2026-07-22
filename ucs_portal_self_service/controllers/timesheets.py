# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.hr_timesheet.controllers.portal import TimesheetCustomerPortal

class PortalCustomTimesheets(TimesheetCustomerPortal):

    @http.route(['/my/timesheets', '/my/timesheets/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_timesheets(self, page=1, sortby=None, filterby=None, search=None, search_in='all', groupby='none', **kw):
        user = request.env.user
        is_employee = bool(request.env['hr.employee'].sudo().search(['|', ('user_id', '=', user.id), ('work_email', '=', user.login)], limit=1))
        if not is_employee:
            return request.redirect('/my')
            
        # We override the base route to inject 'projects' into the template for our modal dropdown
        response = super().portal_my_timesheets(page, sortby, filterby, search, search_in, groupby, **kw)
        if hasattr(response, 'qcontext'):
            # Fetch projects the user has access to, for the "Log Time" modal dropdown
            response.qcontext['projects'] = request.env['project.project'].search([])
            response.qcontext['csrf_token'] = request.csrf_token()
            response.qcontext['error_message'] = kw.get('error')
        return response

    @http.route(['/my/timesheets/create'], type='http', auth="user", methods=['POST'], website=True)
    def custom_timesheets_create(self, **post):
        user = request.env.user
        is_employee = bool(request.env['hr.employee'].sudo().search(['|', ('user_id', '=', user.id), ('work_email', '=', user.login)], limit=1))
        if not is_employee:
            return request.redirect('/my/timesheets')
            
        project_id = int(post.get('project_id', 0))
        task_id = int(post.get('task_id', 0)) or False
        date = post.get('date')
        unit_amount_str = post.get('unit_amount_str', '')
        unit_amount = 0.0
        
        if unit_amount_str:
            try:
                if ':' in unit_amount_str:
                    hours, minutes = unit_amount_str.split(':')
                    unit_amount = float(hours) + (float(minutes) / 60.0)
                else:
                    unit_amount = float(unit_amount_str)
            except ValueError:
                unit_amount = 0.0
                
        name = post.get('name', '')
        if project_id and date and unit_amount > 0:
            user = request.env.user
            employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
            
            vals = {
                'project_id': project_id,
                'task_id': task_id,
                'date': date,
                'unit_amount': unit_amount,
                'name': name,
            }
            if employee:
                vals['employee_id'] = employee.id
                
            try:
                request.env['account.analytic.line'].sudo().create(vals)
                request.env.flush_all()
            except Exception as e:
                request.env.cr.rollback()
                import urllib.parse
                error_msg = str(e).replace('\n', ' ')
                redirect_to = post.get('redirect_to', '/my/timesheets')
                sep = '&' if '?' in redirect_to else '?'
                return request.redirect(f"{redirect_to}{sep}error={urllib.parse.quote(error_msg)}")
            
        redirect_to = post.get('redirect_to', '/my/timesheets')
        return request.redirect(redirect_to)

    @http.route('/my/timesheets/get_tasks_by_project', type='json', auth='user')
    def get_tasks_by_project(self, project_id, **kw):
        user = request.env.user
        project_id = int(project_id) if project_id else 0
        
        # Let base Odoo rules filter the tasks
        tasks = request.env['project.task'].search([('project_id', '=', project_id)])

        return [{'id': t.id, 'name': t.name} for t in tasks]
