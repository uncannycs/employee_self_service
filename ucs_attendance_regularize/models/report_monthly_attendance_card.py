# -*- coding: utf-8 -*-
from odoo import models, api
from datetime import date

class ReportMonthlyAttendanceCard(models.AbstractModel):
    _name = 'report.ucs_attendance_regularize.report_monthly_attendance_card'
    _description = 'Monthly Attendance Card Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        if 'daily_records' in data and 'summary' in data:
            doc = data.get('doc') or (self.env['hr.employee'].browse(docids[0]) if docids else False)
            return {
                'doc_ids': docids,
                'doc_model': 'hr.employee',
                'doc': doc,
                'docs': self.env['hr.employee'].browse(docids),
                'daily_records': data.get('daily_records', []),
                'summary': data.get('summary', {}),
            }

        employee = self.env['hr.employee'].browse(docids[0]) if docids else False
        today = date.today()
        from ..controllers.main import _compute_monthly_card
        daily_records, summary = _compute_monthly_card(self.env, employee, today.year, today.month) if employee else ([], {})

        return {
            'doc_ids': docids,
            'doc_model': 'hr.employee',
            'doc': employee,
            'docs': self.env['hr.employee'].browse(docids),
            'daily_records': daily_records,
            'summary': summary,
        }
