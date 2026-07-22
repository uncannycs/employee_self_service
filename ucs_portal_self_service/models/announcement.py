# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PortalAnnouncement(models.Model):
    _name = 'ucs.portal.announcement'
    _description = 'Portal Announcement'
    _order = 'date desc, id desc'

    name = fields.Char(string='Title', required=True)
    content = fields.Html(string='Content', required=True)
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    active = fields.Boolean(string='Active', default=True)
    
    # Optional: target specific departments or employees
    # department_id = fields.Many2one('hr.department', string='Target Department')
