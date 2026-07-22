from odoo import models, fields

class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    is_in_progress_stage = fields.Boolean(string="Is In-Progress Stage")
    is_done_stage = fields.Boolean(string="Is Done Stage")
