# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from datetime import datetime
import pytz
import urllib.parse

class AttendanceRegularizeController(http.Controller):

    @http.route(['/my/attendance/regularize_request'], type='http', auth="user", website=True, methods=['POST'])
    def submit_regularize_request(self, **post):
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)

        if not employee:
            return request.redirect('/my/attendance/history')

        attendance_id_str = post.get('attendance_id')
        regularize_type = post.get('regularize_type')
        reason = post.get('reason')

        check_in_new_time = post.get('check_in_new') # Format: HH:MM
        check_out_new_time = post.get('check_out_new') # Format: HH:MM

        if not attendance_id_str or not attendance_id_str.isdigit():
            return request.redirect('/my/attendance/history')
  
        attendance_id = int(attendance_id_str)
        attendance = request.env['hr.attendance'].sudo().search([('id', '=', attendance_id), ('employee_id', '=', employee.id)], limit=1)

        if not attendance:
            return request.redirect('/my/attendance/history?error=' + urllib.parse.quote("Invalid attendance record."))

        user_tz = pytz.timezone(user.tz or 'UTC')

        def combine_utc_date_with_local_time(utc_dt, time_str):
            if not utc_dt or not time_str:
                return False
            if ":" not in time_str:
                return False

            parts = time_str.split(':')
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                return False

            hour = int(parts[0])
            minute = int(parts[1])

            utc_dt_aware = pytz.utc.localize(utc_dt)
            local_dt = utc_dt_aware.astimezone(user_tz)

            new_local_dt = local_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)

            return new_local_dt.astimezone(pytz.utc).replace(tzinfo=None)

        vals = {
            'employee_id': employee.id,
            'attendance_id': attendance.id,
            'regularize_type': regularize_type,
            'reason': reason,
            'state': 'submit',
            'check_in_old': attendance.check_in,
            'check_out_old': attendance.check_out,
        }

        if employee.regularize_req_used >= employee.regularize_request_assign:
            return request.redirect('/my/attendance/history?error=' + urllib.parse.quote("You have exhausted your monthly regularization requests limit."))

        if regularize_type == 'check_in' and check_in_new_time:
            vals['check_in_new'] = combine_utc_date_with_local_time(attendance.check_in, check_in_new_time)
            if attendance.check_out and vals['check_in_new'] > attendance.check_out:
                return request.redirect('/my/attendance/history?error=' + urllib.parse.quote("Check-In time cannot be after Check-Out time."))
            last_att = request.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('check_in', '<', attendance.check_in),
                ('id', '!=', attendance.id)
            ], order='check_in desc', limit=1)
            if last_att and last_att.check_out and vals['check_in_new'] < last_att.check_out:
                return request.redirect('/my/attendance/history?error=' + urllib.parse.quote("The requested Check-In time overlaps with your previous attendance."))

        if regularize_type == 'check_out' and check_out_new_time:

            base_dt = attendance.check_out if attendance.check_out else attendance.check_in
            vals['check_out_new'] = combine_utc_date_with_local_time(base_dt, check_out_new_time)
            if vals['check_out_new'] < attendance.check_in:
                return request.redirect('/my/attendance/history?error=' + urllib.parse.quote("Check-Out time cannot be before Check-In time."))
            next_att = request.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('check_in', '>', attendance.check_in),
                ('id', '!=', attendance.id)
            ], order='check_in asc', limit=1)
            if next_att and vals['check_out_new'] > next_att.check_in:
                return request.redirect('/my/attendance/history?error=' + urllib.parse.quote("The requested Check-Out time overlaps with your next attendance."))

        reg = request.env['attendance.regularize'].sudo().create(vals)

        if reg.manager_id:
            template = request.env.ref('ucs_attendance_regularize.email_template_attendance_regularize_submit', raise_if_not_found=False)
            if template:
                template.sudo().send_mail(
                    reg.id,
                    force_send=True,
                    email_values={'email_to': reg.manager_email}
                )

        employee.sudo().write({'regularize_req_used': employee.regularize_req_used + 1})

        return request.redirect('/my/attendance/history')
