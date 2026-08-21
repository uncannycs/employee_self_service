from odoo import models, fields

class ResCompany(models.Model):
    """ Inherit company model to store monthly attendance regularization quota setting. """
    _inherit = 'res.company'

    regularize_request_per_month = fields.Integer(string='Regularize Requests Per Month', default=0)
