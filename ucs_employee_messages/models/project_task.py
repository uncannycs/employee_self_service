# -*- coding: utf-8 -*-
import html
from odoo import models, fields
from markupsafe import Markup


class ProjectTask(models.Model):
    _inherit = 'project.task'

    user_ids = fields.Many2many('res.users', domain="[('active', '=', True)]")

    def message_post(self, **kwargs):
        """
        Auto-detect @mentions and forward task messages to the
        'Task Discussion' channel only (not the general Discussion channel).

        Forwarded message types:
          - 'comment'   → regular user message sent from the chatter
          - 'email'     → messages received via email
          message_type 'notification' (system tracking) is NOT forwarded.
        Log notes (subtype: mail.mt_note) are also forwarded with a [Log Note] label.
        """
        body = kwargs.get('body', '')

        # ── @mention processing ───────────────────────────────────────────────
        if body and not self.env.context.get('skip_task_forwarding'):
            possible_partners = (
                self.sudo().user_ids.mapped('partner_id') | self.sudo().message_partner_ids
            )
            mentioned_partner_ids = list(kwargs.get('partner_ids') or [])

            for partner in possible_partners:
                mention_str = f"@{partner.name}"
                if mention_str in str(body):
                    if partner.id not in mentioned_partner_ids:
                        mentioned_partner_ids.append(partner.id)

            kwargs['partner_ids'] = mentioned_partner_ids

        message = super(ProjectTask, self).message_post(**kwargs)

        # ── Forward to Task Discussion channel ────────────────────────────────
        task_channel = (
            self.project_id.task_discuss_channel_id
            if self.project_id else False
        )

        should_forward = (
            task_channel
            and message.message_type in ('comment', 'email')
            and not self._context.get('skip_task_forwarding')
        )

        if should_forward:
            body_forwarded = kwargs.get('body', '')
            task_link = (
                f"<a href='#' data-oe-model='project.task'"
                f" data-oe-id='{self.id}'>{self.name}</a>"
            )
            author_name = message.author_id.name or 'A user'

            # Detect log note (subtype = mail.mt_note)
            subtype = kwargs.get('subtype_xmlid', '') or ''
            is_log_note = 'mt_note' in subtype

            label = (
                "<span style='color:#e67e22;font-weight:600;'>[Log Note]</span> "
                if is_log_note else ""
            )

            prefix = (
                f"<div class='text-muted' style='font-size:0.85rem;margin-bottom:4px;'>"
                f"<i class='fa fa-tasks'></i> {label}"
                f"<strong>{author_name}</strong> — Task: {task_link}"
                f"</div>"
            )
            new_body = Markup(f"{prefix}{body_forwarded}")

            task_channel.sudo().with_context(
                skip_task_forwarding=True
            ).message_post(
                body=new_body,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=message.author_id.id,
                attachment_ids=kwargs.get('attachment_ids', []),
            )

        return message
