from odoo import models, fields

class ProjectTask(models.Model):
    _inherit = 'project.task'

    client_deadline = fields.Date(string="Client Deadline", tracking=True)
    client_allocated_hours = fields.Float(string="Client Allocated Hours", tracking=True)
