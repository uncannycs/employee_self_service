# -*- coding: utf-8 -*-
import logging
import re
from odoo import models, fields, api, _
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

class ProjectTask(models.Model):
    """ Inherit project.task to add custom portal fields (client_deadline, client_allocated_hours) and notification handlers. """
    _inherit = 'project.task'

    client_deadline = fields.Date(string="Client Deadline", tracking=True)
    client_allocated_hours = fields.Float(string="Client Allocated Hours", tracking=True)
    description_plain = fields.Char(compute='_compute_description_plain')

    @api.depends('description')
    def _compute_description_plain(self):
        """ Compute plain text version of HTML description for preview rendering. """
        for task in self:
            if task.description:
                task.description_plain = html2plaintext(task.description).strip()
            else:
                task.description_plain = ''

    @api.model_create_multi
    def create(self, vals_list):
        """ Override create to auto-notify assigned users and subscribe assigned partners. """
        tasks = super().create(vals_list)
        for task in tasks:
            if task.user_ids:
                task._send_task_assignment_email(task.user_ids)
                task.message_subscribe(partner_ids=task.user_ids.mapped('partner_id').ids)
        return tasks

    def write(self, vals):
        """ Override write to trigger assignment email and follower subscription when assignees change. """
        old_user_ids = {task.id: set(task.user_ids.ids) for task in self} if 'user_ids' in vals else {}
        res = super().write(vals)
        if 'user_ids' in vals:
            for task in self:
                prev_uids = old_user_ids.get(task.id, set())
                new_users = task.user_ids.filtered(lambda u: u.id not in prev_uids)
                if new_users:
                    task._send_task_assignment_email(new_users)
                    task.message_subscribe(partner_ids=new_users.mapped('partner_id').ids)
        return res

    def message_subscribe(self, partner_ids=None, subtype_ids=None):
        """ Override message_subscribe to notify newly added followers via email. """
        old_partners = {task.id: set(task.sudo().message_partner_ids.ids) for task in self} if partner_ids else {}
        res = super().message_subscribe(partner_ids=partner_ids, subtype_ids=subtype_ids)
        if partner_ids:
            for task in self:
                prev_pids = old_partners.get(task.id, set())
                added_pids = [pid for pid in partner_ids if pid not in prev_pids]
                if added_pids:
                    added_partners = self.env['res.partner'].sudo().browse(added_pids)
                    task._send_follower_added_email(added_partners)
        return res

    def message_post(self, body='', subject=None, message_type='notification', subtype_xmlid=None, partner_ids=None, **kwargs):
        msg = super(ProjectTask, self.sudo()).message_post(body=body, subject=subject, message_type=message_type, subtype_xmlid=subtype_xmlid, partner_ids=partner_ids, **kwargs)
        try:
            self._notify_chatter_and_mentions(msg, body, partner_ids)
        except Exception as e:
            _logger.error("Failed to send chatter/mention emails: %s", str(e))
        return msg

    def _send_task_assignment_email(self, assigned_users):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        sender_name = self.env.user.name or 'System'
        company_email = self.env.company.email or self.env.user.email_formatted or 'noreply@company.com'
        for task in self:
            task_url = f"{base_url}/my/tasks/{task.id}"
            for user in assigned_users:
                recipient_email = user.email or user.partner_id.email
                if not recipient_email:
                    continue
                
                subject = f"[Task Assigned] You have been assigned to task: {task.name}"
                body_html = f"""
                <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
                    <div style="background-color: #4a148c; padding: 15px 20px; border-radius: 8px 8px 0 0;">
                        <h3 style="color: #ffffff; margin: 0;">Task Assignment Notification</h3>
                    </div>
                    <div style="border: 1px solid #e2e8f0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; background: #ffffff;">
                        <p>Hello <strong>{user.name}</strong>,</p>
                        <p>You have been assigned to the following task by <strong>{sender_name}</strong>:</p>
                        
                        <div style="background: #f8fafc; border-left: 4px solid #4a148c; padding: 12px 16px; margin: 15px 0; border-radius: 4px;">
                            <p style="margin: 0 0 8px 0;"><strong>Task:</strong> {task.name}</p>
                            <p style="margin: 0 0 8px 0;"><strong>Project:</strong> {task.project_id.name if task.project_id else '-'}</p>
                            <p style="margin: 0;"><strong>Deadline:</strong> {task.date_deadline or 'None'}</p>
                        </div>

                        <p style="margin-top: 20px;">
                            <a href="{task_url}" style="background-color: #4a148c; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
                                View Task in Portal
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
                        'email_to': recipient_email,
                        'body_html': body_html,
                        'state': 'outgoing',
                    })
                    mail.send()
                except Exception as e:
                    _logger.error("Error sending assignment email to %s: %s", recipient_email, str(e))

    def _send_follower_added_email(self, added_partners):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        sender_name = self.env.user.name or 'System'
        company_email = self.env.company.email or self.env.user.email_formatted or 'noreply@company.com'
        for task in self:
            task_url = f"{base_url}/my/tasks/{task.id}"
            for partner in added_partners:
                if partner.id == self.env.user.partner_id.id or not partner.email:
                    continue
                
                subject = f"[Follower Added] You are now following task: {task.name}"
                body_html = f"""
                <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
                    <div style="background-color: #00838f; padding: 15px 20px; border-radius: 8px 8px 0 0;">
                        <h3 style="color: #ffffff; margin: 0;">Follower Notification</h3>
                    </div>
                    <div style="border: 1px solid #e2e8f0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; background: #ffffff;">
                        <p>Hello <strong>{partner.name}</strong>,</p>
                        <p>You have been added as a follower to task <strong>{task.name}</strong> by <strong>{sender_name}</strong>.</p>
                        
                        <p style="margin-top: 20px;">
                            <a href="{task_url}" style="background-color: #00838f; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
                                Open Task Details
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
                    _logger.error("Error sending follower email to %s: %s", partner.email, str(e))

    def _notify_chatter_and_mentions(self, msg, body, explicit_partner_ids=None):
        if not body or not self:
            return
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        sender_partner = self.env.user.partner_id
        company_email = self.env.company.email or self.env.user.email_formatted or 'noreply@company.com'

        mentioned_partners = self.env['res.partner']
        if explicit_partner_ids:
            mentioned_partners |= self.env['res.partner'].sudo().browse(explicit_partner_ids)
        
        partner_ids_in_html = re.findall(r'data-oe-id=["\'](\d+)["\']', body)
        if partner_ids_in_html:
            mentioned_partners |= self.env['res.partner'].sudo().browse([int(pid) for pid in partner_ids_in_html])
        
        plain_body = html2plaintext(body)
        at_names = re.findall(r'@([A-Za-z0-9._\s]+)', plain_body)
        for name in at_names:
            name_clean = name.strip()
            if name_clean:
                found_partner = self.env['res.partner'].sudo().search([('name', 'ilike', name_clean)], limit=1)
                if found_partner:
                    mentioned_partners |= found_partner

        for task in self:
            task_url = f"{base_url}/my/tasks/{task.id}"
            
            for m_partner in mentioned_partners:
                if m_partner.id == sender_partner.id or not m_partner.email:
                    continue
                
                task.sudo().message_subscribe(partner_ids=[m_partner.id])
                
                subject = f"[You were mentioned] {sender_partner.name} mentioned you on Task: {task.name}"
                body_html = f"""
                <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
                    <div style="background-color: #e65100; padding: 15px 20px; border-radius: 8px 8px 0 0;">
                        <h3 style="color: #ffffff; margin: 0;">You Were Mentioned</h3>
                    </div>
                    <div style="border: 1px solid #e2e8f0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; background: #ffffff;">
                        <p>Hello <strong>{m_partner.name}</strong>,</p>
                        <p><strong>{sender_partner.name}</strong> mentioned you in a comment on task <strong>{task.name}</strong>:</p>
                        
                        <div style="background: #fff8e1; border-left: 4px solid #ff8f00; padding: 12px 16px; margin: 15px 0; border-radius: 4px;">
                            {body}
                        </div>

                        <p style="margin-top: 20px;">
                            <a href="{task_url}" style="background-color: #e65100; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
                                Reply in Portal
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
                        'email_to': m_partner.email,
                        'body_html': body_html,
                        'state': 'outgoing',
                    })
                    mail.send()
                except Exception as e:
                    _logger.error("Error sending mention email to %s: %s", m_partner.email, str(e))

            other_followers = task.message_partner_ids.filtered(
                lambda p: p.id != sender_partner.id and p.id not in mentioned_partners.ids and p.email
            )
            for f_partner in other_followers:
                subject = f"[New Message] Update on Task: {task.name}"
                body_html = f"""
                <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
                    <div style="background-color: #4a148c; padding: 15px 20px; border-radius: 8px 8px 0 0;">
                        <h3 style="color: #ffffff; margin: 0;">Task Update Notification</h3>
                    </div>
                    <div style="border: 1px solid #e2e8f0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; background: #ffffff;">
                        <p>Hello <strong>{f_partner.name}</strong>,</p>
                        <p><strong>{sender_partner.name}</strong> posted a message on task <strong>{task.name}</strong>:</p>
                        
                        <div style="background: #f8fafc; border-left: 4px solid #4a148c; padding: 12px 16px; margin: 15px 0; border-radius: 4px;">
                            {body}
                        </div>

                        <p style="margin-top: 20px;">
                            <a href="{task_url}" style="background-color: #4a148c; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
                                View & Reply in Portal
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
                        'email_to': f_partner.email,
                        'body_html': body_html,
                        'state': 'outgoing',
                    })
                    mail.send()
                except Exception as e:
                    _logger.error("Error sending chatter email to %s: %s", f_partner.email, str(e))
