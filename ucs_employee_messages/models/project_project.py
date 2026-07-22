# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # Channel 1: General discussion (e.g. "Discussion: Alpha Project")
    discuss_channel_id = fields.Many2one(
        'discuss.channel', string='Discussion Channel', copy=False
    )
    # Channel 2: Task-related messages (e.g. "Task Discussion: Alpha Project")
    task_discuss_channel_id = fields.Many2one(
        'discuss.channel', string='Task Discussion Channel', copy=False
    )

    # ── Button action: manually create BOTH channels ──────────────────────────
    def action_create_discuss_channels(self):
        """Create Discussion + Task Discussion channels for this project."""
        for project in self:
            project._create_both_channels()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Channels Created',
                'message': 'Discussion and Task Discussion channels have been created.',
                'type': 'success',
                'sticky': False,
            },
        }

    def _create_both_channels(self):
        """Internal: create the two channels if they don't exist yet."""
        self.ensure_one()
        partners = self.message_follower_ids.mapped('partner_id')

        # Channel 1 — Discussion
        if not self.discuss_channel_id:
            ch1 = self.env['discuss.channel'].sudo().create({
                'name': f"Discussion: {self.name}",
                'channel_type': 'group',
            })
            self.discuss_channel_id = ch1.id
            if partners:
                ch1.add_members(partner_ids=partners.ids)

        # Channel 2 — Task Discussion
        if not self.task_discuss_channel_id:
            ch2 = self.env['discuss.channel'].sudo().create({
                'name': f"Task Discussion: {self.name}",
                'channel_type': 'group',
            })
            self.task_discuss_channel_id = ch2.id
            if partners:
                ch2.add_members(partner_ids=partners.ids)

    # ── Member sync helpers (for follower add/remove) ─────────────────────────
    def _sync_discuss_channel_members(self):
        """Keep both channels in sync with current project followers."""
        self.ensure_one()
        self.invalidate_recordset(['message_follower_ids'])
        partners = self.message_follower_ids.mapped('partner_id')

        for channel_field in ['discuss_channel_id', 'task_discuss_channel_id']:
            channel = getattr(self, channel_field)
            if not channel:
                continue
            channel = channel.sudo()
            existing = channel.channel_member_ids.mapped('partner_id')
            to_add = partners - existing
            to_remove = existing - partners
            if to_add:
                channel.add_members(partner_ids=to_add.ids)
            if to_remove:
                channel.channel_member_ids.filtered(
                    lambda m: m.partner_id in to_remove
                ).unlink()

    def _message_subscribe(self, partner_ids=None, subtype_ids=None, customer_ids=None):
        res = super()._message_subscribe(
            partner_ids=partner_ids, subtype_ids=subtype_ids, customer_ids=customer_ids
        )
        for project in self:
            project._sync_discuss_channel_members()
        return res

    def message_unsubscribe(self, partner_ids=None):
        res = super().message_unsubscribe(partner_ids=partner_ids)
        for project in self:
            project._sync_discuss_channel_members()
        return res

    def write(self, vals):
        res = super().write(vals)
        if 'message_follower_ids' in vals or 'user_id' in vals:
            for project in self:
                project._sync_discuss_channel_members()
        return res
