# -*- coding: utf-8 -*-
import re
from odoo import http, _
from odoo.http import request
from odoo.addons.hr_timesheet.controllers.portal import TimesheetCustomerPortal
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from .main import _get_weekly_timesheet_info

def _get_timesheet_calendar_data(user, year=None, month=None, employee_id=None):
    is_manager = _is_timesheet_manager(user)
    
    employees_list = []
    if is_manager:
        all_emps = request.env['hr.employee'].sudo().search([])
        employees_list = [{'id': e.id, 'name': e.name} for e in all_emps]

    if is_manager and employee_id:
        employee = request.env['hr.employee'].sudo().browse(int(employee_id))
    else:
        employee = request.env['hr.employee'].sudo().search(['|', ('user_id', '=', user.id), ('work_email', '=', user.login)], limit=1)

    if not employee:
        return {'is_manager': is_manager, 'employees': employees_list, 'employee_id': None, 'days_data': {}}

    from datetime import date, datetime, timedelta
    import calendar as py_calendar
    
    today = date.today()
    if not year:
        year = today.year
    if not month:
        month = today.month
        
    res_calendar = employee.resource_calendar_id or (employee.company_id and employee.company_id.resource_calendar_id)
    
    day_scheduled_hours = {}
    hours_per_day = 8.0
    if res_calendar:
        if getattr(res_calendar, 'hours_per_day', False) and res_calendar.hours_per_day > 0:
            hours_per_day = float(res_calendar.hours_per_day)
        elif getattr(res_calendar, 'hours_per_week', False) and res_calendar.hours_per_week > 0:
            hours_per_day = round(float(res_calendar.hours_per_week) / 5.0, 2)

    if res_calendar and res_calendar.attendance_ids:
        for day_idx in range(7):
            day_str = str(day_idx)
            attendances = res_calendar.attendance_ids.filtered(lambda a: a.dayofweek == day_str and not getattr(a, 'display_type', False))
            if attendances:
                day_scheduled_hours[day_idx] = hours_per_day
            else:
                day_scheduled_hours[day_idx] = 0.0
    else:
        day_scheduled_hours = {0: hours_per_day, 1: hours_per_day, 2: hours_per_day, 3: hours_per_day, 4: hours_per_day, 5: 0.0, 6: 0.0}

    first_weekday, num_days = py_calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, num_days)

    domain = [
        ('employee_id', '=', employee.id),
        ('date', '>=', start_date),
        ('date', '<=', end_date),
    ]
    timesheets = request.env['account.analytic.line'].sudo().search(domain)
    
    days_data = {}
    for day_num in range(1, num_days + 1):
        d = date(year, month, day_num)
        d_str = d.strftime('%Y-%m-%d')
        w_idx = d.weekday()
        sch_hrs = day_scheduled_hours.get(w_idx, 8.0 if w_idx < 5 else 0.0)
        is_future = (d > today)
        
        day_ts = timesheets.filtered(lambda ts: ts.date == d)
        leave_ts = day_ts.filtered(lambda ts: ts.holiday_id)
        reg_ts = day_ts.filtered(lambda ts: not ts.holiday_id)
        
        reg_hrs = sum(ts.unit_amount for ts in reg_ts)
        leave_hrs = sum(ts.unit_amount for ts in leave_ts)
        tot_hrs = reg_hrs + leave_hrs
        
        has_leave = bool(leave_hrs > 0)
        
        status_code = 'neutral'
        if sch_hrs > 0:
            if has_leave:
                leaves = leave_ts.mapped('holiday_id')
                is_half = any(getattr(l, 'request_unit_half', False) for l in leaves)
                
                # Full day leave check: not marked half-day OR leave hours cover 85%+ of scheduled hours
                if not is_half or leave_hrs >= (sch_hrs * 0.85):
                    status_code = 'yellow'
                else:
                    period = 'am'
                    for l in leaves:
                        p = getattr(l, 'request_date_from_period', False)
                        if p in ['am', 'pm']:
                            period = p
                            break
                    
                    rem_sch = max(sch_hrs - leave_hrs, 0.0)
                    is_work_complete = (reg_hrs >= (rem_sch - 0.1))
                    
                    if period == 'am':
                        if is_work_complete:
                            status_code = 'yellow_top_green_bottom'
                        else:
                            status_code = 'yellow_top_red_bottom' if not is_future else 'yellow'
                    else:
                        if is_work_complete:
                            status_code = 'green_top_yellow_bottom'
                        else:
                            status_code = 'red_top_yellow_bottom' if not is_future else 'yellow'
            else:
                if reg_hrs >= (sch_hrs - 0.1):
                    status_code = 'green'
                else:
                    if not is_future:
                        status_code = 'red'
                    else:
                        status_code = 'neutral'
        else:
            if tot_hrs > 0:
                status_code = 'green'
            else:
                status_code = 'neutral'

        days_data[d_str] = {
            'date': d_str,
            'day': day_num,
            'weekday': w_idx,
            'scheduled_hours': sch_hrs,
            'regular_hours': reg_hrs,
            'leave_hours': leave_hrs,
            'total_hours': tot_hrs,
            'has_leave': has_leave,
            'is_future': is_future,
            'status_code': status_code,
            'entries': [{
                'id': ts.id,
                'name': ts.name or '',
                'project': ts.project_id.name if ts.project_id else '',
                'task': ts.task_id.name if ts.task_id else '',
                'hours': ts.unit_amount,
                'is_leave': bool(ts.holiday_id),
                'state': ts.state or 'draft',
            } for ts in day_ts]
        }

    prev_d = start_date - timedelta(days=1)
    next_d = end_date + timedelta(days=1)

    monthly_scheduled_hours = round(sum(d['scheduled_hours'] for d in days_data.values()), 2)
    monthly_leave_hours = round(sum(d['leave_hours'] for d in days_data.values()), 2)
    monthly_net_required = max(round(monthly_scheduled_hours - monthly_leave_hours, 2), 0.0)
    monthly_regular_hours = round(sum(d['regular_hours'] for d in days_data.values()), 2)

    # Required till today (excluding leave till today)
    sch_till_today = sum(d['scheduled_hours'] for date_str, d in days_data.items() if date.fromisoformat(date_str) <= today)
    lve_till_today = sum(d['leave_hours'] for date_str, d in days_data.items() if date.fromisoformat(date_str) <= today)
    required_till_today_hours = max(round(sch_till_today - lve_till_today, 2), 0.0)

    if year == today.year and month == today.month:
        target_pct_hrs = required_till_today_hours if required_till_today_hours > 0 else monthly_net_required
    elif (year < today.year) or (year == today.year and month < today.month):
        target_pct_hrs = monthly_net_required
    else:
        target_pct_hrs = monthly_net_required

    monthly_completion_pct = round((monthly_regular_hours / target_pct_hrs * 100.0), 1) if target_pct_hrs > 0 else 0.0

    return {
        'year': year,
        'month': month,
        'month_name': start_date.strftime('%B %Y'),
        'first_weekday': first_weekday,
        'num_days': num_days,
        'prev_year': prev_d.year,
        'prev_month': prev_d.month,
        'next_year': next_d.year,
        'next_month': next_d.month,
        'days_data': days_data,
        'employee_id': employee.id,
        'employee_name': employee.name,
        'is_manager': is_manager,
        'employees': employees_list,
        'monthly_scheduled_hours': monthly_scheduled_hours,
        'monthly_required_hours': monthly_scheduled_hours,
        'monthly_net_required': monthly_net_required,
        'required_till_today_hours': required_till_today_hours,
        'monthly_regular_hours': monthly_regular_hours,
        'monthly_leave_hours': monthly_leave_hours,
        'monthly_total_logged': monthly_regular_hours,
        'monthly_completion_pct': monthly_completion_pct,
    }

def _is_timesheet_manager(user):
    return (
        user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_manager') or
        user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_admin') or
        user.has_group('hr_timesheet.group_hr_timesheet_approver') or
        user.has_group('hr_timesheet.group_timesheet_manager') or
        user.has_group('base.group_system')
    )

def _get_filter_domain(filterby):
    today = date.today()
    if filterby == 'draft':
        return [('state', '=', 'draft')]
    elif filterby == 'confirm':
        return [('state', '=', 'confirm')]
    elif filterby == 'approved':
        return [('state', '=', 'approved')]
    elif filterby == 'refused':
        return [('state', '=', 'refused')]
    elif filterby == 'today':
        return [('date', '=', today)]
    elif filterby == 'this_week':
        first_day = today - relativedelta(days=today.weekday())
        last_day = first_day + relativedelta(days=6)
        return [('date', '>=', first_day), ('date', '<=', last_day)]
    elif filterby == 'last_week':
        first_day = today - relativedelta(days=today.weekday() + 7)
        last_day = first_day + relativedelta(days=6)
        return [('date', '>=', first_day), ('date', '<=', last_day)]
    elif filterby == 'this_month':
        first_day = today.replace(day=1)
        last_day = (first_day + relativedelta(months=1)) - relativedelta(days=1)
        return [('date', '>=', first_day), ('date', '<=', last_day)]
    elif filterby == 'last_month':
        first_day = (today.replace(day=1)) - relativedelta(months=1)
        last_day = (today.replace(day=1)) - relativedelta(days=1)
        return [('date', '>=', first_day), ('date', '<=', last_day)]
    elif filterby == 'this_quarter':
        quarter_month = 3 * ((today.month - 1) // 3) + 1
        first_day = today.replace(month=quarter_month, day=1)
        last_day = (first_day + relativedelta(months=3)) - relativedelta(days=1)
        return [('date', '>=', first_day), ('date', '<=', last_day)]
    elif filterby == 'last_quarter':
        quarter_month = 3 * ((today.month - 1) // 3) + 1
        first_this_q = today.replace(month=quarter_month, day=1)
        first_day = first_this_q - relativedelta(months=3)
        last_day = first_this_q - relativedelta(days=1)
        return [('date', '>=', first_day), ('date', '<=', last_day)]
    elif filterby == 'this_year':
        first_day = today.replace(month=1, day=1)
        last_day = today.replace(month=12, day=31)
        return [('date', '>=', first_day), ('date', '<=', last_day)]
    elif filterby == 'last_year':
        first_day = (today - relativedelta(years=1)).replace(month=1, day=1)
        last_day = (today - relativedelta(years=1)).replace(month=12, day=31)
        return [('date', '>=', first_day), ('date', '<=', last_day)]
    return []

def _build_multi_term_search_domain(search_str, search_in='all'):
    if not search_str:
        return []
    terms = [t.strip() for t in re.split(r'[,]+|\s+', str(search_str)) if t.strip()]
    if not terms:
        return []

    term_domains = []
    for term in terms:
        if search_in == 'name':
            term_domains.append([('name', 'ilike', term)])
        elif search_in == 'project':
            term_domains.append([('project_id.name', 'ilike', term)])
        elif search_in == 'task':
            term_domains.append([('task_id.name', 'ilike', term)])
        elif search_in == 'employee':
            term_domains.append([('employee_id.name', 'ilike', term)])
        else: # 'all'
            term_domains.append([
                '|', '|', '|',
                ('name', 'ilike', term),
                ('project_id.name', 'ilike', term),
                ('task_id.name', 'ilike', term),
                ('employee_id.name', 'ilike', term)
            ])

    if len(term_domains) == 1:
        return term_domains[0]

    final_domain = ['|'] * (len(term_domains) - 1)
    for td in term_domains:
        final_domain.extend(td)

    return final_domain

def _build_n_level_groups(records, gb_keys, depth=0):
    if not records or depth >= len(gb_keys):
        return []
    
    from odoo.tools.misc import groupby as groupby_tool
    
    label_getters = {
        'project_id': lambda t: t.project_id.name if t.project_id else 'No Project',
        'task_id': lambda t: t.task_id.name if t.task_id else 'No Task',
        'employee_id': lambda t: t.employee_id.name if t.employee_id else 'No Employee',
        'date': lambda t: str(t.date),
        'state': lambda t: (
            'Draft' if t.state == 'draft' else 
            'Submitted' if t.state == 'confirm' else 
            'Approved' if t.state == 'approved' else 
            'Refused' if t.state == 'refused' else t.state
        ),
    }

    field_key = gb_keys[depth]
    field_func = label_getters.get(field_key, lambda t: str(getattr(t, field_key, '')))
    field_title = field_key.replace('_id', '').replace('_', ' ').title()

    sorted_recs = sorted(records, key=field_func)
    res = []

    for group_label, group_recs in groupby_tool(sorted_recs, key=field_func):
        rec_list = request.env['account.analytic.line'].sudo().concat(*group_recs)
        hours = sum(rec_list.mapped('unit_amount'))

        is_leaf = (depth == len(gb_keys) - 1)
        sub_groups = _build_n_level_groups(rec_list, gb_keys, depth + 1) if not is_leaf else []

        res.append({
            'depth': depth,
            'title': field_title,
            'label': f"{field_title}: {group_label}",
            'hours': hours,
            'count': len(rec_list),
            'timesheets': rec_list if is_leaf else [],
            'sub_groups': sub_groups,
            'is_leaf': is_leaf,
        })

    return res

def _flatten_group_tree(group_nodes, parent_id="grp", depth=0):
    flat_rows = []
    colors = ['#faf5ff', '#f3e8ff', '#e9d5ff', '#d8b4fe', '#c084fc']
    bg_color = colors[min(depth, len(colors) - 1)]

    for idx, node in enumerate(group_nodes):
        current_id = f"{parent_id}_{idx}"
        
        header_item = {
            'type': 'header',
            'depth': depth,
            'padding_left': 15 + (depth * 25),
            'label': node['label'],
            'count': node['count'],
            'hours': node['hours'],
            'parent_class': parent_id,
            'my_class': current_id,
            'bg_color': bg_color,
        }
        flat_rows.append(header_item)
        
        if node['is_leaf']:
            for ts in node['timesheets']:
                flat_rows.append({
                    'type': 'timesheet',
                    'depth': depth + 1,
                    'parent_class': current_id,
                    'timesheet': ts,
                })
        else:
            flat_rows.extend(_flatten_group_tree(node['sub_groups'], parent_id=current_id, depth=depth + 1))

    return flat_rows

class PortalCustomTimesheets(TimesheetCustomerPortal):

    def _get_portal_default_domain(self):
        user = request.env.user
        args = request.httprequest.args or {}
        params = request.params or {}
        
        scope = args.get('scope') or params.get('scope') or 'my'
        is_manager = _is_timesheet_manager(user)
        employee = request.env['hr.employee'].sudo().search(['|', ('user_id', '=', user.id), ('work_email', '=', user.login)], limit=1)
        
        domain = []
        if scope != 'all' or not is_manager:
            if employee:
                domain.append(('employee_id', '=', employee.id))
            else:
                domain.append(('user_id', '=', user.id))

        filterby = args.get('filterby') or params.get('filterby') or 'all'
        domain.extend(_get_filter_domain(filterby))

        search = args.get('search') or params.get('search') or ''
        search_in = args.get('search_in') or params.get('search_in') or 'all'
        if search:
            domain.extend(_build_multi_term_search_domain(search, search_in))

        return domain

    def _get_searchbar_filters(self):
        today = date.today()
        first_this_week = today - relativedelta(days=today.weekday())
        last_this_week = first_this_week + relativedelta(days=6)
        first_last_week = first_this_week - relativedelta(days=7)
        last_last_week = first_this_week - relativedelta(days=1)
        
        first_this_month = today.replace(day=1)
        last_this_month = (first_this_month + relativedelta(months=1)) - relativedelta(days=1)
        first_last_month = (today.replace(day=1)) - relativedelta(months=1)
        last_last_month = (today.replace(day=1)) - relativedelta(days=1)
        
        first_this_year = today.replace(month=1, day=1)
        last_this_year = today.replace(month=12, day=31)
        first_last_year = (today - relativedelta(years=1)).replace(month=1, day=1)
        last_last_year = (today - relativedelta(years=1)).replace(month=12, day=31)

        return {
            'all': {'label': _('All'), 'domain': [], 'sequence': 1},
            'draft': {'label': _('Draft'), 'domain': [('state', '=', 'draft')], 'sequence': 2},
            'confirm': {'label': _('Submitted'), 'domain': [('state', '=', 'confirm')], 'sequence': 3},
            'approved': {'label': _('Approved'), 'domain': [('state', '=', 'approved')], 'sequence': 4},
            'refused': {'label': _('Refused'), 'domain': [('state', '=', 'refused')], 'sequence': 5},
            'today': {'label': _('Today'), 'domain': [('date', '=', today)], 'sequence': 6},
            'this_week': {'label': _('This Week'), 'domain': [('date', '>=', first_this_week), ('date', '<=', last_this_week)], 'sequence': 7},
            'last_week': {'label': _('Last Week'), 'domain': [('date', '>=', first_last_week), ('date', '<=', last_last_week)], 'sequence': 8},
            'this_month': {'label': _('This Month'), 'domain': [('date', '>=', first_this_month), ('date', '<=', last_this_month)], 'sequence': 9},
            'last_month': {'label': _('Last Month'), 'domain': [('date', '>=', first_last_month), ('date', '<=', last_last_month)], 'sequence': 10},
            'this_year': {'label': _('This Year'), 'domain': [('date', '>=', first_this_year), ('date', '<=', last_this_year)], 'sequence': 11},
            'last_year': {'label': _('Last Year'), 'domain': [('date', '>=', first_last_year), ('date', '<=', last_last_year)], 'sequence': 12},
        }

    def _get_searchbar_sortings(self):
        return {
            'date': {'label': _('Newest'), 'order': 'date desc, id desc', 'sequence': 1},
            'date_asc': {'label': _('Oldest'), 'order': 'date asc, id asc', 'sequence': 2},
            'project': {'label': _('Project'), 'order': 'project_id asc, date desc', 'sequence': 3},
            'task': {'label': _('Task'), 'order': 'task_id asc, date desc', 'sequence': 4},
            'employee': {'label': _('Employee'), 'order': 'employee_id asc, date desc', 'sequence': 5},
            'name': {'label': _('Description'), 'order': 'name asc, date desc', 'sequence': 6},
        }

    def _get_searchbar_groupby(self, current_groupby=None):
        fields = [
            ('project_id', _('Project')),
            ('task_id', _('Task')),
            ('employee_id', _('Employee')),
            ('date', _('Date')),
            ('state', _('Status')),
        ]
        
        active_gbs = [g.strip() for g in (current_groupby or '').split(',') if g.strip() and g.strip() != 'none']
        
        gb_dict = {}
        gb_dict['none'] = {'label': _('None'), 'sequence': 1}
        
        seq = 2
        for f_key, f_label in fields:
            if f_key in active_gbs:
                rem_gbs = [g for g in active_gbs if g != f_key]
                target_key = ','.join(rem_gbs) if rem_gbs else 'none'
                gb_dict[target_key] = {'label': _('✓ ') + str(f_label), 'sequence': seq}
            else:
                new_gbs = active_gbs + [f_key]
                target_key = ','.join(new_gbs)
                label_text = f"+ {f_label}" if active_gbs else f_label
                gb_dict[target_key] = {'label': label_text, 'sequence': seq}
            seq += 1

        preset_combos = [
            ('project_id,employee_id', _('Project > Employee')),
            ('project_id,task_id', _('Project > Task')),
            ('employee_id,project_id', _('Employee > Project')),
            ('employee_id,date', _('Employee > Date')),
        ]
        for combo_key, combo_label in preset_combos:
            if combo_key not in gb_dict:
                gb_dict[combo_key] = {'label': combo_label, 'sequence': seq}
                seq += 1

        return gb_dict

    @http.route(['/my/timesheets', '/my/timesheets/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_timesheets(self, page=1, sortby=None, filterby=None, search=None, search_in='all', groupby='none', **kw):
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search(['|', ('user_id', '=', user.id), ('work_email', '=', user.login)], limit=1)
        if not employee and not user.has_group('base.group_system'):
            return request.redirect('/my')

        args = request.httprequest.args or {}
        params = request.params or {}

        scope = args.get('scope') or params.get('scope') or kw.get('scope') or 'my'
        sortby = args.get('sortby') or params.get('sortby') or sortby or 'date'
        filterby = args.get('filterby') or params.get('filterby') or filterby or 'all'
        search = args.get('search') or params.get('search') or search or ''
        search_in = args.get('search_in') or params.get('search_in') or search_in or 'all'
        groupby = args.get('groupby') or params.get('groupby') or groupby or 'none'

        is_manager = _is_timesheet_manager(user)
        if scope == 'all' and not is_manager:
            scope = 'my'

        request.params['scope'] = scope
        request.params['filterby'] = filterby
        request.params['sortby'] = sortby
        request.params['groupby'] = groupby

        # Pass groupby='none' to super so base Odoo doesn't raise KeyError on multi-level comma strings like 'project_id,employee_id'
        response = super().portal_my_timesheets(page, sortby='date', filterby='all', search=search, search_in=search_in, groupby='none', **kw)
        if hasattr(response, 'qcontext'):
            qctx = response.qcontext

            domain = self._get_portal_default_domain()
            order_mapping = {
                'date': 'date desc, id desc',
                'date desc': 'date desc, id desc',
                'date_asc': 'date asc, id asc',
                'date asc': 'date asc, id asc',
                'project': 'project_id asc, date desc',
                'task': 'task_id asc, date desc',
                'employee': 'employee_id asc, date desc',
                'name': 'name asc, date desc',
            }
            order = order_mapping.get(sortby, 'date desc, id desc')

            # Auto-sync leave timesheet states
            approved_leave_ts = request.env['account.analytic.line'].sudo().search([
                ('holiday_id', '!=', False),
                ('holiday_id.state', 'in', ['validate', 'validate1']),
                ('state', '!=', 'approved')
            ])
            if approved_leave_ts:
                approved_leave_ts.write({'state': 'approved'})

            refused_leave_ts = request.env['account.analytic.line'].sudo().search([
                ('holiday_id', '!=', False),
                ('holiday_id.state', 'in', ['refuse', 'cancel'])
            ])
            if refused_leave_ts:
                refused_leave_ts.with_context(leave_unlink=True).sudo().unlink()

            timesheets = request.env['account.analytic.line'].sudo().search(domain, order=order)
            qctx['timesheets'] = timesheets

            if groupby != 'none':
                gb_keys = [k.strip() for k in groupby.split(',') if k.strip()]
                group_tree = _build_n_level_groups(timesheets, gb_keys, depth=0)
                flat_rows = _flatten_group_tree(group_tree, parent_id="grp", depth=0)
            else:
                flat_rows = [{'type': 'timesheet', 'parent_class': '', 'timesheet': ts} for ts in timesheets]

            qctx['flat_group_rows'] = flat_rows

            qctx['sortby'] = sortby
            qctx['filterby'] = filterby
            qctx['groupby'] = groupby
            qctx['search_in'] = search_in
            qctx['search'] = search
            qctx['scope'] = scope
            qctx.update(_get_weekly_timesheet_info(user))
            qctx['calendar_data'] = _get_timesheet_calendar_data(user)

            # Populate failsafe searchbar dictionaries
            filters = self._get_searchbar_filters()
            sortings = self._get_searchbar_sortings()
            groupbys = self._get_searchbar_groupby(current_groupby=groupby)

            if sortby not in sortings:
                sortings[sortby] = {'label': _('Newest'), 'order': 'date desc, id desc', 'sequence': 99}
            if filterby not in filters:
                filters[filterby] = {'label': _('All'), 'domain': [], 'sequence': 99}
            if groupby not in groupbys:
                groupbys[groupby] = {'label': groupby.replace('_id','').replace('_',' ').title(), 'sequence': 99}

            qctx['searchbar_filters'] = filters
            qctx['searchbar_sortings'] = sortings
            qctx['searchbar_groupby'] = groupbys
            
            qctx['is_timesheet_manager'] = is_manager
            qctx['scope'] = scope
            qctx['projects'] = request.env['project.project'].sudo().search([])
            qctx['csrf_token'] = request.csrf_token()
            qctx['error_message'] = kw.get('error')

        return response

    @http.route(['/my/timesheets/create'], type='http', auth="user", methods=['POST'], website=True)
    def custom_timesheets_create(self, **post):
        user = request.env.user
        is_employee = bool(request.env['hr.employee'].sudo().search(['|', ('user_id', '=', user.id), ('work_email', '=', user.login)], limit=1))
        if not is_employee:
            return request.redirect('/my/timesheets')
            
        def _safe_int(val, default=0):
            if not val:
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        project_id = _safe_int(post.get('project_id'), 0)
        task_id = _safe_int(post.get('task_id'), False)
        date = post.get('date')
        unit_amount_str = post.get('unit_amount_str', '')
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
                
        name = post.get('name', '').strip()
        if project_id and task_id and name and date and unit_amount > 0:
            user = request.env.user
            today_str = datetime.now().strftime('%Y-%m-%d')
            redirect_to = post.get('redirect_to', '/my/timesheets')
            sep = '&' if '?' in redirect_to else '?'

            # Guardrail 1: Block future date logging
            if str(date) > today_str:
                import urllib.parse
                error_msg = "Logging timesheets for future dates is not allowed."
                return request.redirect(f"{redirect_to}{sep}error={urllib.parse.quote(error_msg)}")

            employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
            
            vals = {
                'project_id': project_id,
                'task_id': task_id,
                'date': date,
                'unit_amount': unit_amount,
                'name': name,
            }
            if employee:
                vals['employee_id'] = employee.id
                
            try:
                request.env['account.analytic.line'].sudo().create(vals)
                request.env.flush_all()
            except Exception as e:
                request.env.cr.rollback()
                import urllib.parse
                error_msg = str(e).replace('\n', ' ')
                return request.redirect(f"{redirect_to}{sep}error={urllib.parse.quote(error_msg)}")
            
        redirect_to = post.get('redirect_to', '/my/timesheets')
        return request.redirect(redirect_to)

    @http.route('/my/timesheets/get_tasks_by_project', type='jsonrpc', auth='user')
    def get_tasks_by_project(self, project_id, **kw):
        user = request.env.user
        project_id = int(project_id) if project_id else 0
        
        # Let base Odoo rules filter the tasks
        tasks = request.env['project.task'].search([('project_id', '=', project_id)])

        return [{'id': t.id, 'name': t.name} for t in tasks]

    @http.route('/my/timesheets/calendar_data', type='jsonrpc', auth='user')
    def get_timesheet_calendar_data_route(self, year=None, month=None, employee_id=None, **kw):
        user = request.env.user
        try:
            year = int(year) if year else None
            month = int(month) if month else None
            employee_id = int(employee_id) if employee_id else None
        except Exception:
            year, month, employee_id = None, None, None
        return _get_timesheet_calendar_data(user, year=year, month=month, employee_id=employee_id)

    @http.route(['/my/timesheets/delete/<int:timesheet_id>', '/my/timesheets/delete'], type='http', auth="user", methods=['GET', 'POST'], website=True)
    def custom_timesheets_delete(self, timesheet_id=None, **post):
        user = request.env.user
        ts_id = timesheet_id or post.get('timesheet_id')
        redirect_to = post.get('redirect_to') or request.httprequest.referrer or '/my/timesheets'

        if ts_id:
            try:
                ts_id = int(ts_id)
                ts = request.env['account.analytic.line'].sudo().browse(ts_id)
                if ts.exists():
                    is_owner = (ts.employee_id.user_id.id == user.id) or (ts.create_uid.id == user.id)
                    is_manager = _is_timesheet_manager(user)
                    is_draft = (getattr(ts, 'state', 'draft') or 'draft') == 'draft'

                    if (is_owner or is_manager) and is_draft:
                        ts.sudo().unlink()
                    elif not is_draft:
                        import urllib.parse
                        sep = '&' if '?' in redirect_to else '?'
                        return request.redirect(f"{redirect_to}{sep}error=" + urllib.parse.quote("Submitted or approved timesheets cannot be deleted."))
            except Exception as e:
                import urllib.parse
                error_msg = str(e).replace('\n', ' ')
                sep = '&' if '?' in redirect_to else '?'
                return request.redirect(f"{redirect_to}{sep}error={urllib.parse.quote(error_msg)}")

        return request.redirect(redirect_to)
