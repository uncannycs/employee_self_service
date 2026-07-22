# -*- coding: utf-8 -*-
{
    'name': 'Employee Self Service Portal',
    'version': '19.0.1.0.8',
    'category': 'Human Resources',
    'summary': 'Employee Self Service Portal for Odoo 19',
    'description': """
    Custom Employee Self Service Dashboard overriding default Odoo portal.
    """,
    'author': 'Your Company',
    'depends': [
        'portal', 'hr_attendance', 'hr_expense', 'hr_holidays', 'project',
        'hr_timesheet', 'om_hr_payroll',
        'ucs_employee_messages',  # discuss/chat/notification module
    ],
    'data': [
        'security/security.xml',
        'security/ir_rule.xml',
        'security/ir.model.access.csv',
        # discuss_security.xml → moved to ucs_employee_messages
        'views/portal_templates.xml',
        'views/approvals_templates.xml',
        'views/projects_templates.xml',
        'views/timesheets_templates.xml',
        'views/profile_templates.xml',
        'views/directory_templates.xml',
        'views/announcement_views.xml',
        'views/project_task_views.xml',
        # project_project_views.xml → moved to ucs_employee_messages
        # discuss_templates.xml → moved to ucs_employee_messages
        # floating_chat_templates.xml → moved to ucs_employee_messages
    ],
    'assets': {
        'web.assets_frontend': [
            'ucs_portal_self_service/static/src/js/attendance_widget.js',
            'ucs_portal_self_service/static/src/css/style.css',
            # portal_chat.css, portal_mentions.css, portal_floating_chat.css → ucs_employee_messages
            # portal_chat.js, portal_floating_chat.js, portal_mentions.js → ucs_employee_messages
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
