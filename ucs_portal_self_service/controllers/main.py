# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from datetime import datetime, timezone, date
import pytz


def _get_employee(user):
    employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
    return employee


def _format_hours(hours):
    """Convert float hours to HH:MM format."""
    if not hours:
        return '00:00'
    total_seconds = int(round(hours * 3600))
    hrs = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    return f"{hrs:02d}:{mins:02d}"


def _to_user_time(dt_utc, user_tz):
    """Convert naive UTC datetime to user's local time string HH:MM."""
    if not dt_utc:
        return ''
    tz = pytz.timezone(user_tz or 'UTC')
    dt_aware = pytz.utc.localize(dt_utc)
    dt_local = dt_aware.astimezone(tz)
    return dt_local.strftime('%H:%M')


def _get_weekly_timesheet_info(user):
    employee = request.env['hr.employee'].sudo().search(['|', ('user_id', '=', user.id), ('work_email', '=', user.login)], limit=1)
    if not employee:
        return {}
    
    calendar = employee.resource_calendar_id or (employee.company_id and employee.company_id.resource_calendar_id)
    target_hours = 40.0
    if calendar:
        if hasattr(calendar, 'hours_per_week') and calendar.hours_per_week > 0:
            target_hours = float(calendar.hours_per_week)
        elif hasattr(calendar, 'full_time_required_hours') and calendar.full_time_required_hours > 0:
            target_hours = float(calendar.full_time_required_hours)

    from datetime import date, timedelta
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    timesheets = request.env['account.analytic.line'].sudo().search([
        ('employee_id', '=', employee.id),
        ('date', '>=', start_of_week),
        ('date', '<=', end_of_week),
    ])
    
    logged_hours = sum(ts.unit_amount for ts in timesheets)
    remaining_hours = max(0.0, target_hours - logged_hours)
    progress_pct = min(100.0, round((logged_hours / target_hours) * 100, 1)) if target_hours > 0 else 0.0
    
    def format_hrs(val):
        h = int(val)
        m = int(round((val - h) * 60))
        return f"{h:02d}:{m:02d}"

    return {
        'weekly_calendar_name': calendar.name if calendar else 'Standard Schedule',
        'weekly_target_hours': target_hours,
        'weekly_target_hours_str': format_hrs(target_hours),
        'weekly_logged_hours': logged_hours,
        'weekly_logged_hours_str': format_hrs(logged_hours),
        'weekly_remaining_hours': remaining_hours,
        'weekly_remaining_hours_str': format_hrs(remaining_hours),
        'weekly_progress_pct': progress_pct,
        'week_start_date': start_of_week.strftime('%d %b'),
        'week_end_date': end_of_week.strftime('%d %b %Y'),
    }


def _attendance_values(employee):
    """Return current attendance status for the employee."""
    user_tz = request.env.user.tz or 'UTC'
    tz = pytz.timezone(user_tz)
    now_utc = datetime.utcnow()
    now_local = pytz.utc.localize(now_utc).astimezone(tz)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local.astimezone(timezone.utc).replace(tzinfo=None)

    # Find open (currently checked-in) attendance
    open_att = request.env['hr.attendance'].sudo().search([
        ('employee_id', '=', employee.id),
        ('check_out', '=', False),
    ], limit=1)

    # Today's attendances (completed ones)
    today_atts = request.env['hr.attendance'].sudo().search([
        ('employee_id', '=', employee.id),
        ('check_in', '>=', today_start_utc),
    ])

    # Sum completed hours
    hours_today = sum(
        att.worked_hours for att in today_atts if att.check_out
    )

    # Add elapsed time of current open attendance
    check_in_time_str = ''
    check_in_unix = 0
    elapsed_seconds = 0
    if open_att and open_att.check_in:
        # check_in is naive UTC in Odoo
        import calendar
        check_in_unix = int(calendar.timegm(open_att.check_in.timetuple()))
        check_in_time_str = _to_user_time(open_att.check_in, user_tz)
        elapsed_seconds = int((now_utc - open_att.check_in).total_seconds())
        if elapsed_seconds > 0:
            hours_today += elapsed_seconds / 3600.0

    return {
        'is_checked_in': bool(open_att),
        'check_in_time': check_in_time_str,
        'hours_today': _format_hours(hours_today),
        'elapsed_seconds': elapsed_seconds,
        'check_in_unix': check_in_unix,  # UTC unix timestamp for JS
    }


class CustomCustomerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        return values

    @http.route(['/my', '/my/home'], type='http', auth="user", website=True)
    def home(self, **kw):
        return request.redirect('/my/dashboard')

    @http.route(['/my/dashboard'], type='http', auth="user", website=True)
    def employee_dashboard(self, **kw):
        user = request.env.user
        employee = _get_employee(user)

        # Base values for both employee and customer
        values = {
            'user': user,
            'is_employee': bool(employee),
            'employee': employee,
            'page_name': 'home',
            'csrf_token': request.csrf_token(),
            'error_message': kw.get('error'),
            'is_checked_in': False,
            'check_in_time': '',
            'hours_today': '0.00',
            'elapsed_seconds': 0,
            'check_in_unix': 0,
        }

        if employee:
            att = _attendance_values(employee)
            values.update(att)
            values.update(_get_weekly_timesheet_info(user))
            
            # Fetch Announcements for employees
            announcements = request.env['ucs.portal.announcement'].sudo().search([('active', '=', True)], order='date desc, id desc')
            values['announcements'] = announcements

            # Real logic for Upcoming Birthdays
            from datetime import date
            today = date.today()
            upcoming_birthdays = []
            
            employees_with_bday = request.env['hr.employee'].sudo().search([('birthday', '!=', False), ('active', '=', True)])
            
            for emp in employees_with_bday:
                bday = emp.birthday
                try:
                    next_bday = date(today.year, bday.month, bday.day)
                except ValueError:
                    next_bday = date(today.year, 3, 1)
                
                if next_bday < today:
                    try:
                        next_bday = date(today.year + 1, bday.month, bday.day)
                    except ValueError:
                        next_bday = date(today.year + 1, 3, 1)
                
                days_until = (next_bday - today).days
                if 0 <= days_until <= 30:
                    upcoming_birthdays.append({
                        'name': emp.name,
                        'date': next_bday.strftime('%d %B'),
                        'days_until': days_until,
                        'image_url': f'/web/image/hr.employee/{emp.id}/image_128'
                    })
            
            upcoming_birthdays.sort(key=lambda x: x['days_until'])
            values['upcoming_birthdays'] = upcoming_birthdays

            # Hierarchy Tasks Logic
            values['hierarchy_tasks'] = request.env['project.task'].sudo().browse()
            values['tasks_heading'] = "Task Deadlines"

            # Recursive function to get all subordinate employee ids
            def get_all_subordinates(emp):
                subs = emp.subordinate_ids
                all_subs = subs
                for sub in subs:
                    all_subs |= get_all_subordinates(sub)
                return all_subs

            all_emps = get_all_subordinates(employee) | employee
            allowed_user_ids = all_emps.mapped('user_id').ids

            if allowed_user_ids:
                domain = [
                    ('user_ids', 'in', allowed_user_ids),
                    ('state', 'not in', ['1_done', '04_canceled', '1_canceled', 'cancel', 'done']),
                    ('stage_id.is_done_stage', '=', False)
                ]
                
                from datetime import timedelta
                start_of_week = today - timedelta(days=today.weekday())
                end_of_week = start_of_week + timedelta(days=6)
                
                # Format to strings to safely compare with both Date and Datetime fields in ORM
                start_str = start_of_week.strftime('%Y-%m-%d 00:00:00')
                end_str = end_of_week.strftime('%Y-%m-%d 23:59:59')
                today_str = today.strftime('%Y-%m-%d 00:00:00')

                # 1. Current Week
                tasks_this_week = request.env['project.task'].sudo().search(
                    domain + [
                        ('date_deadline', '>=', start_str), 
                        ('date_deadline', '<=', end_str)
                    ], 
                    order='date_deadline asc'
                )
                
                if tasks_this_week:
                    values['hierarchy_tasks'] = tasks_this_week
                    values['tasks_heading'] = "This Week's Task Deadlines"
                else:
                    # 2. Upcoming (After this week)
                    tasks_future = request.env['project.task'].sudo().search(
                        domain + [('date_deadline', '>', end_str)], 
                        order='date_deadline asc'
                    )
                    if tasks_future:
                        values['hierarchy_tasks'] = tasks_future
                        values['tasks_heading'] = "Upcoming Task Deadlines"
                    else:
                        # 3. Recent/Overdue (Before this week)
                        tasks_recent = request.env['project.task'].sudo().search(
                            domain + [('date_deadline', '!=', False)], 
                            order='date_deadline desc'
                        )
                        values['hierarchy_tasks'] = tasks_recent
                        values['tasks_heading'] = "Recent Task Deadlines" if tasks_recent else "No Task Deadlines"

            # In-Progress Tasks Logic
            values['in_progress_tasks'] = request.env['project.task'].sudo().browse()
            if allowed_user_ids:
                in_progress_domain = [
                    ('user_ids', 'in', allowed_user_ids),
                    ('stage_id.is_in_progress_stage', '=', True)
                ]
                values['in_progress_tasks'] = request.env['project.task'].sudo().search(in_progress_domain, order='date_deadline asc')


            # Dummy data for Upcoming Events
            values['upcoming_events'] = [
                {
                    'name': 'Conference for Architects',
                    'date_str': 'Date: 2025-09-25 07:00:00 - 2025-09-25 16:30:00',
                    'venue': 'Venue: Los Angeles Convention Center'
                },
                {
                    'name': 'Design Fair Los Angeles',
                    'date_str': 'Date: 2025-09-30 08:00:00 - 2025-10-04 18:00:00',
                    'venue': 'Venue: Los Angeles Convention Center'
                }
            ]
        else:
            values['announcements'] = request.env['ucs.portal.announcement'].sudo().browse()
            values['upcoming_birthdays'] = []
            values['upcoming_events'] = []

        # Calculate total unread chats for the current user
        total_unread_chats = sum(request.env['discuss.channel.member'].sudo().search([
            ('partner_id', '=', user.partner_id.id),
            ('channel_id.channel_type', 'in', ['channel', 'group'])
        ]).mapped('message_unread_counter'))
        values['total_unread_chats'] = total_unread_chats

        return request.render('ucs_portal_self_service.employee_dashboard_layout', values)

    @http.route(['/my/attendance/history'], type='http', auth="user", website=True)
    def attendance_history(self, page=1, **kw):
        user = request.env.user
        employee = _get_employee(user)
        if not employee:
            return request.redirect('/my/dashboard')

        user_tz = user.tz or 'UTC'
        tz = pytz.timezone(user_tz)

        per_page = 20
        offset = (int(page) - 1) * per_page
        total = request.env['hr.attendance'].sudo().search_count([('employee_id', '=', employee.id)])

        attendances_raw = request.env['hr.attendance'].sudo().search(
            [('employee_id', '=', employee.id)],
            order='check_in desc',
            limit=per_page,
            offset=offset,
        )

        attendances = []
        for att in attendances_raw:
            ci_local = pytz.utc.localize(att.check_in).astimezone(tz) if att.check_in else None
            co_local = pytz.utc.localize(att.check_out).astimezone(tz) if att.check_out else None
            attendances.append({
                'check_in': ci_local.strftime('%d/%m/%Y %H:%M') if ci_local else '',
                'check_out': co_local.strftime('%d/%m/%Y %H:%M') if co_local else 'Ongoing',
                'worked_hours': _format_hours(att.worked_hours),
            })

        total_pages = (total + per_page - 1) // per_page

        values = {
            'employee': employee,
            'attendances': attendances,
            'page': int(page),
            'total_pages': total_pages,
        }
        return request.render('ucs_portal_self_service.portal_attendance_history', values)

    @http.route(['/my/attendance/toggle'], type='http', auth="user", website=True, methods=['POST'])
    def toggle_attendance(self, **kw):
        user = request.env.user
        employee = _get_employee(user)
        if employee:
            try:
                employee.sudo()._attendance_action_change()
                request.env.flush_all()
            except Exception as e:
                request.env.cr.rollback()
                import urllib.parse
                error_msg = str(e).replace('\n', ' ')
                return request.redirect('/my/dashboard?error=' + urllib.parse.quote(error_msg))
        return request.redirect('/my/dashboard')
