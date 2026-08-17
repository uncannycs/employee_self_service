# -*- coding: utf-8 -*-
{
    'name': 'Task Sub-task Management',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Sub-task creation and management in Backend and Employee Portal',
    'description': """
    Extends Odoo 19 Project Task with native Sub-task management.
    - Adds Sub-tasks tab, smart button, and hours metrics in Backend project.task form
    - Adds Sub-tasks section, modal, and creation route in Portal Task Details View
    """,
    'author': 'UncannyCS',
    'depends': [
        'project',
        'hr_timesheet',
        'ucs_portal_self_service',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/project_task_views.xml',
        'views/portal_sub_task_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
