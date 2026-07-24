# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
import urllib.parse
from odoo.addons.ucs_portal_self_service.controllers.timesheets import PortalCustomTimesheets, _is_timesheet_manager

class PortalCustomTimesheetsApproval(PortalCustomTimesheets):

    @http.route(['/my/timesheets/submit_range'], type='http', auth="user", methods=['POST'], website=True)
    def custom_timesheets_submit_range(self, **post):
        user = request.env.user
        date_from = post.get('date_from')
        date_to = post.get('date_to')
        
        if date_from and date_to:
            domain = [
                ('employee_id.user_id', '=', user.id),
                ('state', '=', 'draft'),
                ('date', '>=', date_from),
                ('date', '<=', date_to)
            ]
            my_draft_lines = request.env['account.analytic.line'].sudo().search(domain)
            
            if my_draft_lines:
                try:
                    my_draft_lines.action_submit()
                except Exception as e:
                    error_msg = str(e).replace('\n', ' ')
                    return request.redirect('/my/timesheets?error=' + urllib.parse.quote(error_msg))
        
        return request.redirect('/my/timesheets')

    @http.route(['/my/timesheets/submit/<int:line_id>'], type='http', auth="user", website=True)
    def custom_timesheets_submit_single(self, line_id, **kw):
        user = request.env.user
        line = request.env['account.analytic.line'].sudo().browse(line_id)
        
        if line.exists() and line.employee_id.user_id.id == user.id and line.state == 'draft':
            try:
                line.action_submit()
            except Exception as e:
                error_msg = str(e).replace('\n', ' ')
                return request.redirect('/my/timesheets?error=' + urllib.parse.quote(error_msg))
                
        return request.redirect('/my/timesheets')

    @http.route(['/my/timesheets/approve/<int:line_id>'], type='http', auth="user", website=True)
    def custom_timesheets_approve_single(self, line_id, **kw):
        user = request.env.user
        if _is_timesheet_manager(user):
            line = request.env['account.analytic.line'].sudo().browse(line_id)
            if line.exists() and line.state == 'confirm':
                if (line.employee_id and line.employee_id.user_id and line.employee_id.user_id.id == user.id) or (line.user_id and line.user_id.id == user.id):
                    error_msg = "You cannot approve your own timesheets."
                    return request.redirect('/my/timesheets?error=' + urllib.parse.quote(error_msg))
                try:
                    line.action_approve()
                except Exception as e:
                    error_msg = str(e).replace('\n', ' ')
                    return request.redirect('/my/timesheets?error=' + urllib.parse.quote(error_msg))
        return request.redirect('/my/timesheets')

    @http.route(['/my/timesheets/refuse'], type='http', auth="user", methods=['POST'], website=True)
    def custom_timesheets_refuse(self, **post):
        user = request.env.user
        if _is_timesheet_manager(user):
            line_id = int(post.get('line_id', 0))
            reason = post.get('reason', '').strip()
            if line_id and reason:
                line = request.env['account.analytic.line'].sudo().browse(line_id)
                if line.exists() and line.state == 'confirm':
                    if (line.employee_id and line.employee_id.user_id and line.employee_id.user_id.id == user.id) or (line.user_id and line.user_id.id == user.id):
                        error_msg = "You cannot refuse your own timesheets."
                        return request.redirect('/my/timesheets?error=' + urllib.parse.quote(error_msg))
                    try:
                        line.action_refuse(reason)
                    except Exception as e:
                        error_msg = str(e).replace('\n', ' ')
                        return request.redirect('/my/timesheets?error=' + urllib.parse.quote(error_msg))
        return request.redirect('/my/timesheets')

    @http.route(['/my/timesheets/edit'], type='http', auth="user", methods=['POST'], website=True)
    def custom_timesheets_edit(self, **post):
        user = request.env.user
        line_id = int(post.get('line_id', 0))
        if line_id:
            line = request.env['account.analytic.line'].sudo().browse(line_id)
            if line.exists() and line.employee_id.user_id.id == user.id and line.state != 'approved':
                date = post.get('date')
                unit_amount_str = post.get('unit_amount_str', '')
                name = post.get('name', '')
                
                unit_amount = 0.0
                if unit_amount_str:
                    try:
                        if ':' in unit_amount_str:
                            hours, minutes = unit_amount_str.split(':')
                            unit_amount = float(hours) + (float(minutes) / 60.0)
                        else:
                            unit_amount = float(unit_amount_str)
                    except ValueError:
                        unit_amount = 0.0
                
                if date and unit_amount > 0:
                    vals = {
                        'date': date,
                        'unit_amount': unit_amount,
                        'name': name,
                    }
                    if line.state == 'refused':
                        vals['state'] = 'draft' # Reset to draft so they can resubmit
                        
                    try:
                        line.write(vals)
                    except Exception as e:
                        request.env.cr.rollback()
                        import urllib.parse
                        error_msg = str(e).replace('\n', ' ')
                        return request.redirect('/my/timesheets?error=' + urllib.parse.quote(error_msg))
                        
        return request.redirect('/my/timesheets')
