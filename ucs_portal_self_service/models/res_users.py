# -*- coding: utf-8 -*-
from odoo import models, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    def write(self, vals):
        if 'group_ids' in vals and self.env.context.get('ignore_portal_group_assignments'):
            portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
            internal_group = self.env.ref('base.group_user', raise_if_not_found=False)
            
            if portal_group and internal_group:
                # Iterate over the users we are writing to.
                # If any of them is a portal user, we should strip out internal group assignments.
                # Odoo sets group_ids like [(4, id), ...]
                has_portal_user = any(portal_group in u.group_ids for u in self)
                if has_portal_user:
                    # We are in hr.employee write/create context. Odoo only assigns groups here
                    # to grant backend access rights (like leave manager, timesheet approver).
                    # Since this is a portal user, granting backend rights crashes the system.
                    # We can safely pop group_ids to skip this assignment entirely.
                    vals.pop('group_ids')

        return super(ResUsers, self).write(vals)