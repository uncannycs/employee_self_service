from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    regularize_request_assign = fields.Integer(string='Regularization Requests Assigned', default=0)
    regularize_req_used = fields.Integer(string='Regularization Requests Used', default=0)

    @api.model
    def _cron_reset_regularize_requests(self):
        for company in self.env['res.company'].search([]):
            employees = self.search([('company_id', '=', company.id)])
            employees.write({
                'regularize_request_assign': company.regularize_request_per_month,
                'regularize_req_used': 0
            })
