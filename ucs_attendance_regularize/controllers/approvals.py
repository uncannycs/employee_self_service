from odoo import fields, http
from odoo.http import request
from odoo.addons.ucs_portal_self_service.controllers.approvals import PortalApprovals
from datetime import timedelta
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
                    # Check if it's a subordinate (managers cannot approve their own requests)
                    if req.employee_id.parent_id.user_id == user:
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

        req = request.env['attendance.regularize'].sudo().browse(req_id)
        if req.exists():
            if req.state == 'submit' and is_manager and req.employee_id.parent_id.user_id == user:
                req.sudo().write({
                    'is_approve_manager': True,
                    'manager_approved_time': fields.Datetime.now(),
                    'state': 'manager_approve'
                })

                if req.hr_id or req.employee_id.company_id.email:
                    template = request.env.ref('ucs_attendance_regularize.email_template_attendance_regularize_manager_approve', raise_if_not_found=False)
                    if template:
                        template.sudo().send_mail(req.id, force_send=True)
            elif req.state == 'manager_approve' and is_admin:
                req.sudo().write({
                    'is_approve_hr': True,
                    'hr_approved_time': fields.Datetime.now(),
                    'state': 'hr_approve'
                })

                if req.attendance_id:
                    if req.regularize_type == 'check_in' and req.check_in_new:
                        check_in_val = req.check_in_new
                        last_att = request.env['hr.attendance'].sudo().search([
                            ('employee_id', '=', req.employee_id.id),
                            ('check_in', '<', req.attendance_id.check_in),
                            ('id', '!=', req.attendance_id.id)
                        ], order='check_in desc', limit=1)

                        if last_att and last_att.check_out and check_in_val < last_att.check_out:
                            return request.redirect('/my/approvals?tab=regularize&error=' + urllib.parse.quote("Approval failed: The new check-in time overlaps with a previous attendance record."))

                        if req.attendance_id.check_out and check_in_val >= req.attendance_id.check_out:
                            check_in_val = check_in_val - timedelta(days=1)
                            req.sudo().write({'check_in_new': check_in_val})

                        req.attendance_id.sudo().write({'check_in': check_in_val})

                    elif req.regularize_type == 'check_out' and req.check_out_new:
                        check_out_val = req.check_out_new
                        next_att = request.env['hr.attendance'].sudo().search([
                            ('employee_id', '=', req.employee_id.id),
                            ('check_in', '>', req.attendance_id.check_in),
                            ('id', '!=', req.attendance_id.id)
                        ], order='check_in asc', limit=1)

                        if next_att and check_out_val > next_att.check_in:
                            return request.redirect('/my/approvals?tab=regularize&error=' + urllib.parse.quote("Approval failed: The new check-out time overlaps with the next attendance record."))

                        if check_out_val <= req.attendance_id.check_in:
                            check_out_val = check_out_val + timedelta(days=1)
                            req.sudo().write({'check_out_new': check_out_val})

                        req.attendance_id.sudo().write({'check_out': check_out_val})
        return request.redirect('/my/approvals?tab=regularize')

    @http.route('/my/approvals/regularize/reject/<int:req_id>', type='http', auth="user", website=True)
    def reject_regularize(self, req_id, **kw):
        user = request.env.user
        is_manager = user.has_group('ucs_attendance_regularize.group_attendance_regularize_manager')
        is_admin = user.has_group('ucs_attendance_regularize.group_attendance_regularize_admin')

        if not (is_manager or is_admin):
            return request.redirect('/my/approvals?tab=regularize&error=' + urllib.parse.quote("You are not authorized to reject this request."))

        req = request.env['attendance.regularize'].sudo().browse(req_id)
        if req.exists():
            if (req.state == 'submit' and is_manager and req.employee_id.parent_id.user_id == user) or (req.state == 'manager_approve' and is_admin):
                req.sudo().write({
                    'state': 'reject'
                })

                if req.employee_id and req.employee_id.regularize_req_used > 0:
                    req.employee_id.sudo().write({'regularize_req_used': req.employee_id.regularize_req_used - 1})
        return request.redirect('/my/approvals?tab=regularize')
