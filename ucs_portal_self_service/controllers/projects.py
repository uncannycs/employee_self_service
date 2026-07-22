# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.project.controllers.portal import ProjectCustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, MissingError
import json


class PortalCustomProjects(ProjectCustomerPortal):



    @http.route(['/my/custom/projects', '/my/custom/projects/page/<int:page>'], type='http', auth="user", website=True)
    def custom_portal_my_projects_redirect(self, page=1, **kw):
        return request.redirect(f'/my/projects?page={page}' if page > 1 else '/my/projects')

    @http.route(['/my/projects', '/my/projects/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_projects(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        Project = request.env['project.project']
        domain = self._prepare_project_domain()

        searchbar_sortings = self._prepare_searchbar_sortings()
        if not sortby:
            sortby = 'name'
        order = searchbar_sortings[sortby]['order']

        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        # We use standard search without sudo to rely on ir.rule for access rights
        project_count = Project.search_count(domain)
        pager = portal_pager(
            url="/my/projects",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
            total=project_count,
            page=page,
            step=self._items_per_page
        )

        projects = Project.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_projects_history'] = projects.ids[:100]

        values.update({
            'date': date_begin,
            'date_end': date_end,
            'projects': projects,
            'page_name': 'project',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'error_message': kw.get('error'),
        })
        return request.render("project.portal_my_projects", values)

    def _project_get_page_view_values(self, project, access_token, page=1, date_begin=None, date_end=None, sortby=None, search=None, search_in='content', groupby=None, **kwargs):
        # Override to inject our Kanban data
        values = super()._project_get_page_view_values(project, access_token, page, date_begin, date_end, sortby, search, search_in, groupby, **kwargs)
        
        # We need stages for our custom Kanban board
        stages = request.env['project.task.type'].sudo().search([('project_ids', 'in', [project.id])], order='sequence')
        
        # Flatten the standard grouped tasks to get the filtered list of tasks
        filtered_tasks_list = []
        for group in values.get('grouped_tasks', []):
            filtered_tasks_list.extend(list(group))
            
        if filtered_tasks_list:
            tasks = request.env['project.task'].sudo().browse([t.id for t in filtered_tasks_list])
        else:
            tasks = request.env['project.task'].sudo().browse()
        
        tasks_by_stage = {stage.id: [] for stage in stages}
        tasks_by_stage[False] = []
        
        for task in tasks:
            stage_id = task.stage_id.id if task.stage_id else False
            if stage_id in tasks_by_stage:
                tasks_by_stage[stage_id].append(task)
            else:
                tasks_by_stage[stage_id] = [task]
                
        # Check if user is an employee
        is_employee = bool(request.env['hr.employee'].sudo().search([('user_id', '=', request.env.user.id)], limit=1))
        
        assignable_users = request.env['res.users'].sudo().search([])
        
        values.update({
            'stages': stages,
            'tasks_by_stage': tasks_by_stage,
            'all_tasks': tasks,
            'view_type': request.params.get('view_type', 'kanban'),
            'csrf_token': request.csrf_token(),
            'error_message': kwargs.get('error'),
            'is_employee': is_employee,
            'assignable_users': assignable_users,
        })
        return values

    def _task_get_page_view_values(self, task, access_token, **kwargs):
        values = super()._task_get_page_view_values(task, access_token, **kwargs)
        is_employee = bool(request.env['hr.employee'].sudo().search([('user_id', '=', request.env.user.id)], limit=1))
        assignable_users = request.env['res.users'].sudo().search([])
        values['is_employee'] = is_employee
        values['assignable_users'] = assignable_users
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
        
        if project_id and name:
            vals = {
                'name': name,
                'project_id': project_id,
                'description': description,
            }
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
        
        if name:
            vals = {
                'name': name,
                'description': description,
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
