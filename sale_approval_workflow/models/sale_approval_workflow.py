from odoo import models, fields

class SaleApprovalWorkflow(models.Model):
    _name = 'sale.approval.workflow'
    _description = 'Sale Approval Workflow'

    name = fields.Char(string='Name')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('marketing_approval', 'Marketing Approval'),
        ('technical_approval', 'Technical Approval'),
        ('done', 'Done'),
    ], string='Status', default='draft')