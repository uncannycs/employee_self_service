# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from datetime import datetime, timedelta
import pytz
import base64

def _get_employee(user):
    employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
    if not employee and user.login:
        employee = request.env['hr.employee'].sudo().search([('work_email', '=', user.login)], limit=1)
    return employee

class PortalCustomLeaves(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        return values

    @http.route(['/my/leaves', '/my/leaves/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_leaves(self, page=1, **kw):
        user = request.env.user
        employee = _get_employee(user)
        
        if not employee:
            return request.redirect('/my/dashboard')

        Leave = request.env['hr.leave'].sudo()
        domain = [('employee_id', '=', employee.id)]
        
        leave_count = Leave.search_count(domain)
        pager = portal_pager(
            url="/my/leaves",
            total=leave_count,
            page=page,
            step=self._items_per_page
        )
        
        leaves = Leave.search(domain, order="date_from desc", limit=self._items_per_page, offset=pager['offset'])
        leave_types = request.env['hr.leave.type'].sudo().search([('requires_allocation', '=', 'no')]) # Adjust based on requirement
        leave_types_raw = request.env['hr.leave.type'].sudo().search([('active', '=', True)])
        
        # Odoo Native Time Off Dashboard Logic
        leave_types_with_context = request.env['hr.leave.type'].sudo().with_context(
            employee_id=employee.id,
            allowed_company_ids=[employee.company_id.id]
        )
        domain = [
            ('active', '=', True),
            ('hide_on_dashboard', '=', False),
            ('requires_allocation', '=', 'yes'),
            '|', ('company_id', 'in', leave_types_with_context.env.context.get('allowed_company_ids')), ('company_id', '=', False),
            '|', ('country_id', '=', employee.company_id.country_id.id), ('country_id', '=', False)
        ]
        all_leave_types = leave_types_with_context.search(domain, order='id')
        alloc_data = all_leave_types.get_allocation_data(employee).get(employee, [])
        
        leave_balances = []
        for item in alloc_data:
            # item format: (name, data_dict, requires_allocation, id)
            name = item[0]
            data = item[1]
            
            leave_balances.append({
                'type_name': name,
                'allocated': data.get('max_leaves', 0.0),
                'taken': data.get('leaves_taken', 0.0),
                'remaining': data.get('virtual_remaining_leaves', 0.0),
                'request_unit': data.get('request_unit', 'day'),
                'icon': data.get('icon', ''),
            })
        
        # Types for the dropdown (allocations + no allocation needed types)
        valid_leave_type_ids = [item[3] for item in alloc_data]
        
        no_allocation_types = request.env['hr.leave.type'].sudo().search([
            ('active', '=', True),
            ('requires_allocation', '=', False),
            '|', ('company_id', '=', False), ('company_id', '=', employee.company_id.id),
            '|', ('country_id', '=', False), ('country_id', '=', employee.company_id.country_id.id)
        ])
        
        all_valid_ids = list(set(valid_leave_type_ids + no_allocation_types.ids))
        leave_types = request.env['hr.leave.type'].sudo().browse(all_valid_ids)
        
        # Subordinates & Team Leaves logic for Managers
        def get_all_subordinates(emp):
            subs = emp.subordinate_ids
            all_subs = subs
            for sub in subs:
                all_subs |= get_all_subordinates(sub)
            return all_subs

        subordinates = get_all_subordinates(employee)
        is_manager = bool(subordinates) or user.has_group('base.group_erp_manager') or user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or user.has_group('ucs_employee_leave_management.group_portal_leave_approval_manager')

        team_leaves = request.env['hr.leave'].sudo().browse()
        if is_manager:
            team_employees = (subordinates | employee) if subordinates else request.env['hr.employee'].sudo().search([('active', '=', True)])
            team_leaves = Leave.search([('employee_id', 'in', team_employees.ids)], order="date_from desc", limit=200)

        values = {
            'employee': employee,
            'leaves': leaves,
            'leave_types': leave_types,
            'leave_balances': leave_balances,
            'is_manager': is_manager,
            'team_leaves': team_leaves,
            'scope': kw.get('scope', 'my'),
            'page_name': 'leave',
            'pager': pager,
            'default_url': '/my/leaves',
            'csrf_token': request.csrf_token(),
            'error_message': kw.get('error'),
        }
        return request.render("ucs_employee_leave_management.portal_my_leaves", values)

    @http.route('/my/leaves/get_events', type='json', auth='user')
    def get_leave_events(self, start, end, **kw):
        user = request.env.user
        employee = _get_employee(user)
        if not employee:
            return []

        # Convert start and end strings (ISO format from fullcalendar) to datetime
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00')).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00')).replace(tzinfo=None)

        def get_all_subordinates(emp):
            subs = emp.subordinate_ids
            all_subs = subs
            for sub in subs:
                all_subs |= get_all_subordinates(sub)
            return all_subs

        subordinates = get_all_subordinates(employee)
        is_manager = bool(subordinates) or user.has_group('base.group_erp_manager') or user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or user.has_group('ucs_employee_leave_management.group_portal_leave_approval_manager')

        if is_manager:
            team_employees = (subordinates | employee) if subordinates else request.env['hr.employee'].sudo().search([('active', '=', True)])
            domain = [
                ('employee_id', 'in', team_employees.ids),
                ('date_from', '<', end_dt),
                ('date_to', '>=', start_dt),
                ('state', '!=', 'refuse')
            ]
        else:
            domain = [
                ('employee_id', '=', employee.id),
                ('date_from', '<', end_dt),
                ('date_to', '>=', start_dt),
                ('state', '!=', 'refuse')
            ]

        leaves = request.env['hr.leave'].sudo().search(domain)

        events = []
        for leave in leaves:
            color = '#3788d8' # blue for approved
            if leave.state in ['draft', 'confirm', 'validate1']:
                color = '#f39c12' # orange for pending
                
            state_label_map = {
                'draft': 'Pending',
                'confirm': 'Pending',
                'validate1': 'Pending',
                'validate': 'Approved',
                'refuse': 'Refused'
            }
            st_label = state_label_map.get(leave.state, leave.state.title())
            title = f"{leave.employee_id.name} - {leave.holiday_status_id.name} ({st_label})" if (is_manager and leave.employee_id != employee) else f"{leave.holiday_status_id.name} ({st_label})"
            
            atts = leave.supported_attachment_ids or leave.attachment_ids or request.env['ir.attachment'].sudo().search([('res_model', '=', 'hr.leave'), ('res_id', '=', leave.id)])
            att_list = [{'id': att.id, 'name': att.name} for att in atts]

            dt_from = leave.request_date_from or (leave.date_from.date() if leave.date_from else False)
            dt_to = leave.request_date_to or (leave.date_to.date() if leave.date_to else False)
            
            if dt_from and dt_to:
                start_str = dt_from.strftime('%Y-%m-%d')
                # FullCalendar allDay end is EXCLUSIVE, so add 1 day to include the final date
                end_str = (dt_to + timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                start_str = leave.date_from.strftime('%Y-%m-%d') if leave.date_from else ''
                end_str = (leave.date_to + timedelta(days=1)).strftime('%Y-%m-%d') if leave.date_to else ''

            events.append({
                'id': leave.id,
                'title': title,
                'start': start_str,
                'end': end_str,
                'color': color,
                'allDay': True,
                'description': leave.name or '',
                'leave_id': leave.id,
                'employee_id': leave.employee_id.id,
                'employee_name': leave.employee_id.name,
                'is_owner': bool(employee and leave.employee_id.id == employee.id),
                'holiday_status_id': leave.holiday_status_id.id,
                'holiday_status_name': leave.holiday_status_id.name,
                'state': leave.state,
                'date_from_val': dt_from.strftime('%Y-%m-%d') if dt_from else '',
                'date_to_val': dt_to.strftime('%Y-%m-%d') if dt_to else '',
                'request_unit_half': bool(leave.request_unit_half),
                'request_date_from_period': leave.request_date_from_period or 'am',
                'request_unit_hours': bool(leave.request_unit_hours),
                'number_of_days': leave.number_of_days,
                'number_of_hours': leave.number_of_hours,
                'reason': leave.name or '',
                'attachments': att_list,
            })
            
        # Public holidays
        holidays = request.env['resource.calendar.leaves'].sudo().search([
            ('date_from', '<', end_dt),
            ('date_to', '>=', start_dt),
            ('resource_id', '=', False)
        ])
        for holiday in holidays:
            h_from = holiday.date_from.date()
            h_to = holiday.date_to.date() + timedelta(days=1)
            events.append({
                'id': f'holiday_{holiday.id}',
                'title': holiday.name,
                'start': h_from.strftime('%Y-%m-%d'),
                'end': h_to.strftime('%Y-%m-%d'),
                'color': '#28a745',
                'allDay': True,
            })

        return events

    @http.route('/my/leaves/create', type='http', auth="user", methods=['POST'], website=True)
    def create_leave(self, **post):
        user = request.env.user
        employee = _get_employee(user)
        if not employee:
            return request.redirect('/my/dashboard')

        try:
            leave_type_id = int(post.get('holiday_status_id') or 0)
            date_from = post.get('date_from')
            date_to = post.get('date_to')
            name = post.get('name', '')
            is_half_day = post.get('request_unit_half') == 'True'
            half_day_period = post.get('request_date_from_period')
            partial_minutes = post.get('partial_minutes')
            partial_type = post.get('partial_type')
            
            leave_type = request.env['hr.leave.type'].sudo().browse(leave_type_id)
            is_hourly = leave_type.exists() and leave_type.request_unit == 'hour'
            
            if leave_type_id and date_from and (date_to or is_half_day or is_hourly):
                df = datetime.strptime(date_from, '%Y-%m-%d')
                dt = df if (is_half_day or is_hourly) else datetime.strptime(date_to, '%Y-%m-%d')
                
                # To avoid required field errors on date_from/date_to in some Odoo versions,
                # we provide them explicitly as naive datetimes (Odoo converts to UTC based on timezone later, 
                # or treats them as UTC. For full days, 00:00:00 to 23:59:59 is a safe fallback).
                start_dt = df.replace(hour=0, minute=0, second=0)
                end_dt = dt.replace(hour=23, minute=59, second=59)

                # Validate balance before creating
                leave_types_with_context = request.env['hr.leave.type'].sudo().with_context(
                    employee_id=employee.id,
                    allowed_company_ids=[employee.company_id.id]
                )
                domain = [
                    ('active', '=', True),
                    ('hide_on_dashboard', '=', False),
                    ('requires_allocation', '=', 'yes'),
                    '|', ('company_id', 'in', leave_types_with_context.env.context.get('allowed_company_ids')), ('company_id', '=', False),
                    '|', ('country_id', '=', employee.company_id.country_id.id), ('country_id', '=', False)
                ]
                all_leave_types = leave_types_with_context.search(domain, order='id')
                alloc_data = all_leave_types.get_allocation_data(employee).get(employee, [])
                
                temp_leave_vals = {
                    'employee_id': employee.id,
                    'holiday_status_id': leave_type_id,
                    'request_date_from': df.date(),
                    'request_date_to': dt.date(),
                }
                
                if is_half_day:
                    temp_leave_vals['request_unit_half'] = True
                    temp_leave_vals['request_date_from_period'] = half_day_period
                    temp_leave_vals['request_date_to_period'] = half_day_period
                elif is_hourly and partial_minutes:
                    mins = int(partial_minutes)
                    temp_leave_vals['request_unit_hours'] = True
                    request_hour_from = 9.0
                    request_hour_to = request_hour_from + (mins / 60.0)
                    
                    calendar = employee.resource_calendar_id
                    if calendar:
                        attendances = calendar.attendance_ids.filtered(lambda a: a.dayofweek == str(df.weekday()))
                        if attendances:
                            if partial_type == 'late':
                                first_att = attendances.sorted(key=lambda a: a.hour_from)[0]
                                request_hour_from = first_att.hour_from
                                request_hour_to = request_hour_from + (mins / 60.0)
                            else:
                                last_att = attendances.sorted(key=lambda a: a.hour_to, reverse=True)[0]
                                request_hour_to = last_att.hour_to
                                request_hour_from = request_hour_to - (mins / 60.0)
                                
                    temp_leave_vals['request_hour_from'] = request_hour_from
                    temp_leave_vals['request_hour_to'] = request_hour_to
                
                temp_leave = request.env['hr.leave'].sudo().new(temp_leave_vals)
                temp_leave._compute_date_from_to()
                temp_leave._compute_duration()
                
                for item in alloc_data:
                    if item[3] == leave_type_id:
                        requires_alloc = item[2]
                        if requires_alloc != 'no':
                            data = item[1]
                            remaining = data.get('virtual_remaining_leaves', 0.0)
                            unit = data.get('request_unit', 'day')
                            mins_hours = (int(partial_minutes) / 60.0) if (is_hourly and partial_minutes) else 0.0
                            requested = (temp_leave.number_of_hours or mins_hours) if unit == 'hour' else temp_leave.number_of_days
                            
                            if round(requested, 2) > round(remaining, 2):
                                if is_hourly and partial_minutes:
                                    remaining_mins = int(round(remaining * 60))
                                    requested_mins = int(partial_minutes)
                                    raise Exception(f"Insufficient leave balance. You only have {remaining_mins} minute(s) ({remaining} hour(s)) available, but requested {requested_mins} minute(s).")
                                elif unit == 'hour':
                                    raise Exception(f"Insufficient leave balance. You only have {remaining} hour(s) available, but requested {requested} hour(s).")
                                else:
                                    raise Exception(f"Insufficient leave balance. You only have {remaining} day(s) available, but requested {requested} day(s).")
                        break

                create_vals = {
                    'employee_id': employee.id,
                    'holiday_status_id': leave_type_id,
                    'request_date_from': df.date(),
                    'request_date_to': dt.date(),
                    'name': name,
                }
                if is_half_day:
                    create_vals['request_unit_half'] = True
                    create_vals['request_date_from_period'] = half_day_period
                    create_vals['request_date_to_period'] = half_day_period
                elif is_hourly and partial_minutes:
                    create_vals['request_unit_hours'] = True
                    create_vals['request_hour_from'] = temp_leave_vals['request_hour_from']
                    create_vals['request_hour_to'] = temp_leave_vals['request_hour_to']
                else:
                    create_vals['date_from'] = start_dt
                    create_vals['date_to'] = end_dt
                    
                leave_record = request.env['hr.leave'].sudo().create(create_vals)
                if leave_record.state == 'validate':
                    leave_record.sudo().write({'state': 'confirm'})

                # Save Uploaded Attachments & Link to hr.leave for backend & portal visibility
                files = request.httprequest.files.getlist('attachment')
                if not files:
                    file_single = request.httprequest.files.get('attachment')
                    if file_single:
                        files = [file_single]

                attachment_ids = []
                for file in files:
                    if file and getattr(file, 'filename', False):
                        file_data = file.read()
                        if file_data:
                            base64_data = base64.b64encode(file_data).decode('utf-8')
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': file.filename,
                                'datas': base64_data,
                                'res_model': 'hr.leave',
                                'res_id': leave_record.id,
                            })
                            attachment_ids.append(attachment.id)

                if attachment_ids:
                    if hasattr(leave_record, 'supported_attachment_ids'):
                        leave_record.sudo().write({'supported_attachment_ids': [(6, 0, attachment_ids)]})
                    if hasattr(leave_record, 'attachment_ids'):
                        leave_record.sudo().write({'attachment_ids': [(6, 0, attachment_ids)]})

                # Flush the environment to trigger any @api.constrains (like overlap checks)
                # so that the exception is caught here instead of at the end of the request.
                request.env.flush_all()
        except Exception as e:
            # Rollback the transaction to clear any aborted state
            request.env.cr.rollback()
            
            # Print the error to the server log so it can be debugged
            import logging
            logging.getLogger(__name__).error("Leave Creation Error: %s", str(e))
            # Redirect with error parameter so UI can show it
            import urllib.parse
            
            # Extract the meaningful part of the error if it's a ValidationError
            error_msg = str(e)
            if hasattr(e, 'args') and len(e.args) > 0:
                error_msg = str(e.args[0])
            
            error_msg = error_msg.replace('\n', ' ')
            return request.redirect('/my/leaves?error=' + urllib.parse.quote(error_msg))
            
        return request.redirect('/my/leaves')

    @http.route('/my/leaves/attachment/<int:attachment_id>', type='http', auth="user", website=True)
    def download_leave_attachment(self, attachment_id, **kw):
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id)
        if not attachment.exists():
            return request.not_found()

        user = request.env.user
        employee = _get_employee(user)

        leave = False
        if attachment.res_model == 'hr.leave' and attachment.res_id:
            leave = request.env['hr.leave'].sudo().browse(attachment.res_id)
        else:
            leave = request.env['hr.leave'].sudo().search([
                '|', ('supported_attachment_ids', 'in', attachment.id),
                     ('attachment_ids', 'in', attachment.id)
            ], limit=1)

        is_owner = (leave and employee and leave.employee_id.id == employee.id)
        is_manager = (leave and employee and leave.employee_id.parent_id.id == employee.id)
        is_admin = user.has_group('base.group_erp_manager') or user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin') or user.has_group('hr_holidays.group_hr_holidays_user')

        if not (is_owner or is_manager or is_admin):
            return request.redirect('/my/leaves?error=Unauthorized%20attachment%20access.')

        return request.redirect('/web/content/%s?download=true' % attachment.id)

    @http.route('/my/leaves/update/<int:leave_id>', type='http', auth="user", methods=['POST'], website=True)
    def update_leave(self, leave_id, **kw):
        user = request.env.user
        employee = _get_employee(user)
        if not employee:
            return request.redirect('/my/leaves?error=Employee%20record%20not%20found.')

        leave = request.env['hr.leave'].sudo().search([
            ('id', '=', leave_id),
            ('employee_id', '=', employee.id),
            ('state', 'in', ['draft', 'confirm', 'validate1'])
        ], limit=1)

        if not leave:
            return request.redirect('/my/leaves?error=Leave%20cannot%20be%20edited%20or%20is%20already%20processed.')

        post = request.httprequest.form
        try:
            leave_type_id = int(post.get('holiday_status_id') or 0)
            date_from = post.get('date_from')
            date_to = post.get('date_to')
            name = post.get('name', '')
            is_half_day = post.get('request_unit_half') == 'True'
            half_day_period = post.get('request_date_from_period')

            if leave_type_id and date_from:
                df = datetime.strptime(date_from, '%Y-%m-%d')
                dt = df if is_half_day else datetime.strptime(date_to or date_from, '%Y-%m-%d')

                update_vals = {
                    'holiday_status_id': leave_type_id,
                    'request_date_from': df.date(),
                    'request_date_to': dt.date(),
                    'date_from': df.replace(hour=0, minute=0, second=0),
                    'date_to': dt.replace(hour=23, minute=59, second=59),
                    'name': name,
                }

                if is_half_day:
                    update_vals['request_unit_half'] = True
                    update_vals['request_date_from_period'] = half_day_period
                    update_vals['request_date_to_period'] = half_day_period
                else:
                    update_vals['request_unit_half'] = False

                leave.sudo().write(update_vals)

                # Save new attachments if uploaded
                files = request.httprequest.files.getlist('attachment')
                if not files:
                    file_single = request.httprequest.files.get('attachment')
                    if file_single:
                        files = [file_single]

                attachment_ids = []
                for file in files:
                    if file and getattr(file, 'filename', False):
                        file_data = file.read()
                        if file_data:
                            base64_data = base64.b64encode(file_data).decode('utf-8')
                            attachment = request.env['ir.attachment'].sudo().create({
                                'name': file.filename,
                                'datas': base64_data,
                                'res_model': 'hr.leave',
                                'res_id': leave.id,
                            })
                            attachment_ids.append(attachment.id)

                if attachment_ids:
                    existing_atts = leave.supported_attachment_ids.ids if hasattr(leave, 'supported_attachment_ids') else []
                    all_atts = list(set(existing_atts + attachment_ids))
                    if hasattr(leave, 'supported_attachment_ids'):
                        leave.sudo().write({'supported_attachment_ids': [(6, 0, all_atts)]})
                    if hasattr(leave, 'attachment_ids'):
                        leave.sudo().write({'attachment_ids': [(6, 0, all_atts)]})

                request.env.flush_all()
        except Exception as e:
            request.env.cr.rollback()
            import logging
            logging.getLogger(__name__).error("Leave Update Error: %s", str(e))
            import urllib.parse
            error_msg = str(e)
            if hasattr(e, 'args') and len(e.args) > 0:
                error_msg = str(e.args[0])
            return request.redirect('/my/leaves?error=' + urllib.parse.quote(error_msg.replace('\n', ' ')))

        return request.redirect('/my/leaves')

    @http.route('/my/leaves/cancel/<int:leave_id>', type='http', auth="user", website=True)
    def cancel_leave(self, leave_id, **kw):
        user = request.env.user
        employee = _get_employee(user)
        
        domain = [('id', '=', leave_id)]
        is_admin = user.has_group('base.group_erp_manager') or user.has_group('ucs_employee_leave_management.group_portal_leave_approval_admin')
        is_mgr = user.has_group('ucs_employee_leave_management.group_portal_leave_approval_manager')
        if not (is_admin or is_mgr) and employee:
            domain.append(('employee_id', '=', employee.id))

        leave = request.env['hr.leave'].sudo().search(domain, limit=1)
        
        if leave:
            try:
                # In Odoo, refusing/cancelling a leave releases the allocated balance properly
                if hasattr(leave, 'action_refuse'):
                    leave.sudo().action_refuse()
                elif hasattr(leave, 'action_cancel'):
                    leave.sudo().action_cancel()
                else:
                    leave.sudo().write({'state': 'refuse'})
            except Exception as e:
                try:
                    leave.sudo().write({'state': 'refuse'})
                except Exception as ex:
                    import urllib.parse
                    error_msg = str(ex).replace('\n', ' ')
                    return request.redirect('/my/leaves?error=' + urllib.parse.quote(error_msg))
            
        return request.redirect('/my/leaves')
