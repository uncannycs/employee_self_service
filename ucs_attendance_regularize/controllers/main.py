# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from datetime import datetime
import pytz

class AttendanceRegularizeController(http.Controller):

    @http.route(['/my/attendance/regularize_request'], type='http', auth="user", website=True, methods=['POST'])
    def submit_regularize_request(self, **post):
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        
        if not employee:
            return request.redirect('/my/attendance/history')
            
        attendance_id = post.get('attendance_id')
        regularize_type = post.get('regularize_type')
        reason = post.get('reason')
        
        check_in_old_str = post.get('check_in_old') # Format: DD/MM/YYYY HH:MM
        check_out_old_str = post.get('check_out_old') # Format: DD/MM/YYYY HH:MM or 'Ongoing'
        
        check_in_new_time = post.get('check_in_new') # Format: HH:MM
        check_out_new_time = post.get('check_out_new') # Format: HH:MM
        
        user_tz = pytz.timezone(user.tz or 'UTC')
        
        def parse_local_to_utc(date_str, time_str):
            if not date_str or not time_str:
                return False
            # date_str is expected to be from the old time like "DD/MM/YYYY HH:MM"
            # We only need "DD/MM/YYYY"
            try:
                date_part = date_str.split(' ')[0]
                dt_str = f"{date_part} {time_str}"
                local_dt = datetime.strptime(dt_str, '%d/%m/%Y %H:%M')
                local_dt = user_tz.localize(local_dt)
                utc_dt = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
                return utc_dt
            except Exception as e:
                return False
                
        def parse_old_to_utc(dt_str):
            if not dt_str or dt_str == 'Ongoing':
                return False
            try:
                local_dt = datetime.strptime(dt_str, '%d/%m/%Y %I:%M %p')
                local_dt = user_tz.localize(local_dt)
                utc_dt = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
                return utc_dt
            except Exception as e:
                return False

        vals = {
            'employee_id': employee.id,
            'regularize_type': regularize_type,
            'reason': reason,
            'state': 'submit',
        }
        
        # Check quota
        if employee.regularize_req_used >= employee.regularize_request_assign:
            import urllib.parse
            return request.redirect('/my/attendance/history?error=' + urllib.parse.quote("You have exhausted your monthly regularization requests limit."))
        
        if attendance_id:
            vals['attendance_id'] = int(attendance_id)
            
        vals['check_in_old'] = parse_old_to_utc(check_in_old_str)
        vals['check_out_old'] = parse_old_to_utc(check_out_old_str)
        
        if regularize_type == 'check_in' and check_in_new_time:
            vals['check_in_new'] = parse_local_to_utc(check_in_old_str, check_in_new_time)
            
        if regularize_type == 'check_out' and check_out_new_time:
            # If it's ongoing, we might not have a check_out date, so fallback to check_in date
            base_date_str = check_out_old_str if check_out_old_str and check_out_old_str != 'Ongoing' else check_in_old_str
            vals['check_out_new'] = parse_local_to_utc(base_date_str, check_out_new_time)
            
        # Create record
        request.env['attendance.regularize'].sudo().create(vals)
        
        # Increment used quota
        employee.sudo().write({'regularize_req_used': employee.regularize_req_used + 1})
        
        return request.redirect('/my/attendance/history')
