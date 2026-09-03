import base64
import urllib.parse
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal

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
            update_vals = {}
            partner_vals = {}

            # Handle Profile Image File Upload & Deletion
            delete_profile_image = post.get('delete_profile_image')
            profile_image = post.get('profile_image') or request.httprequest.files.get('profile_image')

            if delete_profile_image == '1':
                employee.sudo().write({'image_1920': False})
                if user.partner_id:
                    user.partner_id.sudo().write({'image_1920': False})
                user.sudo().write({'image_1920': False})
            elif profile_image and getattr(profile_image, 'filename', False):
                image_data = profile_image.read()
                if image_data:
                    base64_str = base64.b64encode(image_data).decode('utf-8')
                    employee.sudo().write({'image_1920': base64_str})
                    if user.partner_id:
                        user.partner_id.sudo().write({'image_1920': base64_str})
                    user.sudo().write({'image_1920': base64_str})

            # Phone numbers
            work_phone = post.get('work_phone')
            mobile_phone = post.get('mobile_phone')
            emergency_contact = post.get('emergency_contact')
            emergency_phone = post.get('emergency_phone')

            if work_phone is not None:
                update_vals['work_phone'] = work_phone
                partner_vals['phone'] = work_phone
            if mobile_phone is not None:
                update_vals['mobile_phone'] = mobile_phone
                partner_vals['mobile'] = mobile_phone
            if emergency_contact is not None:
                update_vals['emergency_contact'] = emergency_contact
            if emergency_phone is not None:
                update_vals['emergency_phone'] = emergency_phone

            if update_vals:
                employee.sudo().write(update_vals)
                if user.partner_id and partner_vals:
                    valid_partner_fields = request.env['res.partner']._fields
                    safe_partner_vals = {k: v for k, v in partner_vals.items() if k in valid_partner_fields}
                    if safe_partner_vals:
                        user.partner_id.sudo().write(safe_partner_vals)

            return request.redirect('/my/profile?success=Profile details updated successfully.')
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Profile Update Error: %s", str(e))
            error_msg = str(e).replace('\n', ' ')
            return request.redirect('/my/profile?error=' + urllib.parse.quote(error_msg))
