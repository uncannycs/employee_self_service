# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
import urllib.parse

class SubTaskPortal(CustomerPortal):
    """ Portal controller extension for creating, linking, and unlinking sub-tasks under a parent task. """

    def _task_get_page_view_values(self, task, access_token, **kwargs):
        """ Inject sub-tasks list, count, and creation access permissions into task page context. """
        values = super()._task_get_page_view_values(task, access_token, **kwargs)
        if task:
            values['subtasks'] = task.child_ids.sudo()
            values['subtask_count'] = len(task.child_ids)
            
            user = request.env.user
            # Strict permission check: ONLY users with group_portal_task_create group can create new tasks
            has_create = user.has_group('ucs_portal_self_service.group_portal_task_create')
            values['has_task_create_access'] = has_create

            if task.project_id:
                existing_tasks = request.env['project.task'].sudo().search([
                    ('project_id', '=', task.project_id.id),
                    ('id', '!=', task.id),
                    ('parent_id', '!=', task.id),
                ], order='name asc')
                values['project_existing_tasks'] = existing_tasks
            else:
                values['project_existing_tasks'] = request.env['project.task'].sudo()

        return values

    @http.route(['/my/subtask/create'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def portal_subtask_create(self, **post):
        """ Handle portal request to link an existing task or create a new sub-task under a parent task. """
        parent_id = post.get('parent_id')
        if not parent_id:
            return request.redirect('/my/projects')

        try:
            parent_id_int = int(parent_id)
            parent_task = request.env['project.task'].sudo().browse(parent_id_int)
            if not parent_task.exists():
                return request.redirect('/my/projects')
        except Exception:
            return request.redirect('/my/projects')

        subtask_mode = post.get('subtask_mode', 'existing')
        existing_task_id = post.get('existing_task_id')

        # Mode 1: Link Existing Task
        if subtask_mode == 'existing' or existing_task_id:
            if existing_task_id:
                try:
                    exist_id_int = int(existing_task_id)
                    exist_task = request.env['project.task'].sudo().browse(exist_id_int)
                    if exist_task.exists():
                        exist_task.write({'parent_id': parent_task.id})
                        request.env.flush_all()
                except Exception as e:
                    request.env.cr.rollback()
                    return request.redirect(f'/my/tasks/{parent_task.id}?error=' + urllib.parse.quote(str(e).replace('\n', ' ')))
            return request.redirect(f'/my/tasks/{parent_task.id}')

        # Mode 2: Create New Sub-task (Strict permission check)
        user = request.env.user
        has_create = user.has_group('ucs_portal_self_service.group_portal_task_create')
        if not has_create:
            return request.redirect(f'/my/tasks/{parent_task.id}?error=Permission+Denied')

        name = post.get('name', '').strip()
        description = post.get('description', '')
        date_deadline = post.get('date_deadline') or False
        allocated_hours_str = post.get('allocated_hours_str', '')
        user_id_raw = post.get('user_id')
        
        tag_ids_raw = request.httprequest.form.getlist('tag_ids')
        tag_ids = [int(tid) for tid in tag_ids_raw if tid and str(tid).isdigit()]

        allocated_hours = 0.0
        if allocated_hours_str:
            try:
                if ':' in allocated_hours_str:
                    hrs, mins = allocated_hours_str.split(':')
                    allocated_hours = float(hrs) + (float(mins) / 60.0)
                else:
                    allocated_hours = float(allocated_hours_str)
            except ValueError:
                allocated_hours = 0.0

        user_ids = []
        if user_id_raw:
            try:
                user_ids = [(6, 0, [int(user_id_raw)])]
            except ValueError:
                pass

        if name:
            try:
                vals = {
                    'name': name,
                    'description': description,
                    'parent_id': parent_task.id,
                    'project_id': parent_task.project_id.id if parent_task.project_id else False,
                    'date_deadline': date_deadline,
                }
                
                if 'developer_allocated_hours' in request.env['project.task']._fields:
                    vals['developer_allocated_hours'] = allocated_hours
                if 'allocated_hours' in request.env['project.task']._fields:
                    vals['allocated_hours'] = allocated_hours
                    
                if user_ids:
                    vals['user_ids'] = user_ids
                    
                if tag_ids:
                    vals['tag_ids'] = [(6, 0, tag_ids)]
                    
                if parent_task.project_id and parent_task.project_id.type_ids:
                    vals['stage_id'] = parent_task.project_id.type_ids[0].id

                request.env['project.task'].sudo().create(vals)
                request.env.flush_all()
            except Exception as e:
                request.env.cr.rollback()
                return request.redirect(f'/my/tasks/{parent_task.id}?error=' + urllib.parse.quote(str(e).replace('\n', ' ')))

        return request.redirect(f'/my/tasks/{parent_task.id}')

    @http.route(['/my/subtask/unlink'], type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def portal_subtask_unlink(self, **post):
        """ Unlink a sub-task from its parent task in portal. """
        subtask_id = post.get('subtask_id')
        parent_id = post.get('parent_id')
        if not parent_id:
            return request.redirect('/my/projects')

        try:
            parent_id_int = int(parent_id)
            parent_task = request.env['project.task'].sudo().browse(parent_id_int)
        except Exception:
            return request.redirect('/my/projects')

        if subtask_id:
            try:
                subtask_id_int = int(subtask_id)
                subtask = request.env['project.task'].sudo().browse(subtask_id_int)
                if subtask.exists() and subtask.parent_id.id == parent_task.id:
                    subtask.write({'parent_id': False})
                    request.env.flush_all()
            except Exception as e:
                request.env.cr.rollback()
                return request.redirect(f'/my/tasks/{parent_task.id}?error=' + urllib.parse.quote(str(e).replace('\n', ' ')))

        return request.redirect(f'/my/tasks/{parent_task.id}')
