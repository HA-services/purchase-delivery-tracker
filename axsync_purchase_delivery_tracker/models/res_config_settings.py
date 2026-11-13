# -*- coding: utf-8 -*-
# Part of AXSync. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    axsync_alert_upcoming = fields.Boolean(
        'Upcoming Delivery Alerts', config_parameter='axsync_purchase_delivery_tracker.alert_upcoming', default=True)
    axsync_alert_overdue = fields.Boolean(
        'Overdue Delivery Alerts', config_parameter='axsync_purchase_delivery_tracker.alert_overdue', default=True)
    axsync_alert_partial = fields.Boolean(
        'Partial Receipt Alerts', config_parameter='axsync_purchase_delivery_tracker.alert_partial', default=True)
    axsync_alert_days = fields.Integer(
        'Upcoming Window (Days)', config_parameter='axsync_purchase_delivery_tracker.alert_days', default=3)

    def action_axsync_send_alerts(self):
        self.execute()
        created = self.env['axsync.delivery.alert'].cron_send_alerts()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': 'Delivery alerts', 'type': 'success', 'sticky': False,
                       'message': '%s new alert(s) sent.' % created},
        }
