from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Adding partner_id field to associate a product with a partner (customer or supplier)
    vendor_id = fields.Many2one('res.partner', string='Partner', help="Vendor that provided last performa or is associated with this product.", readonly=True)
    vendor_price_unit = fields.Float(string='Unit Price', readonly=True)
