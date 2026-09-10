# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.ucs_portal_self_service.controllers.approvals import PortalApprovals
import urllib.parse

class LeavePortalApprovals(PortalApprovals):
    
    def _prepare_approvals_values(self):
        values = super()._prepare_approvals_values()
        user = request.env.user

        is_admin_or_manager = (
            user.has_group('base.group_erp_manager') or
            user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or
            user.has_group('hr_holidays.group_hr_holidays_user') or
            user.has_group('hr_holidays.group_hr_holidays_responsible')
        )

        Leave = request.env['hr.leave'].sudo()
        if is_admin_or_manager:
            domain = ['|', ('state', '=', 'confirm'), ('cancellation_requested', '=', True)]
        else:
            domain = [('employee_id.parent_id.user_id', '=', user.id), '|', ('state', '=', 'confirm'), ('cancellation_requested', '=', True)]
            
        leaves = Leave.search(domain, order="date_from desc")
        
        values.update({
            'leaves': leaves,
            'has_leave_approvals': True,
        })
        return values

    @http.route('/my/approvals/approve/<int:leave_id>', type='http', auth="user", website=True)
    def portal_approve_leave(self, leave_id, **kw):
        user = request.env.user
        Leave = request.env['hr.leave'].sudo()
        leave = Leave.browse(leave_id)
        
        is_admin_or_manager = (
            user.has_group('base.group_erp_manager') or
            user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or
            user.has_group('hr_holidays.group_hr_holidays_user') or
            user.has_group('hr_holidays.group_hr_holidays_responsible')
        )

        if leave.exists() and leave.state == 'confirm':
            if is_admin_or_manager or leave.employee_id.parent_id.user_id.id == user.id:
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
        Leave = request.env['hr.leave'].sudo()
        leave = Leave.browse(leave_id)
        redirect_url = kw.get('redirect', '/my/approvals?tab=leave')
        
        is_admin_or_manager = (
            user.has_group('base.group_erp_manager') or
            user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or
            user.has_group('hr_holidays.group_hr_holidays_user') or
            user.has_group('hr_holidays.group_hr_holidays_responsible')
        )

        def get_all_subordinates(emp):
            subs = emp.subordinate_ids
            all_subs = subs
            for sub in subs:
                all_subs |= get_all_subordinates(sub)
            return all_subs

        manager_emp = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        subordinates = get_all_subordinates(manager_emp) if manager_emp else request.env['hr.employee'].sudo().browse()

        is_authorized = (
            is_admin_or_manager or
            leave.employee_id.parent_id.user_id.id == user.id or
            leave.employee_id.id in subordinates.ids
        )

        if leave.exists() and leave.state in ['confirm', 'validate', 'validate1']:
            if is_authorized:
                try:
                    leave.sudo().action_refuse()
                    return request.redirect(redirect_url)
                except Exception as e:
                    error_msg = str(e)
                    sep = '&' if '?' in redirect_url else '?'
                    return request.redirect(redirect_url + sep + 'error=' + urllib.parse.quote(error_msg))
            else:
                sep = '&' if '?' in redirect_url else '?'
                return request.redirect(redirect_url + sep + 'error=' + urllib.parse.quote("You are not authorized to refuse this leave."))
                
        return request.redirect(redirect_url)

    @http.route('/my/approvals/cancellation/approve/<int:leave_id>', type='http', auth="user", website=True)
    def portal_approve_cancellation(self, leave_id, **kw):
        user = request.env.user
        Leave = request.env['hr.leave'].sudo()
        leave = Leave.browse(leave_id)
        
        is_admin_or_manager = (
            user.has_group('base.group_erp_manager') or
            user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or
            user.has_group('hr_holidays.group_hr_holidays_user') or
            user.has_group('hr_holidays.group_hr_holidays_responsible')
        )

        def get_all_subordinates(emp):
            subs = emp.subordinate_ids
            all_subs = subs
            for sub in subs:
                all_subs |= get_all_subordinates(sub)
            return all_subs

        manager_emp = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        subordinates = get_all_subordinates(manager_emp) if manager_emp else request.env['hr.employee'].sudo().browse()

        is_authorized = (
            is_admin_or_manager or
            leave.employee_id.parent_id.user_id.id == user.id or
            leave.employee_id.id in subordinates.ids
        )

        if leave.exists() and leave.cancellation_requested:
            if is_authorized:
                try:
                    # Approve cancellation: Refuse/Cancel the leave to restore leave balance automatically
                    if hasattr(leave, 'action_refuse'):
                        leave.sudo().action_refuse()
                    elif hasattr(leave, 'action_cancel'):
                        leave.sudo().action_cancel()
                    else:
                        leave.sudo().write({'state': 'refuse'})
                    leave.sudo().write({'cancellation_requested': False})
                    return request.redirect('/my/approvals?tab=leave')
                except Exception as e:
                    error_msg = str(e)
                    return request.redirect('/my/approvals?tab=leave&error=' + urllib.parse.quote(error_msg))
            else:
                return request.redirect('/my/approvals?tab=leave&error=' + urllib.parse.quote("You are not authorized to approve this cancellation request."))
                
        return request.redirect('/my/approvals?tab=leave')

    @http.route('/my/approvals/cancellation/reject/<int:leave_id>', type='http', auth="user", website=True)
    def portal_reject_cancellation(self, leave_id, **kw):
        user = request.env.user
        Leave = request.env['hr.leave'].sudo()
        leave = Leave.browse(leave_id)
        
        is_admin_or_manager = (
            user.has_group('base.group_erp_manager') or
            user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or
            user.has_group('hr_holidays.group_hr_holidays_user') or
            user.has_group('hr_holidays.group_hr_holidays_responsible')
        )

        def get_all_subordinates(emp):
            subs = emp.subordinate_ids
            all_subs = subs
            for sub in subs:
                all_subs |= get_all_subordinates(sub)
            return all_subs

        manager_emp = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        subordinates = get_all_subordinates(manager_emp) if manager_emp else request.env['hr.employee'].sudo().browse()

        is_authorized = (
            is_admin_or_manager or
            leave.employee_id.parent_id.user_id.id == user.id or
            leave.employee_id.id in subordinates.ids
        )

        if leave.exists() and leave.cancellation_requested:
            if is_authorized:
                try:
                    # Reject cancellation: clear request flag, keep leave validated/approved
                    leave.sudo().write({'cancellation_requested': False})
                    return request.redirect('/my/approvals?tab=leave')
                except Exception as e:
                    error_msg = str(e)
                    return request.redirect('/my/approvals?tab=leave&error=' + urllib.parse.quote(error_msg))
            else:
                return request.redirect('/my/approvals?tab=leave&error=' + urllib.parse.quote("You are not authorized to reject this cancellation request."))
                
        return request.redirect('/my/approvals?tab=leave')
