# -*- coding: utf-8 -*-
{
    'name': 'UCS Timesheet Export',
    'summary': 'Export Timesheet Records to Excel XLSX format from Employee Self Service Portal',
    'description': """
        This module provides Excel (.xlsx) report export functionality for Employee Timesheets 
        from the Employee Self Service Portal (/my/timesheets).
    """,
    'author': 'UncannyCS',
    'website': 'https://uncannycs.com',
    'category': 'Human Resources/Timesheets',
    'version': '19.0.1.0.0',
    'depends': [
        'hr_timesheet',
        'account',
        'portal',
        'ucs_portal_self_service',
        'ucs_employee_timesheet_approval',
    ],
    'data': [
        'views/timesheets_templates.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
