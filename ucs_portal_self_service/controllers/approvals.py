# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal

class PortalApprovals(CustomerPortal):
    
    def _prepare_approvals_values(self):
        """
        Hook method for sub-modules to inject their own approval data.
        Returns a dictionary of values to be passed to the template.
        """
        return {
            'page_name': 'approvals',
            'error_message': request.params.get('error'),
        }

    @http.route(['/my/approvals'], type='http', auth="user", website=True)
    def portal_my_approvals(self, **kw):
        values = self._prepare_approvals_values()
        return request.render("ucs_portal_self_service.portal_my_approvals", values)
