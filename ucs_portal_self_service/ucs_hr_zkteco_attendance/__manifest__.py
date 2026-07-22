{
    "name": "ZKTeco Attendance Integration",
    "version": "19.0.1.0.0",
    "author": "OpenAI",
    "website": "",
    "category": "Human Resources",
    "summary": "Integrate ZKTeco biometric devices with Odoo HR Attendance",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_attendance",
    ],
    "external_dependencies": {
        "python": [
            "pyzk",
            "pytz",
        ]
    },
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/menu.xml",
        "views/zk_device_views.xml",
        "views/hr_employee_views.xml",
        "views/attendance_log_views.xml",
        "views/sync_history_views.xml",
        "wizard/sync_wizard_views.xml",
    ],
    "application": True,
    "installable": True,
}