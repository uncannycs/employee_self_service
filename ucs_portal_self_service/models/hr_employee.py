# -*- coding: utf-8 -*-
from odoo import models, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def write(self, vals):
        # We pass a context flag so res.users can avoid adding backend groups to portal users
        return super(HrEmployee, self.with_context(ignore_portal_group_assignments=True)).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        return super(HrEmployee, self.with_context(ignore_portal_group_assignments=True)).create(vals_list)
