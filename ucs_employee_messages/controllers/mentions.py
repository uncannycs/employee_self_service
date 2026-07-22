# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class PortalMentions(http.Controller):

    @http.route(['/my/mentions/suggest'], type='jsonrpc', auth="user")
    def get_mention_suggestions(self, model, res_id, term=''):
        """Fetch users to mention based on channel members or task followers."""
        res_id = int(res_id)
        term = term.lower()
        suggestions = []
        
        if model == 'discuss.channel':
            # Get members of the channel
            members = request.env['discuss.channel.member'].sudo().search([
                ('channel_id', '=', res_id)
            ])
            partners = members.mapped('partner_id')
            
            for partner in partners:
                if not term or term in partner.name.lower():
                    suggestions.append({
                        'id': partner.id,
                        'name': partner.name,
                    })
                    
        elif model == 'project.task':
            # Get task assignees and followers
            task = request.env['project.task'].sudo().browse(res_id)
            if task.exists():
                partners = task.user_ids.mapped('partner_id') | task.message_partner_ids
                for partner in partners:
                    if not term or term in partner.name.lower():
                        # Avoid duplicates
                        if not any(s['id'] == partner.id for s in suggestions):
                            suggestions.append({
                                'id': partner.id,
                                'name': partner.name,
                            })
                            
        # Sort and limit to 8 suggestions
        suggestions = sorted(suggestions, key=lambda k: k['name'])[:8]
        return suggestions
