# -*- coding: utf-8 -*-
{
    'name': 'Employee Self Service Leave Management',
    'version': '1.0',
    'category': 'Human Resources',
    'summary': 'Leave Management for Employee Self Service Portal',
    'description': """
    This module provides leave management and approvals functionality for the employee self service portal.
    """,
    'author': 'UCS',
    'depends': ['ucs_portal_self_service', 'hr_holidays'],
    'data': [
        'security/security.xml',
        'views/portal_templates.xml',
        'views/leaves_templates.xml',
        'views/approvals_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
