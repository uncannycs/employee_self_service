from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    biometric_user_id = fields.Char(
        string="Biometric User ID",
        copy=False,
        index=True,
        help="User ID stored in the ZKTeco device."
    )

    biometric_device_id = fields.Many2one(
        "zk.device",
        string="Biometric Device",
        copy=False
    )

    biometric_active = fields.Boolean(
        string="Enable Biometric",
        default=True
    )

    biometric_last_sync = fields.Datetime(
        string="Last Biometric Sync",
        readonly=True,
        copy=False
    )

    _sql_constraints = [
        (
            "biometric_user_unique",
            "unique(biometric_user_id)",
            "Biometric User ID must be unique."
        )
    ]

    @api.model
    def get_employee_by_biometric_id(self, biometric_id):
        """
        Returns employee mapped with biometric id.
        """
        return self.search([
            ("biometric_user_id", "=", str(biometric_id)),
            ("biometric_active", "=", True)
        ], limit=1)

    def assign_biometric_user(self, biometric_id, device):
        """
        Assign biometric information to employee.
        """
        self.ensure_one()

        self.write({
            "biometric_user_id": str(biometric_id),
            "biometric_device_id": device.id,
        })

    def mark_biometric_synced(self):
        """
        Update last sync timestamp.
        """
        self.ensure_one()

        self.biometric_last_sync = fields.Datetime.now()

    def clear_biometric(self):
        """
        Remove biometric mapping.
        """
        self.ensure_one()

        self.write({
            "biometric_user_id": False,
            "biometric_device_id": False,
            "biometric_last_sync": False,
        })