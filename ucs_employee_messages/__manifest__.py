# -*- coding: utf-8 -*-
{
    'name': 'UCS Employee Messages',
    'version': '19.0.1.0.0',
    'category': 'Discuss',
    'summary': 'Portal Chat, Floating Notification Widget & Mentions for Employees',
    'description': """
    Provides a global floating chat widget, real-time push/sound notifications,
    project discuss-channel auto-sync, and @mention autocomplete for portal users.
    All discuss/message functionality extracted from ucs_portal_self_service.
    """,
    'author': 'Your Company',
    'depends': [
        'portal',
        'mail',
        'project',
    ],
    'data': [
        'security/discuss_security.xml',
        'views/discuss_templates.xml',
        'views/floating_chat_templates.xml',
        'views/project_project_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'ucs_employee_messages/static/src/css/portal_chat.css',
            'ucs_employee_messages/static/src/css/portal_mentions.css',
            'ucs_employee_messages/static/src/css/portal_floating_chat.css',
            'ucs_employee_messages/static/src/js/portal_chat.js',
            'ucs_employee_messages/static/src/js/portal_mentions.js',
            'ucs_employee_messages/static/src/js/portal_floating_chat.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
