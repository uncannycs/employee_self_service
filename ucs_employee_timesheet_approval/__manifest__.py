# -*- coding: utf-8 -*-
{
    'name': 'Employee Timesheet Approval',
    'version': '1.0',
    'category': 'Human Resources/Timesheets',
    'summary': 'Portal approval workflow for employee timesheets',
    'description': """
        Adds an approval workflow (Draft -> Submitted -> Approved/Refused) 
        to base timesheet lines and provides a manager approval interface in the portal.
    """,
    'author': 'UCS',
    'depends': ['hr_timesheet', 'account', 'ucs_portal_self_service'],
    'data': [
        'security/security_groups.xml',
        'views/approvals_templates.xml',
        'views/timesheets_templates.xml',
        'views/account_analytic_line_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
