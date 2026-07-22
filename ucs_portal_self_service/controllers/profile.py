# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
import urllib.parse

def _get_employee(user):
    employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
    if not employee and user.login:
        employee = request.env['hr.employee'].sudo().search([('work_email', '=', user.login)], limit=1)
    return employee

class PortalCustomProfile(CustomerPortal):

    @http.route(['/my/profile'], type='http', auth="user", website=True)
    def portal_my_profile(self, **kw):
        user = request.env.user
        employee = _get_employee(user)
        
        if not employee:
            return request.redirect('/my/dashboard')

        values = {
            'employee': employee,
            'page_name': 'profile',
            'csrf_token': request.csrf_token(),
            'success_message': kw.get('success'),
            'error_message': kw.get('error'),
        }
        return request.render("ucs_portal_self_service.portal_my_profile", values)

    @http.route(['/my/profile/update'], type='http', auth="user", methods=['POST'], website=True)
    def portal_my_profile_update(self, **post):
        user = request.env.user
        employee = _get_employee(user)
        
        if not employee:
            return request.redirect('/my/dashboard')

        try:
            # We only allow updating specific non-sensitive fields
            emergency_contact = post.get('emergency_contact')
            emergency_phone = post.get('emergency_phone')
            
            update_vals = {}
            if emergency_contact is not None:
                update_vals['emergency_contact'] = emergency_contact
            if emergency_phone is not None:
                update_vals['emergency_phone'] = emergency_phone
                
            if update_vals:
                employee.sudo().write(update_vals)
                
            return request.redirect('/my/profile?success=Profile updated successfully.')
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Profile Update Error: %s", str(e))
            error_msg = str(e).replace('\n', ' ')
            return request.redirect('/my/profile?error=' + urllib.parse.quote(error_msg))
