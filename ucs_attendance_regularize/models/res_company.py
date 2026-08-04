from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    regularize_request_per_month = fields.Integer(string='Regularize Requests Per Month', default=0)
