# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class ProjectProject(models.Model):
    _inherit = 'project.project'

    def message_subscribe(self, partner_ids=None, subtype_ids=None):
        old_partners = {project.id: set(project.message_partner_ids.ids) for project in self} if partner_ids else {}
        res = super().message_subscribe(partner_ids=partner_ids, subtype_ids=subtype_ids)
        if partner_ids:
            for project in self:
                prev_pids = old_partners.get(project.id, set())
                added_pids = [pid for pid in partner_ids if pid not in prev_pids]
                if added_pids:
                    added_partners = self.env['res.partner'].sudo().browse(added_pids)
                    project._send_project_follower_added_email(added_partners)
        return res

    def _send_project_follower_added_email(self, added_partners):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        sender_name = self.env.user.name or 'System'
        company_email = self.env.company.email or self.env.user.email_formatted or 'noreply@company.com'
        for project in self:
            project_url = f"{base_url}/my/projects/{project.id}"
            for partner in added_partners:
                if partner.id == self.env.user.partner_id.id or not partner.email:
                    continue
                
                subject = f"[Follower Added] You are now following project: {project.name}"
                body_html = f"""
                <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
                    <div style="background-color: #00838f; padding: 15px 20px; border-radius: 8px 8px 0 0;">
                        <h3 style="color: #ffffff; margin: 0;">Project Follower Notification</h3>
                    </div>
                    <div style="border: 1px solid #e2e8f0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; background: #ffffff;">
                        <p>Hello <strong>{partner.name}</strong>,</p>
                        <p>You have been added as a follower to project <strong>{project.name}</strong> by <strong>{sender_name}</strong>.</p>
                        
                        <p style="margin-top: 20px;">
                            <a href="{project_url}" style="background-color: #00838f; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
                                Open Project Page
                            </a>
                        </p>
                        <br/>
                        <p style="font-size: 12px; color: #777;">This is an automated notification from Employee Self Service.</p>
                    </div>
                </div>
                """
                try:
                    mail = self.env['mail.mail'].sudo().create({
                        'subject': subject,
                        'email_from': company_email,
                        'email_to': partner.email,
                        'body_html': body_html,
                        'state': 'outgoing',
                    })
                    mail.send()
                except Exception as e:
                    _logger.error("Error sending project follower email to %s: %s", partner.email, str(e))
