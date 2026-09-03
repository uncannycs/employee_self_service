# -*- coding: utf-8 -*-
import re
import logging
from werkzeug.exceptions import NotFound

from odoo import http, _
from odoo.fields import Domain
from odoo.http import request
from odoo.addons.portal.controllers.portal_thread import PortalChatter
from odoo.addons.mail.controllers.thread import ThreadController
from odoo.addons.portal.utils import get_portal_partner

_logger = logging.getLogger(__name__)


class CustomPortalChatter(PortalChatter):

    @http.route('/mail/chatter_fetch', type='jsonrpc', auth='public', website=True)
    def portal_message_fetch(self, thread_model, thread_id, fetch_params=None, **kw):
        """ Override portal_message_fetch to:
            1. Include tracking logs and notes in portal Communication History.
            2. Filter field tracking values and messages based on role-based field security:
               - Employees: see Developer Deadline & Hours, hide Client Deadline & Hours.
               - Clients: see Client Deadline & Hours, hide Developer Deadline & Hours.
               - Project Managers: see ALL fields.
        """
        env = request.env if (request and hasattr(request, 'env') and request.env) else thread_model.env if hasattr(thread_model, 'env') else False
        if not env and kw.get('env'):
            env = kw['env']
        if not env:
            env = self.env
        user = env.user
        
        # Check thread access
        if kw.get('token'):
            thread = ThreadController._get_thread_with_access(
                thread_model, thread_id, token=kw.get("token"),
            )
            if not thread:
                raise NotFound()
            if portal_partner := get_portal_partner(
                thread, _hash=None, pid=None, token=kw.get("token"),
            ):
                if request and hasattr(request, 'update_context'):
                    request.update_context(
                        portal_data={"portal_partner": portal_partner, "portal_thread": thread}
                    )
        else:
            thread = env[thread_model].sudo().browse(thread_id)
            if not thread.exists():
                raise NotFound()

        # Build expanded domain to fetch comments, log notes, and tracking changes
        domain = Domain([
            ('model', '=', thread_model),
            ('res_id', '=', thread_id),
            '|', '|',
            ('body', 'not in', [False, '', '<span class="o-mail-Message-edited"></span>']),
            ('tracking_value_ids', '!=', False),
            ('attachment_ids', '!=', False)
        ])

        if not user._is_internal():
            # Non-employee sees only non-internal messages
            domain = env['mail.message']._get_search_domain_share() & domain

        Message = env['mail.message'].sudo()
        res = Message._message_fetch(domain, **(fetch_params or {}))
        messages = res.pop("messages")

        # Determine hidden tracking fields based on user role
        is_pm = (
            user.has_group('ucs_portal_self_service.group_custom_project_manager') or
            user.has_group('project.group_project_manager') or
            user.has_group('base.group_erp_manager')
        )
        
        is_employee = False
        if hasattr(user, 'login') and user.login:
            is_employee = bool(env['hr.employee'].sudo().search([
                '|', ('user_id', '=', user.id), ('work_email', '=', user.login)
            ], limit=1))
        else:
            is_employee = bool(env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1))
            
        if not is_employee and user.has_group('base.group_user'):
            is_employee = True

        hidden_fields = set()
        if not is_pm:
            if is_employee:
                # Employee user: hide Client fields
                hidden_fields = {'client_deadline', 'client_allocated_hours'}
            else:
                # External / Client user: hide Developer fields
                hidden_fields = {'date_deadline', 'allocated_hours'}

        filtered_messages = env['mail.message'].sudo()
        formatted_tracking_map = {}

        for msg in messages:
            tracking_values = msg.tracking_value_ids
            visible_trackings = [t for t in tracking_values if t.field_id.name not in hidden_fields] if tracking_values else []

            body = msg.body or ''
            if body and hidden_fields:
                body_lines = re.split(r'<br\s*/?>', body, flags=re.IGNORECASE) if ('<br' in body or '<BR' in body) else body.split('\n')
                filtered_lines = []
                for line in body_lines:
                    hide_line = False
                    for hf in hidden_fields:
                        label = 'Client' if 'client' in hf else ('Developer' if 'date_deadline' in hf or 'allocated_hours' in hf else hf)
                        if hf in line or (label == 'Client' and 'Client' in line) or (label == 'Developer' and 'Developer' in line):
                            hide_line = True
                            break
                    if not hide_line:
                        filtered_lines.append(line)
                body = '<br/>'.join(filtered_lines) if ('<br' in (msg.body or '') or '<BR' in (msg.body or '')) else '\n'.join(filtered_lines)

            tracking_html = ""
            if visible_trackings:
                items = []
                for t in visible_trackings:
                    fname = t.field_id.name
                    fdesc = t.field_id.field_description or fname
                    if fname == 'date_deadline':
                        fdesc = 'Developer Deadline'
                    elif fname == 'client_deadline':
                        fdesc = 'Client Deadline'
                    elif fname == 'allocated_hours':
                        fdesc = 'Developer Allocated Hours'
                    elif fname == 'client_allocated_hours':
                        fdesc = 'Client Allocated Hours'

                    old_val = t.old_value_char or t.old_value_float or t.old_value_datetime or 'None'
                    new_val = t.new_value_char or t.new_value_float or t.new_value_datetime or 'None'

                    if isinstance(old_val, float) and 'hours' in fname:
                        old_val = f"{int(old_val):02d}:{int(round((old_val % 1) * 60)):02d}"
                    if isinstance(new_val, float) and 'hours' in fname:
                        new_val = f"{int(new_val):02d}:{int(round((new_val % 1) * 60)):02d}"

                    items.append(f"<li style='margin-bottom: 2px;'><strong>{fdesc}:</strong> <i>{old_val}</i> &rarr; <b>{new_val}</b></li>")

                if items:
                    tracking_html = (
                        '<div class="o_tracking_values" style="font-size:0.85rem; color:#495057; margin-top:4px;">'
                        '<ul style="margin:0; padding-left:16px; list-style-type:disc;">'
                        + ''.join(items) +
                        '</ul></div>'
                    )

            has_body = bool(body and body.strip())
            has_attachments = bool(msg.attachment_ids)
            has_trackings = bool(tracking_html)

            if not has_body and not has_attachments and not has_trackings:
                continue

            filtered_messages |= msg
            final_body = (body or '') + tracking_html
            formatted_tracking_map[msg.id] = final_body

        formatted_dicts = filtered_messages.portal_message_format(options=kw)
        for val_dict in formatted_dicts:
            mid = val_dict.get('id')
            if mid in formatted_tracking_map:
                val_dict['body'] = ["markup", formatted_tracking_map[mid]]

        return {
            **res,
            "data": {"mail.message": formatted_dicts},
            "messages": filtered_messages.ids,
        }
