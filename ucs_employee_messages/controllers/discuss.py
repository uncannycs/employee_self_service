# -*- coding: utf-8 -*-
import html
from odoo import http, fields, _
from odoo.http import request
from markupsafe import Markup
from werkzeug.exceptions import NotFound, Forbidden

class PortalDiscuss(http.Controller):

    @http.route(['/my/chats'], type='http', auth="user", website=True)
    def portal_my_chats(self, **kw):
        user = request.env.user
        partner = user.partner_id
        
        # Get channels where the user is a member using sudo
        channels = request.env['discuss.channel'].sudo().search([
            ('channel_member_ids.partner_id', '=', partner.id),
            ('channel_type', 'in', ['channel', 'group']) # Get project channels
        ])
        
        # Fetch unread counts for these channels
        members = request.env['discuss.channel.member'].sudo().search([
            ('partner_id', '=', partner.id),
            ('channel_id', 'in', channels.ids)
        ])
        unread_counts = {m.channel_id.id: m.message_unread_counter for m in members}
        
        values = {
            'channels': channels,
            'unread_counts': unread_counts,
            'page_name': 'chats',
        }
        return request.render("ucs_portal_self_service.portal_my_chats", values)

    @http.route(['/my/chats/<int:channel_id>'], type='http', auth="user", website=True)
    def portal_chat_room(self, channel_id, **kw):
        user = request.env.user
        partner = user.partner_id
        
        # Ensure channel exists and user is a member
        channel = request.env['discuss.channel'].search([
            ('id', '=', channel_id),
            ('channel_member_ids.partner_id', '=', partner.id)
        ], limit=1)
        
        if not channel:
            raise NotFound()
            
        # Reset unread counter by setting last seen message
        member = request.env['discuss.channel.member'].sudo().search([
            ('channel_id', '=', channel.id),
            ('partner_id', '=', partner.id)
        ], limit=1)
        
        last_message = request.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
        ], limit=1, order='id DESC')
        
        if member and last_message:
            member.sudo()._mark_as_read(last_message.id)
            
        values = {
            'channel': channel,
            'page_name': 'chats',
            'partner': partner,
        }
        return request.render("ucs_portal_self_service.portal_chat_room", values)

    @http.route(['/my/chats/<int:channel_id>/messages'], type='jsonrpc', auth="user")
    def get_chat_messages(self, channel_id, last_id=0, **kw):
        user = request.env.user
        partner = user.partner_id
        
        # Security check using sudo
        channel = request.env['discuss.channel'].sudo().search([
            ('id', '=', channel_id),
            ('channel_member_ids.partner_id', '=', partner.id)
        ], limit=1)
        
        if not channel:
            return {'error': 'Unauthorized'}
            
        domain = [
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel_id),
            ('message_type', 'in', ['comment', 'notification', 'email'])
        ]
        if last_id:
            domain.append(('id', '>', int(last_id)))
            
        # Get latest 50 messages, oldest first for display using sudo
        messages = request.env['mail.message'].sudo().search(domain, limit=50, order='id DESC')
        
        res = []
        for msg in reversed(messages):
            is_self = msg.author_id.id == partner.id
            res.append({
                'id': msg.id,
                'body': html.unescape(msg.body) if msg.body else '',
                'author_name': msg.author_id.name or 'System',
                'author_id': msg.author_id.id,
                'is_self': is_self,
                'date': msg.date.strftime('%d %b %Y, %I:%M %p') if msg.date else '',
                'message_type': msg.message_type
            })
            
        return {'messages': res}
        
    @http.route(['/my/chats/api/channels'], type='jsonrpc', auth="user")
    def get_api_channels(self, **kw):
        user = request.env.user
        partner = user.partner_id
        
        channels = request.env['discuss.channel'].sudo().search([
            ('channel_member_ids.partner_id', '=', partner.id),
            ('channel_type', 'in', ['channel', 'group'])
        ])
        
        members = request.env['discuss.channel.member'].sudo().search([
            ('partner_id', '=', partner.id),
            ('channel_id', 'in', channels.ids)
        ])
        unread_counts = {m.channel_id.id: m.message_unread_counter for m in members}
        
        res = []
        for channel in channels:
            res.append({
                'id': channel.id,
                'name': channel.name,
                'member_count': channel.member_count,
                'unread_count': unread_counts.get(channel.id, 0)
            })
            
        return {'channels': res}
        
    @http.route(['/my/chats/api/mark_read'], type='jsonrpc', auth="user")
    def api_mark_read(self, channel_id, **kw):
        user = request.env.user
        partner = user.partner_id
        
        channel = request.env['discuss.channel'].sudo().search([
            ('id', '=', int(channel_id)),
            ('channel_member_ids.partner_id', '=', partner.id)
        ], limit=1)
        
        if not channel:
            return {'error': 'Unauthorized'}
            
        member = request.env['discuss.channel.member'].sudo().search([
            ('channel_id', '=', channel.id),
            ('partner_id', '=', partner.id)
        ], limit=1)
        
        last_message = request.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
        ], limit=1, order='id DESC')
        
        if member and last_message:
            member.sudo()._mark_as_read(last_message.id)
            
        return {'success': True}

    @http.route(['/my/chats/<int:channel_id>/send'], type='jsonrpc', auth="user")
    def send_chat_message(self, channel_id, body, **kw):
        user = request.env.user
        partner = user.partner_id
        
        if not body or not body.strip():
            return {'error': 'Empty message'}
            
        # Security check using sudo
        channel = request.env['discuss.channel'].sudo().search([
            ('id', '=', channel_id),
            ('channel_member_ids.partner_id', '=', partner.id)
        ], limit=1)
        
        if not channel:
            return {'error': 'Unauthorized'}
            
        # Handle mentions
        partner_ids = kw.get('partner_ids') or []
        if isinstance(partner_ids, str):
            partner_ids = [int(p) for p in partner_ids.split(',') if p.strip().isdigit()]
            
        mentioned_partners = request.env['res.partner'].sudo().browse(partner_ids)
        for partner in mentioned_partners:
            mention_str = f"@{partner.name}"
            if mention_str in body:
                html_mention = f'<a href="#" class="o_mail_redirect" data-oe-model="res.partner" data-oe-id="{partner.id}">@{partner.name}</a>'
                body = body.replace(mention_str, html_mention)
                
        message = channel.sudo().message_post(
            body=Markup(body) if isinstance(body, str) else body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=partner.id,
            partner_ids=mentioned_partners.ids,
        )
        
        # Mark the message as read for the sender so it doesn't show up in their unread count
        member = request.env['discuss.channel.member'].sudo().search([
            ('channel_id', '=', channel.id),
            ('partner_id', '=', partner.id)
        ], limit=1)
        if member:
            member.sudo()._mark_as_read(message.id)
        
        return {
            'success': True,
            'message': {
                'id': message.id,
                'body': message.body,
                'author_name': message.author_id.name,
                'author_id': message.author_id.id,
                'is_self': True,
                'date': message.date.strftime('%d %b %Y, %I:%M %p') if message.date else '',
                'message_type': message.message_type
            }
        }

    @http.route(['/my/chats/unread'], type='jsonrpc', auth="user")
    def get_unread_messages(self, last_id=0, **kw):
        user = request.env.user
        partner = user.partner_id
        
        # Get all channels where the user is a member using sudo
        channels = request.env['discuss.channel'].sudo().search([
            ('channel_member_ids.partner_id', '=', partner.id),
            ('channel_type', 'in', ['channel', 'group'])
        ])
        
        if not channels:
            return {'messages': [], 'max_id': 0, 'total_unread_chats': 0, 'unread_counts': {}}
            
        # Fetch unread counts for these channels
        members = request.env['discuss.channel.member'].sudo().search([
            ('partner_id', '=', partner.id),
            ('channel_id', 'in', channels.ids)
        ])
        unread_counts = {m.channel_id.id: m.message_unread_counter for m in members}
        total_unread_chats = sum(unread_counts.values())
            
        domain = [
            ('model', '=', 'discuss.channel'),
            ('res_id', 'in', channels.ids),
            ('message_type', 'in', ['comment', 'notification', 'email']),
            ('author_id', '!=', partner.id) # Don't notify about self messages
        ]
        
        if last_id:
            domain.append(('id', '>', int(last_id)))
        else:
            # If no last_id is provided, just return the max id to initialize polling without triggering a storm
            max_msg = request.env['mail.message'].sudo().search(domain, limit=1, order='id DESC')
            return {
                'max_id': max_msg.id if max_msg else 0, 
                'messages': [],
                'total_unread_chats': total_unread_chats,
                'unread_counts': unread_counts
            }
            
        messages = request.env['mail.message'].sudo().search(domain, limit=10, order='id ASC')
        
        res = []
        max_id = int(last_id)
        for msg in messages:
            if msg.id > max_id:
                max_id = msg.id
                
            # Find the channel name
            channel = channels.filtered(lambda c: c.id == msg.res_id)
            channel_name = channel.name if channel else 'Project'
            
            res.append({
                'id': msg.id,
                'channel_id': msg.res_id,
                'channel_name': channel_name,
                'author_name': msg.author_id.name or 'System',
                'body': html.unescape(msg.body) if msg.body else '',
            })
            
        return {
            'messages': res, 
            'max_id': max_id,
            'total_unread_chats': total_unread_chats,
            'unread_counts': unread_counts
        }
