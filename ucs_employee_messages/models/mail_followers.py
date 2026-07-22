# -*- coding: utf-8 -*-
from odoo import models, api


class MailFollowers(models.Model):
    _inherit = 'mail.followers'

    def unlink(self):
        """On follower removal, re-sync project discuss channel membership."""
        projects = self.env['project.project'].search([
            ('id', 'in', self.filtered(
                lambda f: f.res_model == 'project.project'
            ).mapped('res_id'))
        ])
        res = super().unlink()
        for project in projects:
            project._sync_discuss_channel_members()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """On follower addition, re-sync project discuss channel membership."""
        followers = super().create(vals_list)
        projects = self.env['project.project'].search([
            ('id', 'in', followers.filtered(
                lambda f: f.res_model == 'project.project'
            ).mapped('res_id'))
        ])
        for project in projects:
            project._sync_discuss_channel_members()
        return followers
