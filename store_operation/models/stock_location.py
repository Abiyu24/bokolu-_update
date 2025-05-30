from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockLocation(models.Model):
    _inherit = 'stock.location'

    def get_warehouse(self):
        warehouse = self.env['stock.warehouse'].search([
            ('lot_stock_id', '=', self.id)], limit=1)
        return warehouse



class WarehouseTag(models.Model):
    _name = 'warehouse.tag'
    _description = 'Warehouse Tag'
    inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Tag Name', required=True)
    description = fields.Text(string='Description')


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'
    tag_ids = fields.Many2one('warehouse.tag', string='Tags')