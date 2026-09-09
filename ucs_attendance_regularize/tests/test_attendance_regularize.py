# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError
from datetime import datetime, date, timedelta
from ..controllers.main import _compute_monthly_card

@tagged('post_install', '-at_install', 'ucs_attendance')
class TestAttendanceRegularize(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        
        # Create test company & employee
        cls.test_company = cls.env['res.company'].create({'name': 'Test ESS Company'})
        cls.test_employee = cls.env['hr.employee'].create({
            'name': 'John ESS Tester',
            'company_id': cls.test_company.id,
            'regularize_request_assign': 3,
            'regularize_req_used': 0,
        })
        
        # Create attendances for current month
        today = date.today()
        ci_dt = datetime.combine(today, datetime.min.time()) + timedelta(hours=9)
        co_dt = ci_dt + timedelta(hours=8)
        
        cls.attendance = cls.env['hr.attendance'].create({
            'employee_id': cls.test_employee.id,
            'check_in': ci_dt,
            'check_out': co_dt,
        })

    def test_01_quota_initial_and_deduction(self):
        """ Test initial regularization quota and deduction upon submission. """
        emp = self.test_employee
        self.assertEqual(emp.regularize_request_assign, 3)
        self.assertEqual(emp.regularize_req_used, 0)
        
        # Simulate regularize request creation
        reg = self.env['attendance.regularize'].create({
            'employee_id': emp.id,
            'attendance_id': self.attendance.id,
            'regularize_type': 'check_in',
            'reason': 'Forgot to punch check-in',
            'state': 'submit',
        })
        emp.write({'regularize_req_used': emp.regularize_req_used + 1})
        
        self.assertEqual(emp.regularize_req_used, 1)
        remaining = emp.regularize_request_assign - emp.regularize_req_used
        self.assertEqual(remaining, 2)

    def test_02_monthly_attendance_card_calculation(self):
        """ Test daily records and summary calculation for Monthly Attendance Card. """
        today = date.today()
        daily_records, summary = _compute_monthly_card(
            self.env, self.test_employee, today.year, today.month
        )
        
        self.assertTrue(len(daily_records) >= 28)
        self.assertEqual(summary['month_name'], today.strftime('%B %Y'))
        self.assertTrue(summary['working_days'] > 0)
        self.assertTrue(summary['tot_worked'] >= 8.0)

    def test_03_quota_reset_cron(self):
        """ Test monthly cron job for resetting employee regularization quotas. """
        self.test_employee.write({'regularize_req_used': 3})
        self.env['hr.employee']._cron_reset_regularize_requests()
        self.assertEqual(self.test_employee.regularize_req_used, 0)
