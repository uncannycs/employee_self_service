# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.ucs_portal_self_service.controllers.approvals import PortalApprovals
import urllib.parse

class LeavePortalApprovals(PortalApprovals):
    
    def _prepare_approvals_values(self):
        values = super()._prepare_approvals_values()
        
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not employee:
            return values

        Leave = request.env['hr.leave'].sudo()
        if user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin'):
            domain = [('state', '=', 'confirm')]
        else:
            domain = [('state', '=', 'confirm'), ('employee_id.leave_manager_id', '=', user.id)]
            
        leaves = Leave.search(domain, order="date_from desc")
        
        values.update({
            'leaves': leaves,
            'has_leave_approvals': True,
        })
        return values

    @http.route('/my/approvals/approve/<int:leave_id>', type='http', auth="user", website=True)
    def portal_approve_leave(self, leave_id, **kw):
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        
        Leave = request.env['hr.leave'].sudo()
        leave = Leave.browse(leave_id)
        
        if leave.exists() and leave.state == 'confirm':
            if user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or leave.employee_id.leave_manager_id.id == user.id:
                try:
                    leave.with_user(1).action_approve()
                    return request.redirect('/my/approvals?tab=leave')
                except Exception as e:
                    error_msg = str(e)
                    return request.redirect('/my/approvals?tab=leave&error=' + urllib.parse.quote(error_msg))
            else:
                return request.redirect('/my/approvals?tab=leave&error=' + urllib.parse.quote("You are not authorized to approve this leave."))
                
        return request.redirect('/my/approvals?tab=leave')

    @http.route('/my/approvals/refuse/<int:leave_id>', type='http', auth="user", website=True)
    def portal_refuse_leave(self, leave_id, **kw):
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        
        Leave = request.env['hr.leave'].sudo()
        leave = Leave.browse(leave_id)
        
        if leave.exists() and leave.state == 'confirm':
            if user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or leave.employee_id.leave_manager_id.id == user.id:
                try:
                    leave.with_user(1).action_refuse()
                    return request.redirect('/my/approvals?tab=leave')
                except Exception as e:
                    error_msg = str(e)
                    return request.redirect('/my/approvals?tab=leave&error=' + urllib.parse.quote(error_msg))
            else:
                return request.redirect('/my/approvals?tab=leave&error=' + urllib.parse.quote("You are not authorized to refuse this leave."))
                
        return request.redirect('/my/approvals?tab=leave')
