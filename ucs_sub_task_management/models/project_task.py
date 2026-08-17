# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class ProjectTask(models.Model):
    _inherit = 'project.task'

    developer_allocated_hours = fields.Float(
        string="Developer Allocated Hours",
    )
    client_allocated_hours = fields.Float(
        string="Client Allocated Hours",
    )

    subtask_count = fields.Integer(
        string="Sub-tasks Count",
        compute="_compute_custom_subtask_count",
        store=True,
    )
    subtask_allocated_hours = fields.Float(
        string="Sub-tasks Allocated Hours",
        compute="_compute_subtask_hours",
        store=True,
    )
    subtask_effective_hours = fields.Float(
        string="Sub-tasks Logged Hours",
        compute="_compute_subtask_hours",
        store=True,
    )

    @api.depends('child_ids')
    def _compute_custom_subtask_count(self):
        for task in self:
            task.subtask_count = len(task.child_ids)

    @api.depends('child_ids', 'child_ids.allocated_hours', 'child_ids.developer_allocated_hours', 'child_ids.effective_hours', 'child_ids.timesheet_ids.unit_amount')
    def _compute_subtask_hours(self):
        for task in self:
            tot_alloc = 0.0
            tot_eff = 0.0
            for child in task.child_ids:
                tot_alloc += child.developer_allocated_hours or child.allocated_hours or 0.0
                tot_eff += child.effective_hours or sum(child.timesheet_ids.mapped('unit_amount')) or 0.0
            task.subtask_allocated_hours = tot_alloc
            task.subtask_effective_hours = tot_eff

    def action_open_subtasks(self):
        self.ensure_one()
        return {
            'name': _('Sub-tasks'),
            'view_mode': 'list,kanban,form',
            'res_model': 'project.task',
            'type': 'ir.actions.act_window',
            'domain': [('parent_id', '=', self.id)],
            'context': {
                'default_parent_id': self.id,
                'default_project_id': self.project_id.id,
            }
        }
