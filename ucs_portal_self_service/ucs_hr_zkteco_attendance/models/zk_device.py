from werkzeug import useragents
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from zk import ZK
except ImportError:
    ZK = None


class ZkDevice(models.Model):
    _name = "zk.device"
    _description = "ZKTeco Device"
    _rec_name = "name"

    name = fields.Char(required=True)

    ip_address = fields.Char(
        string="IP Address",
        required=True
    )

    port = fields.Integer(
        default=4370,
        required=True
    )

    password = fields.Char()

    timeout = fields.Integer(
        default=10
    )

    enabled = fields.Boolean(
        default=True
    )

    last_sync = fields.Datetime(
        readonly=True
    )

    state = fields.Selection(
        [
            ('draft', 'Not Tested'),
            ('connected', 'Connected'),
            ('failed', 'Connection Failed')
        ],
        default='draft',
        readonly=True
    )

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True
    )

    def _get_connection(self):
        """
        Returns connected ZK instance.
        Caller is responsible for disconnect().
        """
        self.ensure_one()

        if ZK is None:
            raise UserError(
                _("Please install pyzk library.\n\npip install pyzk")
            )

        zk = ZK(
            self.ip_address,
            port=self.port,
            timeout=self.timeout,
            password=int(self.password or 0),
            force_udp=False,
            ommit_ping=False,
        )

        return zk.connect()

    def action_test_connection(self):
        """
        Test device connectivity.
        """
        self.ensure_one()

        try:
            conn = self._get_connection()

            device_name = conn.get_device_name()
            firmware = conn.get_firmware_version()

            conn.disconnect()

            self.state = "connected"

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Success"),
                    "message": _(
                        "Connected successfully.\n"
                        "Device: %s\n"
                        "Firmware: %s"
                    ) % (device_name, firmware),
                    "type": "success",
                    "sticky": False,
                }
            }

        except Exception as e:
            self.state = "failed"

            _logger.exception(e)

            raise UserError(str(e))

    def action_download_users(self):
        """
        Download users from biometric device.
        """
        self.ensure_one()

        conn = None

        try:
            conn = self._get_connection()

            users = conn.get_users()

            total = 0

            employee_model = self.env["hr.employee"]

            for user in users:

                employee = employee_model.search([
                    ("biometric_user_id", "=", str(user.user_id))
                ], limit=1)

                if employee:
                    employee.write({
                        "name": user.name,
                        "biometric_device_id": self.id,
                    })
                else:
                    employee_model.create({
                        "name": user.name,
                        "biometric_user_id": str(user.user_id),
                        "biometric_device_id": self.id,
                    })

                total += 1

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Completed"),
                    "message": _("%s users downloaded.") % total,
                    "type": "success",
                }
            }

        except Exception as e:
            _logger.exception(e)
            raise UserError(str(e))

        finally:
            if conn:
                conn.disconnect()

    def action_download_attendance(self):
        """
        Reads attendance logs from device.

        Actual HR attendance creation
        will be implemented in Part 5.
        """
        self.ensure_one()

        conn = None

        try:

            conn = self._get_connection()

            attendances = conn.get_attendance()

            total = len(attendances)

            self.last_sync = fields.Datetime.now()

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Completed"),
                    "message": _("%s attendance logs downloaded.") % total,
                    "type": "success",
                }
            }

        except Exception as e:

            _logger.exception(e)

            raise UserError(str(e))

        finally:

            if conn:
                conn.disconnect()