# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.ucs_portal_self_service.controllers.approvals import PortalApprovals
import urllib.parse

class TimesheetPortalApprovals(PortalApprovals):
    
    def _prepare_approvals_values(self):
        values = super()._prepare_approvals_values()
        
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not employee:
            return values

        Line = request.env['account.analytic.line'].sudo()
        if user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_admin'):
            domain = [('state', '=', 'confirm'), ('project_id', '!=', False)]
        elif user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_manager'):
            domain = [
                ('state', '=', 'confirm'), 
                ('project_id', '!=', False),
                ('employee_id.parent_id.user_id', '=', user.id)
            ]
        else:
            # Not authorized to view approvals
            return values
            
        order = "employee_id, date desc"
        
        # Base domain for access
        Line = request.env['account.analytic.line'].sudo()
        
        # Extract possible employees and projects from base_domain for filter dropdowns
        all_timesheets = Line.search(domain)
        filter_employees = all_timesheets.mapped('employee_id').sorted(key=lambda x: x.name)
        filter_projects = all_timesheets.mapped('project_id').sorted(key=lambda x: x.name)
        
        # Now apply user selected filters
        filter_employee = request.params.get('filter_employee')
        filter_project = request.params.get('filter_project')
        filter_date_from = request.params.get('filter_date_from')
        filter_date_to = request.params.get('filter_date_to')
        
        if filter_employee:
            domain.append(('employee_id', '=', int(filter_employee)))
        if filter_project:
            domain.append(('project_id', '=', int(filter_project)))
        if filter_date_from:
            domain.append(('date', '>=', filter_date_from))
        if filter_date_to:
            domain.append(('date', '<=', filter_date_to))
                
        timesheets = Line.search(domain, order=order)
        
        from itertools import groupby as py_groupby
        grouped_timesheets = []
        for group_key, ts_group in py_groupby(timesheets, key=lambda x: x.employee_id):
            grouped_timesheets.append((group_key, list(ts_group)))
        
        values.update({
            'grouped_timesheets': grouped_timesheets,
            'timesheets': timesheets, # keep original for counts/checks if needed
            'has_timesheet_approvals': True if timesheets else False,
            'filter_employees': filter_employees,
            'filter_projects': filter_projects,
            'current_filter_employee': filter_employee or '',
            'current_filter_project': filter_project or '',
            'current_filter_date_from': filter_date_from or '',
            'current_filter_date_to': filter_date_to or '',
        })
        return values

    @http.route('/my/approvals/timesheet/approve/<int:line_id>', type='http', auth="user", website=True)
    def portal_approve_timesheet(self, line_id, **kw):
        user = request.env.user
        
        Line = request.env['account.analytic.line'].sudo()
        line = Line.browse(line_id)
        
        if line.exists() and line.state == 'confirm':
            is_admin = user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_admin')
            is_manager = line.employee_id.parent_id.user_id.id == user.id
            
            if is_admin or is_manager:
                try:
                    line.with_user(1).action_approve()
                    return request.redirect('/my/approvals?tab=timesheet')
                except Exception as e:
                    error_msg = str(e)
                    return request.redirect('/my/approvals?tab=timesheet&error=' + urllib.parse.quote(error_msg))
            else:
                return request.redirect('/my/approvals?tab=timesheet&error=' + urllib.parse.quote("You are not authorized to approve this timesheet."))
                
        return request.redirect('/my/approvals?tab=timesheet')

    @http.route('/my/approvals/timesheet/refuse/<int:line_id>', type='http', auth="user", website=True)
    def portal_refuse_timesheet(self, line_id, **kw):
        user = request.env.user
        reason = kw.get('reason', '')
        
        Line = request.env['account.analytic.line'].sudo()
        line = Line.browse(line_id)
        
        if line.exists() and line.state == 'confirm':
            is_admin = user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_admin')
            is_manager = line.employee_id.parent_id.user_id.id == user.id
            
            if is_admin or is_manager:
                try:
                    line.with_user(1).action_refuse(reason=reason)
                    return request.redirect('/my/approvals?tab=timesheet')
                except Exception as e:
                    error_msg = str(e)
                    return request.redirect('/my/approvals?tab=timesheet&error=' + urllib.parse.quote(error_msg))
            else:
                return request.redirect('/my/approvals?tab=timesheet&error=' + urllib.parse.quote("You are not authorized to refuse this timesheet."))
                
        return request.redirect('/my/approvals?tab=timesheet')
