# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ProjectTags(models.Model):
    _inherit = 'project.tags'

    color_badge_style = fields.Char(compute='_compute_color_badge_style')

    @api.depends('color')
    def _compute_color_badge_style(self):
        styles = {
            0: "background-color: #6c757d; color: #ffffff;",
            1: "background-color: #ef4444; color: #ffffff;",
            2: "background-color: #f97316; color: #ffffff;",
            3: "background-color: #eab308; color: #1e293b;",
            4: "background-color: #22c55e; color: #ffffff;",
            5: "background-color: #06b6d4; color: #ffffff;",
            6: "background-color: #3b82f6; color: #ffffff;",
            7: "background-color: #6366f1; color: #ffffff;",
            8: "background-color: #a855f7; color: #ffffff;",
            9: "background-color: #ec4899; color: #ffffff;",
            10: "background-color: #14b8a6; color: #ffffff;",
            11: "background-color: #f43f5e; color: #ffffff;",
        }
        for tag in self:
            tag.color_badge_style = styles.get((tag.color or 0) % 12, styles[0])
