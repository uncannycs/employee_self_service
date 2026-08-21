from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    """ Inherit settings configuration model for attendance regularization parameters. """
    _inherit = 'res.config.settings'

    regularize_request_per_month = fields.Integer(
        related='company_id.regularize_request_per_month', 
        readonly=False, 
        string='Regularize Requests Per Month', 
        help='Employee can per month regularize request, this is also renew start month 1st date'
    )

    def action_update_regularize_requests(self):
        """ Manually sync and assign regularization request quota to all company employees. """
        self.ensure_one()
        employees = self.env['hr.employee'].search([('company_id', '=', self.company_id.id)])
        employees.write({'regularize_request_assign': self.regularize_request_per_month})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Successfully updated the regularization requests limit for all employees.',
                'type': 'success',
                'sticky': False,
            }
        }
