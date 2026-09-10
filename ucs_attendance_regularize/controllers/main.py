# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from datetime import datetime, date, time, timedelta
import calendar
import pytz
import urllib.parse
import io
import xlsxwriter


def _format_hrs(hours):
    if not hours or hours <= 0:
        return '00h 00m'
    total_seconds = int(round(hours * 3600))
    hrs = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    return f"{hrs:02d}h {mins:02d}m"


def _compute_monthly_card(env, employee, year, month):
    user_tz_str = env.user.tz or 'UTC'
    user_tz = pytz.timezone(user_tz_str)

    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    start_dt_local = user_tz.localize(datetime.combine(start_date, time.min))
    end_dt_local = user_tz.localize(datetime.combine(end_date, time.max))

    start_dt_utc = start_dt_local.astimezone(pytz.utc).replace(tzinfo=None)
    end_dt_utc = end_dt_local.astimezone(pytz.utc).replace(tzinfo=None)

    attendances = env['hr.attendance'].sudo().search([
        ('employee_id', '=', employee.id),
        ('check_in', '>=', start_dt_utc),
        ('check_in', '<=', end_dt_utc)
    ], order='check_in asc')

    leaves = env['hr.leave'].sudo().search([
        ('employee_id', '=', employee.id),
        ('state', '=', 'validate'),
        ('request_date_from', '<=', end_date),
        ('request_date_to', '>=', start_date)
    ])

    cal = employee.resource_calendar_id or employee.company_id.resource_calendar_id
    public_holidays = env['resource.calendar.leaves'].sudo().search([
        '|', ('calendar_id', '=', cal.id if cal else False), ('calendar_id', '=', False),
        ('resource_id', '=', False),
        ('date_from', '<=', end_dt_utc),
        ('date_to', '>=', start_dt_utc)
    ])

    default_std_hours = cal.hours_per_day if (cal and hasattr(cal, 'hours_per_day') and cal.hours_per_day) else 8.0

    daily_records = []
    tot_worked = 0.0
    tot_target = 0.0
    tot_shortfall = 0.0
    tot_overtime = 0.0
    present_days_cnt = 0
    leave_days_cnt = 0
    working_days_cnt = 0

    curr_date = start_date
    while curr_date <= end_date:
        wday_idx = curr_date.weekday()
        wday_str = curr_date.strftime('%A')
        day_fmt = curr_date.strftime('%d %b %Y')

        is_scheduled = True
        if cal:
            specs = cal.attendance_ids.filtered(lambda a: a.dayofweek == str(wday_idx) and getattr(a, 'day_period', '') != 'lunch')
            if not specs:
                is_scheduled = False
                std_hours = 0.0
            else:
                std_hours = sum(a.hour_to - a.hour_from for a in specs)
        else:
            if wday_idx >= 5:
                is_scheduled = False
                std_hours = 0.0
            else:
                std_hours = default_std_hours

        day_start_utc = user_tz.localize(datetime.combine(curr_date, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        day_end_utc = user_tz.localize(datetime.combine(curr_date, time.max)).astimezone(pytz.utc).replace(tzinfo=None)

        pub_hol = public_holidays.filtered(lambda h: h.date_from <= day_end_utc and h.date_to >= day_start_utc)
        is_pub_hol = bool(pub_hol)

        day_leave = leaves.filtered(lambda l: l.request_date_from <= curr_date and l.request_date_to >= curr_date)
        is_on_leave = bool(day_leave)

        day_atts = []
        for att in attendances:
            if att.check_in:
                ci_loc = pytz.utc.localize(att.check_in).astimezone(user_tz)
                if ci_loc.date() == curr_date:
                    day_atts.append(att)

        worked_hrs = sum(att.worked_hours or 0.0 for att in day_atts)

        first_ci_str = '-'
        last_co_str = '-'
        if day_atts:
            ci_dt = pytz.utc.localize(day_atts[0].check_in).astimezone(user_tz)
            first_ci_str = ci_dt.strftime('%I:%M %p')

            co_dt_raw = day_atts[-1].check_out
            if co_dt_raw:
                co_dt = pytz.utc.localize(co_dt_raw).astimezone(user_tz)
                last_co_str = co_dt.strftime('%I:%M %p')
            else:
                last_co_str = 'Ongoing'

        if is_pub_hol or is_on_leave or not is_scheduled:
            target_hrs = 0.0
        else:
            target_hrs = std_hours

        if is_scheduled and not is_pub_hol and not is_on_leave:
            working_days_cnt += 1

        shortfall = 0.0
        overtime = 0.0
        if target_hrs > 0:
            if worked_hrs < target_hrs:
                shortfall = target_hrs - worked_hrs
            elif worked_hrs > target_hrs:
                overtime = worked_hrs - target_hrs

        if is_pub_hol:
            status = f"Public Holiday ({pub_hol[0].name})"
            status_code = "HOLIDAY"
        elif is_on_leave:
            leave_days_cnt += 1
            l_name = day_leave[0].holiday_status_id.name if day_leave[0].holiday_status_id else "Leave"
            status = f"Leave ({l_name})"
            status_code = "LEAVE"
        elif not is_scheduled:
            if worked_hrs > 0:
                present_days_cnt += 1
                status = "Present (Weekend)"
                status_code = "PRESENT"
            else:
                status = "Weekend"
                status_code = "WEEKEND"
        elif worked_hrs > 0:
            present_days_cnt += 1
            if shortfall > 0.05:
                status = "Present (Shortfall)"
                status_code = "SHORTFALL"
            else:
                status = "Present"
                status_code = "PRESENT"
        else:
            status = "Absent"
            status_code = "ABSENT"

        tot_worked += worked_hrs
        tot_target += target_hrs
        tot_shortfall += shortfall
        tot_overtime += overtime

        daily_records.append({
            'date': curr_date.strftime('%Y-%m-%d'),
            'day_str': day_fmt,
            'weekday_str': wday_str,
            'check_in': first_ci_str,
            'check_out': last_co_str,
            'worked_hours': worked_hrs,
            'worked_hours_str': _format_hrs(worked_hrs),
            'target_hours': target_hrs,
            'target_hours_str': _format_hrs(target_hrs),
            'shortfall_hours': shortfall,
            'shortfall_hours_str': _format_hrs(shortfall) if shortfall > 0 else '-',
            'overtime_hours': overtime,
            'overtime_hours_str': _format_hrs(overtime) if overtime > 0 else '-',
            'status': status,
            'status_code': status_code,
        })

        curr_date += timedelta(days=1)

    summary = {
        'total_days': last_day,
        'working_days': working_days_cnt,
        'present_days': present_days_cnt,
        'leave_days': leave_days_cnt,
        'tot_worked': tot_worked,
        'tot_worked_str': _format_hrs(tot_worked),
        'tot_target': tot_target,
        'tot_target_str': _format_hrs(tot_target),
        'tot_shortfall': tot_shortfall,
        'tot_shortfall_str': _format_hrs(tot_shortfall),
        'tot_overtime': tot_overtime,
        'tot_overtime_str': _format_hrs(tot_overtime),
        'month_name': start_date.strftime('%B %Y'),
    }

    return daily_records, summary


class AttendanceRegularizeController(http.Controller):
    """ Controller handling attendance regularization requests and monthly attendance card exports. """

    @http.route(['/my/attendance/export_card'], type='http', auth="user", website=True)
    def export_attendance_card(self, month=None, year=None, format='pdf', **kw):
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not employee:
            return request.redirect('/my/dashboard')

        today = date.today()
        month_val = int(month or today.month)
        year_val = int(year or today.year)

        daily_records, summary = _compute_monthly_card(request.env, employee, year_val, month_val)

        if format == 'xlsx':
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            worksheet = workbook.add_worksheet('Attendance Card')

            # Formats
            title_fmt = workbook.add_format({'bold': True, 'font_size': 16, 'font_color': '#4C1D95', 'align': 'left'})
            sub_title_fmt = workbook.add_format({'bold': True, 'font_size': 12, 'font_color': '#64748B', 'align': 'left'})
            header_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#4C1D95', 'align': 'center', 'border': 1})
            data_fmt = workbook.add_format({'align': 'center', 'border': 1})
            bold_data_fmt = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
            label_fmt = workbook.add_format({'bold': True, 'bg_color': '#F8FAFC', 'border': 1})
            val_fmt = workbook.add_format({'border': 1})

            # Headers info
            company_name = employee.company_id.name or 'Company'
            worksheet.write(0, 0, company_name.upper(), title_fmt)
            worksheet.write(1, 0, f"OFFICIAL MONTHLY ATTENDANCE CARD - {summary['month_name']}", sub_title_fmt)

            # Employee Box
            worksheet.write(3, 0, "Employee Name:", label_fmt)
            worksheet.write(3, 1, employee.name, val_fmt)
            worksheet.write(3, 3, "Job Position:", label_fmt)
            worksheet.write(3, 4, employee.job_title or (employee.job_id and employee.job_id.name) or '-', val_fmt)

            worksheet.write(4, 0, "Department:", label_fmt)
            worksheet.write(4, 1, employee.department_id.name if employee.department_id else '-', val_fmt)
            worksheet.write(4, 3, "Work Schedule:", label_fmt)
            worksheet.write(4, 4, employee.resource_calendar_id.name if employee.resource_calendar_id else 'Standard Schedule', val_fmt)

            # Summary Box
            worksheet.write(6, 0, "Working Days", label_fmt)
            worksheet.write(6, 1, summary['working_days'], val_fmt)
            worksheet.write(6, 2, "Days Present", label_fmt)
            worksheet.write(6, 3, summary['present_days'], val_fmt)
            worksheet.write(6, 4, "Total Worked", label_fmt)
            worksheet.write(6, 5, summary['tot_worked_str'], val_fmt)

            worksheet.write(7, 0, "Total Shortfall", label_fmt)
            worksheet.write(7, 1, summary['tot_shortfall_str'], val_fmt)
            worksheet.write(7, 2, "Total Overtime", label_fmt)
            worksheet.write(7, 3, summary['tot_overtime_str'], val_fmt)

            # Table Header
            headers = ["Date", "Day", "Check In", "Check Out", "Worked Hours", "Target Hours", "Shortfall", "Overtime", "Status"]
            start_row = 10
            for col_idx, h in enumerate(headers):
                worksheet.write(start_row, col_idx, h, header_fmt)

            row = start_row + 1
            for rec in daily_records:
                worksheet.write(row, 0, rec['day_str'], data_fmt)
                worksheet.write(row, 1, rec['weekday_str'], data_fmt)
                worksheet.write(row, 2, rec['check_in'], bold_data_fmt)
                worksheet.write(row, 3, rec['check_out'], bold_data_fmt)
                worksheet.write(row, 4, rec['worked_hours_str'], bold_data_fmt)
                worksheet.write(row, 5, rec['target_hours_str'], data_fmt)
                worksheet.write(row, 6, rec['shortfall_hours_str'], data_fmt)
                worksheet.write(row, 7, rec['overtime_hours_str'], data_fmt)
                worksheet.write(row, 8, rec['status'], data_fmt)
                row += 1

            # Adjust Column Widths
            worksheet.set_column(0, 0, 14)
            worksheet.set_column(1, 1, 12)
            worksheet.set_column(2, 3, 14)
            worksheet.set_column(4, 7, 14)
            worksheet.set_column(8, 8, 25)

            workbook.close()
            output.seek(0)
            file_data = output.read()

            filename = f"Attendance_Card_{employee.name.replace(' ', '_')}_{year_val}_{month_val:02d}.xlsx"
            return request.make_response(
                file_data,
                headers=[
                    ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                    ('Content-Disposition', f'attachment; filename="{filename}"')
                ]
            )

        # Default PDF Report Generation
        report = request.env.ref('ucs_attendance_regularize.action_report_monthly_attendance_card')
        pdf_content, _ = report.sudo()._render_qweb_pdf(
            'ucs_attendance_regularize.action_report_monthly_attendance_card',
            [employee.id],
            data={
                'doc': employee,
                'daily_records': daily_records,
                'summary': summary,
            }
        )
        filename = f"Monthly_Attendance_Card_{employee.name.replace(' ', '_')}_{year_val}_{month_val:02d}.pdf"
        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )

    @http.route(['/my/attendance/regularize_request'], type='http', auth="user", website=True, methods=['POST'])
    def submit_regularize_request(self, **post):
        """ Validate and create an attendance regularization request submitted by an employee. """
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

