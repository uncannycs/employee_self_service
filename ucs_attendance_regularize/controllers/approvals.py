from odoo import fields, http
from odoo.http import request
from odoo.addons.ucs_portal_self_service.controllers.approvals import PortalApprovals
import urllib.parse

class RegularizePortalApprovals(PortalApprovals):
    def _prepare_approvals_values(self):
        values = super()._prepare_approvals_values()
        user = request.env.user
        
        if user.has_group('ucs_attendance_regularize.group_attendance_regularize_manager') or user.has_group('ucs_attendance_regularize.group_attendance_regularize_admin'):
            is_manager = user.has_group('ucs_attendance_regularize.group_attendance_regularize_manager')
            is_admin = user.has_group('ucs_attendance_regularize.group_attendance_regularize_admin')
            
            domain = [('state', 'in', ['submit', 'manager_approve'])]
            all_requests = request.env['attendance.regularize'].search(domain, order="create_date desc").sudo()
            
            final_requests = request.env['attendance.regularize']
            for req in all_requests:
                if req.state == 'submit' and is_manager:
                    # Check if it's a subordinate or self
                    if req.employee_id.parent_id.user_id == user or req.employee_id.user_id == user:
                        final_requests |= req
                elif req.state == 'manager_approve' and is_admin:
                    final_requests |= req
            
            pending_requests = final_requests
            
            values.update({
                'has_regularize_approvals': True,
                'regularize_requests': pending_requests,
                'regularize_check_in_count': len(pending_requests.filtered(lambda r: r.regularize_type == 'check_in')),
                'regularize_check_out_count': len(pending_requests.filtered(lambda r: r.regularize_type == 'check_out')),
                'regularize_total_count': len(pending_requests),
            })
            
        return values

    @http.route('/my/approvals/regularize/approve/<int:req_id>', type='http', auth="user", website=True)
    def approve_regularize(self, req_id, **kw):
        user = request.env.user
        is_manager = user.has_group('ucs_attendance_regularize.group_attendance_regularize_manager')
        is_admin = user.has_group('ucs_attendance_regularize.group_attendance_regularize_admin')
        
        if not (is_manager or is_admin):
            return request.redirect('/my/approvals?tab=regularize&error=' + urllib.parse.quote("You are not authorized to approve this request."))
            
        req = request.env['attendance.regularize'].browse(req_id)
        if req.exists():
            if req.state == 'submit' and is_manager and (req.employee_id.parent_id.user_id == user or req.employee_id.user_id == user):
                req.sudo().write({
                    'is_approve_manager': True,
                    'manager_approved_time': fields.Datetime.now(),
                    'state': 'manager_approve'
                })
            elif req.state == 'manager_approve' and is_admin:
                req.sudo().write({
                    'is_approve_hr': True,
                    'hr_approved_time': fields.Datetime.now(),
                    'state': 'hr_approve'
                })
        return request.redirect('/my/approvals?tab=regularize')

    @http.route('/my/approvals/regularize/reject/<int:req_id>', type='http', auth="user", website=True)
    def reject_regularize(self, req_id, **kw):
        user = request.env.user
        is_manager = user.has_group('ucs_attendance_regularize.group_attendance_regularize_manager')
        is_admin = user.has_group('ucs_attendance_regularize.group_attendance_regularize_admin')
        
        if not (is_manager or is_admin):
            return request.redirect('/my/approvals?tab=regularize&error=' + urllib.parse.quote("You are not authorized to reject this request."))
            
        req = request.env['attendance.regularize'].browse(req_id)
        if req.exists():
            if (req.state == 'submit' and is_manager and (req.employee_id.parent_id.user_id == user or req.employee_id.user_id == user)) or (req.state == 'manager_approve' and is_admin):
                req.sudo().write({
                    'state': 'reject'
                })
        return request.redirect('/my/approvals?tab=regularize')
