# -*- coding: utf-8 -*-
import re
import json
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from odoo import http, _
from odoo.http import request
from odoo.addons.project.controllers.portal import ProjectCustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, MissingError


def _build_n_level_project_groups(records, gb_keys, depth=0):
    if not records or depth >= len(gb_keys):
        return []
    
    from odoo.tools.misc import groupby as groupby_tool
    
    label_getters = {
        'user_id': lambda p: p.user_id.name if p.user_id else _('Unassigned Manager'),
        'partner_id': lambda p: p.partner_id.name if p.partner_id else _('No Customer'),
        'date': lambda p: p.create_date.strftime('%B %Y') if p.create_date else _('Unknown Date'),
    }

    field_key = gb_keys[depth]
    field_func = label_getters.get(field_key, lambda p: str(getattr(p, field_key, '')))
    field_title = field_key.replace('_id', '').replace('_', ' ').title()

    sorted_recs = sorted(records, key=field_func)
    res = []

    for group_label, group_recs in groupby_tool(sorted_recs, key=field_func):
        rec_list = request.env['project.project'].sudo().concat(*group_recs)
        task_count = sum(rec_list.mapped('task_count'))

        is_leaf = (depth == len(gb_keys) - 1)
        sub_groups = _build_n_level_project_groups(rec_list, gb_keys, depth + 1) if not is_leaf else []

        res.append({
            'depth': depth,
            'title': field_title,
            'label': f"{field_title}: {group_label}",
            'task_count': task_count,
            'count': len(rec_list),
            'projects': rec_list if is_leaf else [],
            'sub_groups': sub_groups,
            'is_leaf': is_leaf,
        })

    return res


def _flatten_project_group_tree(group_nodes, parent_id="pgrp", depth=0):
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
            'task_count': node['task_count'],
            'parent_class': parent_id,
            'my_class': current_id,
            'bg_color': bg_color,
        }
        flat_rows.append(header_item)
        
        if node['is_leaf']:
            for p in node['projects']:
                flat_rows.append({
                    'type': 'project',
                    'depth': depth + 1,
                    'parent_class': current_id,
                    'project': p,
                })
        else:
            flat_rows.extend(_flatten_project_group_tree(node['sub_groups'], parent_id=current_id, depth=depth + 1))

    return flat_rows


def _build_n_level_task_groups(records, gb_keys, depth=0):
    if not records or depth >= len(gb_keys):
        return []
    
    from odoo.tools.misc import groupby as groupby_tool
    
    label_getters = {
        'project_id': lambda t: t.project_id.name if t.project_id else _('No Project'),
        'stage_id': lambda t: t.stage_id.name if t.stage_id else _('No Stage'),
        'user_ids': lambda t: (', '.join(t.user_ids.mapped('name')) if t.user_ids else _('Unassigned')),
        'priority': lambda t: (_('★ High Priority') if t.priority == '1' else _('Normal Priority')),
        'date_deadline': lambda t: (t.date_deadline.strftime('%B %Y') if t.date_deadline else _('No Deadline')),
    }

    field_key = gb_keys[depth]
    field_func = label_getters.get(field_key, lambda t: str(getattr(t, field_key, '')))
    field_title = field_key.replace('_ids', '').replace('_id', '').replace('_', ' ').title()

    sorted_recs = sorted(records, key=field_func)
    res = []

    for group_label, group_recs in groupby_tool(sorted_recs, key=field_func):
        rec_list = request.env['project.task'].sudo().concat(*group_recs)
        allocated_hours = sum(rec_list.mapped('allocated_hours'))

        is_leaf = (depth == len(gb_keys) - 1)
        sub_groups = _build_n_level_task_groups(rec_list, gb_keys, depth + 1) if not is_leaf else []

        res.append({
            'depth': depth,
            'title': field_title,
            'label': f"{field_title}: {group_label}",
            'allocated_hours': allocated_hours,
            'count': len(rec_list),
            'tasks': rec_list if is_leaf else [],
            'sub_groups': sub_groups,
            'is_leaf': is_leaf,
        })

    return res


def _flatten_task_group_tree(group_nodes, parent_id="tgrp", depth=0):
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
            'allocated_hours': node['allocated_hours'],
            'parent_class': parent_id,
            'my_class': current_id,
            'bg_color': bg_color,
        }
        flat_rows.append(header_item)
        
        if node['is_leaf']:
            for task in node['tasks']:
                flat_rows.append({
                    'type': 'task',
                    'depth': depth + 1,
                    'parent_class': current_id,
                    'task': task,
                })
        else:
            flat_rows.extend(_flatten_task_group_tree(node['sub_groups'], parent_id=current_id, depth=depth + 1))

    return flat_rows


class PortalCustomProjects(ProjectCustomerPortal):

    def _get_project_searchbar_filters(self):
        today = date.today()
        first_this_month = today.replace(day=1)
        last_this_month = (first_this_month + relativedelta(months=1)) - relativedelta(days=1)
        first_last_month = (today.replace(day=1)) - relativedelta(months=1)
        last_last_month = (today.replace(day=1)) - relativedelta(days=1)
        
        first_this_year = today.replace(month=1, day=1)
        last_this_year = today.replace(month=12, day=31)

        user = request.env.user
        return {
            'all': {'label': _('All Projects'), 'domain': [], 'sequence': 1},
            'open': {'label': _('Active Projects'), 'domain': [('active', '=', True)], 'sequence': 2},
            'my': {'label': _('My Projects'), 'domain': ['|', '|', ('user_id', '=', user.id), ('partner_id', '=', user.partner_id.id), ('task_ids.user_ids', 'in', [user.id])], 'sequence': 3},
            'this_month': {'label': _('Created This Month'), 'domain': [('create_date', '>=', first_this_month), ('create_date', '<=', last_this_month)], 'sequence': 4},
            'last_month': {'label': _('Created Last Month'), 'domain': [('create_date', '>=', first_last_month), ('create_date', '<=', last_last_month)], 'sequence': 5},
            'this_year': {'label': _('Created This Year'), 'domain': [('create_date', '>=', first_this_year), ('create_date', '<=', last_this_year)], 'sequence': 6},
        }

    def _get_project_searchbar_sortings(self):
        return {
            'name': {'label': _('Name'), 'order': 'name asc', 'sequence': 1},
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc', 'sequence': 2},
            'date_asc': {'label': _('Oldest'), 'order': 'create_date asc, id asc', 'sequence': 3},
            'task_count': {'label': _('Task Count'), 'order': 'task_count desc, name asc', 'sequence': 4},
            'user_id': {'label': _('Project Manager'), 'order': 'user_id asc, name asc', 'sequence': 5},
        }

    def _get_project_searchbar_groupby(self, current_groupby=None):
        fields = [
            ('user_id', _('Project Manager')),
            ('partner_id', _('Customer')),
            ('date', _('Created Month')),
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
            ('user_id,partner_id', _('Manager > Customer')),
            ('partner_id,user_id', _('Customer > Manager')),
        ]
        for combo_key, combo_label in preset_combos:
            if combo_key not in gb_dict:
                gb_dict[combo_key] = {'label': combo_label, 'sequence': seq}
                seq += 1

        return gb_dict

    def _get_task_searchbar_filters(self):
        today = date.today()
        first_this_week = today - relativedelta(days=today.weekday())
        last_this_week = first_this_week + relativedelta(days=6)
        
        first_this_month = today.replace(day=1)
        last_this_month = (first_this_month + relativedelta(months=1)) - relativedelta(days=1)
        first_last_month = (today.replace(day=1)) - relativedelta(months=1)
        last_last_month = (today.replace(day=1)) - relativedelta(days=1)

        user = request.env.user
        return {
            'all': {'label': _('All Tasks'), 'domain': [], 'sequence': 1},
            'my': {'label': _('My Tasks'), 'domain': [('user_ids', 'in', [user.id])], 'sequence': 2},
            'open': {'label': _('Open Tasks'), 'domain': [('is_closed', '=', False)], 'sequence': 3},
            'closed': {'label': _('Closed Tasks'), 'domain': [('is_closed', '=', True)], 'sequence': 4},
            'unassigned': {'label': _('Unassigned Tasks'), 'domain': [('user_ids', '=', False)], 'sequence': 5},
            'high_priority': {'label': _('High Priority'), 'domain': [('priority', '=', '1')], 'sequence': 6},
            'overdue': {'label': _('Overdue Tasks'), 'domain': [('date_deadline', '<', today), ('is_closed', '=', False)], 'sequence': 7},
            'today': {'label': _('Deadline Today'), 'domain': [('date_deadline', '=', today)], 'sequence': 8},
            'this_week': {'label': _('Deadline This Week'), 'domain': [('date_deadline', '>=', first_this_week), ('date_deadline', '<=', last_this_week)], 'sequence': 9},
            'this_month': {'label': _('Deadline This Month'), 'domain': [('date_deadline', '>=', first_this_month), ('date_deadline', '<=', last_this_month)], 'sequence': 10},
        }

    def _get_task_searchbar_sortings(self):
        return {
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc', 'sequence': 1},
            'name': {'label': _('Title'), 'order': 'name asc', 'sequence': 2},
            'date_deadline': {'label': _('Deadline'), 'order': 'date_deadline asc, id desc', 'sequence': 3},
            'stage': {'label': _('Stage'), 'order': 'stage_id asc, sequence asc', 'sequence': 4},
            'priority': {'label': _('Priority'), 'order': 'priority desc, create_date desc', 'sequence': 5},
            'project': {'label': _('Project'), 'order': 'project_id asc, name asc', 'sequence': 6},
        }

    def _get_task_searchbar_groupby(self, current_groupby=None):
        fields = [
            ('project_id', _('Project')),
            ('stage_id', _('Stage')),
            ('user_ids', _('Assignee')),
            ('priority', _('Priority')),
            ('date_deadline', _('Deadline Month')),
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
            ('project_id,stage_id', _('Project > Stage')),
            ('project_id,user_ids', _('Project > Assignee')),
            ('stage_id,user_ids', _('Stage > Assignee')),
            ('user_ids,stage_id', _('Assignee > Stage')),
            ('priority,stage_id', _('Priority > Stage')),
        ]
        for combo_key, combo_label in preset_combos:
            if combo_key not in gb_dict:
                gb_dict[combo_key] = {'label': combo_label, 'sequence': seq}
                seq += 1

        return gb_dict

    def _get_project_searchbar_inputs(self):
        return {
            'all': {'input': 'all', 'label': _('Search in All'), 'order': 1},
            'name': {'input': 'name', 'label': _('Search in Name'), 'order': 2},
        }

    def _get_task_searchbar_inputs(self):
        return {
            'all': {'input': 'all', 'label': _('Search in All'), 'order': 1},
            'title': {'input': 'title', 'label': _('Search in Title'), 'order': 2},
            'user': {'input': 'user', 'label': _('Search in Assignee'), 'order': 3},
            'stage': {'input': 'stage', 'label': _('Search in Stage'), 'order': 4},
        }

    @http.route(['/my/custom/projects', '/my/custom/projects/page/<int:page>'], type='http', auth="user", website=True)
    def custom_portal_my_projects_redirect(self, page=1, **kw):
        return request.redirect(f'/my/projects?page={page}' if page > 1 else '/my/projects')

    @http.route(['/my/projects', '/my/projects/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_projects(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, search=None, search_in='all', groupby=None, **kw):
        args = request.httprequest.args or {}
        params = request.params or {}

        sortby = args.get('sortby') or params.get('sortby') or sortby or 'name'
        filterby = args.get('filterby') or params.get('filterby') or filterby or 'all'
        search = args.get('search') or params.get('search') or search or ''
        search_in = args.get('search_in') or params.get('search_in') or search_in or 'all'
        groupby = args.get('groupby') or params.get('groupby') or groupby or 'none'

        values = self._prepare_portal_layout_values()
        Project = request.env['project.project']
        domain = self._prepare_project_domain()

        filters = self._get_project_searchbar_filters()
        sortings = self._get_project_searchbar_sortings()
        groupbys = self._get_project_searchbar_groupby(current_groupby=groupby)
        inputs = self._get_project_searchbar_inputs()

        if sortby not in sortings:
            sortings[sortby] = {'label': sortby.replace('_id','').replace('_',' ').title(), 'order': 'name asc', 'sequence': 99}
        if filterby not in filters:
            filters[filterby] = {'label': filterby.replace('_',' ').title(), 'domain': [], 'sequence': 99}
        if groupby not in groupbys:
            groupbys[groupby] = {'label': groupby.replace('_ids','').replace('_id','').replace('_',' ').title(), 'sequence': 99}

        if filterby in filters and filters[filterby].get('domain'):
            domain += filters[filterby]['domain']

        if search:
            domain += [('name', 'ilike', search)]

        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        order = sortings.get(sortby, {}).get('order', 'name asc')

        projects = Project.search(domain, order=order)

        if groupby != 'none':
            gb_keys = [k.strip() for k in groupby.split(',') if k.strip()]
            group_tree = _build_n_level_project_groups(projects, gb_keys, depth=0)
            flat_rows = _flatten_project_group_tree(group_tree, parent_id="pgrp", depth=0)
        else:
            flat_rows = [{'type': 'project', 'parent_class': '', 'project': p} for p in projects]

        project_count = len(projects)
        pager = portal_pager(
            url="/my/projects",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'filterby': filterby, 'search': search, 'groupby': groupby},
            total=project_count,
            page=page,
            step=self._items_per_page
        )

        request.session['my_projects_history'] = projects.ids[:100]

        values.update({
            'default_url': '/my/projects',
            'date': date_begin,
            'date_end': date_end,
            'projects': projects,
            'flat_group_rows': flat_rows,
            'page_name': 'project',
            'pager': pager,
            'searchbar_sortings': sortings,
            'searchbar_filters': filters,
            'searchbar_groupby': groupbys,
            'searchbar_inputs': inputs,
            'sortby': sortby,
            'filterby': filterby,
            'search_in': search_in,
            'search': search,
            'groupby': groupby,
            'error_message': kw.get('error'),
        })
        return request.render("project.portal_my_projects", values)

    def _project_get_page_view_values(self, project, access_token, page=1, date_begin=None, date_end=None, sortby=None, search=None, search_in='content', groupby=None, **kwargs):
        args = request.httprequest.args or {}
        params = request.params or {}

        sortby = args.get('sortby') or params.get('sortby') or sortby or 'date'
        filterby = args.get('filterby') or params.get('filterby') or kwargs.get('filterby') or 'all'
        search = args.get('search') or params.get('search') or search or ''
        search_in = args.get('search_in') or params.get('search_in') or search_in or 'content'
        groupby = args.get('groupby') or params.get('groupby') or groupby or 'none'

        filters = self._get_task_searchbar_filters()
        sortings = self._get_task_searchbar_sortings()
        groupbys = self._get_task_searchbar_groupby(current_groupby=groupby)
        inputs = self._get_task_searchbar_inputs()

        if sortby not in sortings:
            sortings[sortby] = {'label': sortby.replace('_id','').replace('_',' ').title(), 'order': 'create_date desc, id desc', 'sequence': 99}
        if filterby not in filters:
            filters[filterby] = {'label': filterby.replace('_',' ').title(), 'domain': [], 'sequence': 99}
        if groupby not in groupbys:
            groupbys[groupby] = {'label': groupby.replace('_ids','').replace('_id','').replace('_',' ').title(), 'sequence': 99}

        order = sortings.get(sortby, {}).get('order', 'create_date desc, id desc')

        # Override to inject our Kanban & Multi-level GroupBy data
        # Pass valid ORM order string (e.g. 'create_date desc, id desc') to super() so base Odoo doesn't raise ValueError on field 'date'
        values = super()._project_get_page_view_values(project, access_token, page=page, date_begin=date_begin, date_end=date_end, sortby=order, search=search, search_in=search_in, groupby='none', **kwargs)
        
        Task = request.env['project.task']
        domain = [('project_id', '=', project.id)]

        if filterby in filters and filters[filterby].get('domain'):
            domain += filters[filterby]['domain']

        if search:
            if search_in == 'title' or search_in == 'name':
                domain += [('name', 'ilike', search)]
            elif search_in == 'user' or search_in == 'assignee':
                domain += [('user_ids.name', 'ilike', search)]
            elif search_in == 'stage':
                domain += [('stage_id.name', 'ilike', search)]
            else: # 'all' or 'content'
                domain += ['|', '|', ('name', 'ilike', search), ('description', 'ilike', search), ('user_ids.name', 'ilike', search)]

        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        order = sortings.get(sortby, {}).get('order', 'create_date desc, id desc')
        tasks = Task.sudo().search(domain, order=order)

        stages = request.env['project.task.type'].sudo().search([('project_ids', 'in', [project.id])], order='sequence')
        
        tasks_by_stage = {stage.id: [] for stage in stages}
        tasks_by_stage[False] = []
        
        for task in tasks:
            stage_id = task.stage_id.id if task.stage_id else False
            if stage_id in tasks_by_stage:
                tasks_by_stage[stage_id].append(task)
            else:
                tasks_by_stage[stage_id] = [task]

        if groupby != 'none':
            gb_keys = [k.strip() for k in groupby.split(',') if k.strip()]
            group_tree = _build_n_level_task_groups(tasks, gb_keys, depth=0)
            flat_rows = _flatten_task_group_tree(group_tree, parent_id="tgrp", depth=0)
        else:
            flat_rows = [{'type': 'task', 'parent_class': '', 'task': t} for t in tasks]

        is_employee = bool(request.env['hr.employee'].sudo().search([('user_id', '=', request.env.user.id)], limit=1))
        assignable_users = request.env['res.users'].sudo().search([])
        all_tags = request.env['project.tags'].sudo().search([])

        kanban_columns = self._build_kanban_columns(tasks, groupby, stages)

        values.update({
            'default_url': f'/my/projects/{project.id}',
            'stages': stages,
            'tasks_by_stage': tasks_by_stage,
            'kanban_columns': kanban_columns,
            'all_tasks': tasks,
            'grouped_tasks': [tasks] if tasks else [],
            'flat_group_rows': flat_rows,
            'view_type': request.params.get('view_type', 'kanban'),
            'searchbar_sortings': sortings,
            'searchbar_filters': filters,
            'searchbar_groupby': groupbys,
            'searchbar_inputs': inputs,
            'sortby': sortby,
            'filterby': filterby,
            'search_in': search_in,
            'search': search,
            'groupby': groupby,
            'csrf_token': request.csrf_token(),
            'error_message': kwargs.get('error'),
            'is_employee': is_employee,
            'assignable_users': assignable_users,
            'all_tags': all_tags,
        })
        return values

    def _build_kanban_columns(self, tasks, groupby, stages):
        primary_gb = (groupby or 'none').split(',')[0].strip()
        if primary_gb in ('user', 'user_ids'):
            user_ids = tasks.user_ids
            columns = []
            for user in user_ids:
                u_tasks = tasks.filtered(lambda t: user in t.user_ids)
                columns.append({
                    'id': user.id,
                    'title': user.name,
                    'tasks': u_tasks,
                })
            unassigned_tasks = tasks.filtered(lambda t: not t.user_ids)
            if unassigned_tasks or not columns:
                columns.append({
                    'id': 0,
                    'title': _('Unassigned'),
                    'tasks': unassigned_tasks,
                })
            return columns

        elif primary_gb == 'priority':
            priority_labels = dict(request.env['project.task']._fields['priority']._description_selection(request.env))
            columns = []
            for prio_val, prio_name in priority_labels.items():
                p_tasks = tasks.filtered(lambda t: t.priority == prio_val)
                columns.append({
                    'id': prio_val,
                    'title': prio_name,
                    'tasks': p_tasks,
                })
            return columns

        elif primary_gb == 'project_id':
            projects = tasks.mapped('project_id')
            columns = []
            for prj in projects:
                p_tasks = tasks.filtered(lambda t: t.project_id.id == prj.id)
                columns.append({
                    'id': prj.id,
                    'title': prj.name,
                    'tasks': p_tasks,
                })
            no_prj_tasks = tasks.filtered(lambda t: not t.project_id)
            if no_prj_tasks:
                columns.append({
                    'id': 0,
                    'title': _('No Project'),
                    'tasks': no_prj_tasks,
                })
            return columns

        elif primary_gb == 'date_deadline':
            columns_dict = {}
            for t in tasks:
                month_key = t.date_deadline.strftime('%B %Y') if t.date_deadline else _('No Deadline')
                if month_key not in columns_dict:
                    columns_dict[month_key] = []
                columns_dict[month_key].append(t)
            
            columns = []
            for month_key, t_list in columns_dict.items():
                columns.append({
                    'id': month_key,
                    'title': month_key,
                    'tasks': request.env['project.task'].sudo().concat(*t_list) if t_list else [],
                })
            return columns

        else:
            columns = []
            for stage in stages:
                s_tasks = tasks.filtered(lambda t: t.stage_id.id == stage.id)
                columns.append({
                    'id': stage.id,
                    'title': stage.name,
                    'tasks': s_tasks,
                })
            no_stage_tasks = tasks.filtered(lambda t: not t.stage_id)
            if no_stage_tasks:
                columns.append({
                    'id': 0,
                    'title': _('New / No Stage'),
                    'tasks': no_stage_tasks,
                })
            return columns


    def _task_get_page_view_values(self, task, access_token, **kwargs):
        values = super()._task_get_page_view_values(task, access_token, **kwargs)
        user = request.env.user
        is_employee = bool(request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)) or user.has_group('base.group_user')
        assignable_users = request.env['res.users'].sudo().search([])
        
        timesheets = values.get('timesheets')
        if timesheets and not is_employee:
            # Customer Portal User: show approved timesheets only
            if 'state' in timesheets._fields:
                timesheets = timesheets.filtered(lambda ts: ts.state == 'approved')
            values['timesheets'] = timesheets

        values['is_employee'] = is_employee
        values['assignable_users'] = assignable_users
        values['all_tags'] = request.env['project.tags'].sudo().search([])
        return values

    # KEEP OUR CUSTOM API ENDPOINTS BUT RENAME THEM
    @http.route(['/my/projects/create'], type='http', auth="user", methods=['POST'], website=True)
    def custom_project_create(self, **post):
        if not request.env.user.has_group('ucs_portal_self_service.group_portal_project_create'):
            return request.redirect('/my/projects')
            
        name = post.get('name')
        description = post.get('description', '')
        
        if name:
            try:
                request.env['project.project'].sudo().create({
                    'name': name,
                    'description': description,
                    'user_id': request.env.user.id,
                })
                request.env.flush_all()
            except Exception as e:
                request.env.cr.rollback()
                import urllib.parse
                return request.redirect('/my/projects?error=' + urllib.parse.quote(str(e).replace('\n', ' ')))
            
        return request.redirect('/my/projects')

    @http.route(['/my/tasks/create'], type='http', auth="user", methods=['POST'], website=True)
    def custom_task_create(self, **post):
        if not request.env.user.has_group('ucs_portal_self_service.group_portal_task_create'):
            return request.redirect('/my/projects')
            
        project_id = int(post.get('project_id', 0))
        name = post.get('name')
        description = post.get('description', '')
        date_deadline = post.get('date_deadline')
        allocated_hours_str = post.get('allocated_hours_str')
        user_id = int(post.get('user_id', 0)) if post.get('user_id') else False
        
        tag_ids_raw = request.httprequest.form.getlist('tag_ids')
        tag_ids = [int(tid) for tid in tag_ids_raw if tid and str(tid).isdigit()]
        
        if project_id and name:
            vals = {
                'name': name,
                'project_id': project_id,
                'description': description,
            }
            if tag_ids:
                vals['tag_ids'] = [(6, 0, tag_ids)]
            if date_deadline:
                vals['date_deadline'] = date_deadline
            if allocated_hours_str:
                try:
                    if ':' in allocated_hours_str:
                        h, m = allocated_hours_str.split(':')
                        vals['allocated_hours'] = float(h) + (float(m) / 60.0)
                    else:
                        vals['allocated_hours'] = float(allocated_hours_str)
                except ValueError:
                    pass
            if user_id:
                vals['user_ids'] = [(4, user_id)]
                
            try:
                request.env['project.task'].sudo().create(vals)
                request.env.flush_all()
            except Exception as e:
                request.env.cr.rollback()
                import urllib.parse
                return request.redirect(f'/my/projects/{project_id}?error=' + urllib.parse.quote(str(e).replace('\n', ' ')))
            
        return request.redirect(f'/my/projects/{project_id}')

    @http.route(['/my/tasks/update'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def custom_task_update(self, **post):
        if not request.env.user.has_group('ucs_portal_self_service.group_portal_task_create'):
            return request.redirect('/my/projects')
            
        task_id = int(post.get('task_id', 0))
        if not task_id:
            return request.redirect('/my/projects')
            
        # Get the task (we must ensure they have access to it)
        try:
            task = request.env['project.task'].browse(task_id)
            if not task.exists():
                return request.redirect('/my/projects')
        except Exception:
            return request.redirect('/my/projects')
            
        name = post.get('name')
        description = post.get('description', '')
        date_deadline = post.get('date_deadline')
        allocated_hours_str = post.get('allocated_hours_str')
        user_id = int(post.get('user_id', 0)) if post.get('user_id') else False
        
        tag_ids_raw = request.httprequest.form.getlist('tag_ids')
        tag_ids = [int(tid) for tid in tag_ids_raw if tid and str(tid).isdigit()]
        
        if name:
            vals = {
                'name': name,
                'description': description,
                'tag_ids': [(6, 0, tag_ids)],
            }
            if date_deadline:
                vals['date_deadline'] = date_deadline
            else:
                vals['date_deadline'] = False
                
            if allocated_hours_str:
                try:
                    if ':' in allocated_hours_str:
                        h, m = allocated_hours_str.split(':')
                        vals['allocated_hours'] = float(h) + (float(m) / 60.0)
                    else:
                        vals['allocated_hours'] = float(allocated_hours_str)
                except ValueError:
                    vals['allocated_hours'] = 0.0
            else:
                vals['allocated_hours'] = 0.0
                
            if user_id:
                vals['user_ids'] = [(6, 0, [user_id])]
            else:
                vals['user_ids'] = [(5, 0, 0)]
                
            try:
                task.sudo().write(vals)
                request.env.flush_all()
            except Exception as e:
                request.env.cr.rollback()
                import urllib.parse
                return request.redirect(f'/my/tasks/{task_id}?error=' + urllib.parse.quote(str(e).replace('\n', ' ')))
            
        return request.redirect(f'/my/tasks/{task_id}')

    @http.route(['/my/tasks/update_stage'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def update_task_stage(self, **post):
        task_id = int(post.get('task_id', 0))
        stage_id = int(post.get('stage_id', 0))
        
        if task_id and stage_id:
            task = request.env['project.task'].sudo().search([('id', '=', task_id)])
            if task:
                try:
                    task.write({'stage_id': stage_id})
                    return json.dumps({'success': True})
                except Exception as e:
                    return json.dumps({'success': False, 'error': str(e)})
        return json.dumps({'success': False, 'error': 'Invalid parameters'})
