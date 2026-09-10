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

        is_admin = (
            user.has_group('base.group_erp_manager') or
            user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_admin') or
            user.has_group('hr_timesheet.group_timesheet_manager') or
            user.has_group('hr_timesheet.group_hr_timesheet_approver')
        )

        Line = request.env['account.analytic.line'].sudo()
        if is_admin:
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
            is_admin = (
                user.has_group('base.group_erp_manager') or
                user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_admin') or
                user.has_group('hr_timesheet.group_timesheet_manager') or
                user.has_group('hr_timesheet.group_hr_timesheet_approver')
            )
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
        
        Line = request.env['account.analytic.line'].sudo()
        line = Line.browse(line_id)
        
        if line.exists() and line.state == 'confirm':
            is_admin = (
                user.has_group('base.group_erp_manager') or
                user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_admin') or
                user.has_group('hr_timesheet.group_timesheet_manager') or
                user.has_group('hr_timesheet.group_hr_timesheet_approver')
            )
            is_manager = line.employee_id.parent_id.user_id.id == user.id
            
            if is_admin or is_manager:
                try:
                    reason = kw.get('reason') or kw.get('reject_reason') or ''
                    line.sudo().action_refuse(reason=reason)
                    return request.redirect('/my/approvals?tab=timesheet')
                except Exception as e:
                    error_msg = str(e)
                    return request.redirect('/my/approvals?tab=timesheet&error=' + urllib.parse.quote(error_msg))
            else:
                return request.redirect('/my/approvals?tab=timesheet&error=' + urllib.parse.quote("You are not authorized to refuse this timesheet."))
                
        return request.redirect('/my/approvals?tab=timesheet')

    @http.route('/my/approvals/timesheet/bulk_action', type='jsonrpc', auth="user", methods=['POST'], website=True, csrf=False)
    def portal_bulk_timesheet_action(self, action=None, timesheet_ids=None, reason='', **kw):
        user = request.env.user
        ts_ids = []
        if isinstance(timesheet_ids, (list, tuple)):
            for x in timesheet_ids:
                try:
                    ts_ids.append(int(x))
                except (ValueError, TypeError):
                    pass
        elif timesheet_ids:
            try:
                ts_ids.append(int(timesheet_ids))
            except (ValueError, TypeError):
                pass

        processed = 0
        if ts_ids and action in ['approve', 'refuse']:
            lines = request.env['account.analytic.line'].sudo().browse(ts_ids)
            is_admin = (
                user.has_group('base.group_erp_manager') or
                user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_admin') or
                user.has_group('hr_timesheet.group_timesheet_manager') or
                user.has_group('hr_timesheet.group_hr_timesheet_approver')
            )
            for line in lines:
                if line.exists() and line.state == 'confirm':
                    is_manager = line.employee_id.parent_id.user_id.id == user.id
                    if is_admin or is_manager:
                        try:
                            if action == 'approve':
                                line.sudo().action_approve()
                            elif action == 'refuse':
                                line.sudo().action_refuse(reason=reason or '')
                            processed += 1
                        except Exception as e:
                            import logging
                            logging.getLogger(__name__).error("Bulk action failed for line %s: %s", line.id, str(e))

        return {'success': True, 'processed': processed}

