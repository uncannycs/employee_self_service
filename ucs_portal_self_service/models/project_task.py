from odoo import models, fields, api
from odoo.tools import html2plaintext

class ProjectTask(models.Model):
    _inherit = 'project.task'

    client_deadline = fields.Date(string="Client Deadline", tracking=True)
    client_allocated_hours = fields.Float(string="Client Allocated Hours", tracking=True)
    description_plain = fields.Char(compute='_compute_description_plain')

    @api.depends('description')
    def _compute_description_plain(self):
        for task in self:
            if task.description:
                task.description_plain = html2plaintext(task.description).strip()
            else:
                task.description_plain = ''
