# -*- coding: utf-8 -*-
from odoo import models, fields

class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    mandatory_attachment = fields.Boolean(
        string="Mandatory Attachment",
        default=False,
        help="Require attachment when leave request duration exceeds threshold days."
    )
    mandatory_attachment_min_days = fields.Float(
        string="Mandatory Attachment Min Days",
        default=2.0,
        help="Minimum duration (in days) after which attachment is required (e.g. Sick Leave > 2 days)."
    )
