from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ModelSignature(models.AbstractModel):
    _name = 'model.signature.purchase'
    _description = 'Model Signature'

    checked_signature = fields.Binary('Checker Signature')
    approved_signature = fields.Binary('Approver Signature')


class PurchaseRequest(models.Model):
    _name = 'purchase.request'
    _description = 'Purchase Request'
    _inherit = ['mail.thread', 'mail.activity.mixin','model.signature.purchase']
    _check_company_auto = True

    name = fields.Char(string='Name', required=True, copy=False, default=lambda self: _('New'), readonly=True)
    store_request_id = fields.Many2one('store.request', string='Store Request', required=True)
    request_lines = fields.One2many('purchase.request.line', 'request_id', string='Request Lines')
    purchase_performa_count = fields.Integer(string='Purchase Performa Count', compute='_compute_purchase_performa_count')
    validated_manager_id = fields.Many2one('res.users', string='Validated by', tracking=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse',readonly=True)
    location_id = fields.Many2one('stock.location', string='Source Location', related='warehouse_id.lot_stock_id',readonly=True)
    requester_id = fields.Many2one('res.users', string='Requested by', default=lambda self: self.env.user,readonly=True)
    destination_location_id = fields.Many2one('stock.location', string='Destination Location',readonly=True)
    reason = fields.Char(string="Reason",readonly=True)
    ref = fields.Char(string="Reference",readonly=True)
    approved_manager_id = fields.Many2one('res.users', string='Approved by')
    checked_manager_id = fields.Many2one('res.users', string='Checked by')
    remark = fields.Text(string="Remark")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    checked_date = fields.Date(string='Checked Date', readonly=True)
    approved_date = fields.Date(string='Approved Date', readonly=True)
    start_dat = fields.Date(string="start_date",readonly=True)

    checkbox_routine = fields.Boolean('Routine',default=True)
    checkbox_critical = fields.Boolean('Critical', default=False)
    checkbox_urgent = fields.Boolean('Urgent', default=False)
   # company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    date_start = fields.Date(string='Start Date',default=fields.Date.context_today,help="Start date for the request")
    requested_by = fields.Many2one('res.users',string='Requested By',default=lambda self: self.env.user, tracking=True)
    currency_id = fields.Many2one('res.currency',string='Currency',required=True,default=lambda self: self.env.company.currency_id,help="The currency used for all purchase requests" )
    estimated_cost = fields.Monetary(string='Estimated Cost',currency_field='currency_id',help="Manual estimation of product cost for this request")
    assigned_to = fields.Many2one('res.users', string='Assigned To',tracking=True,help="Person responsible for handling this request")
    picking_type_id = fields.Many2one('stock.picking.type', string='Picking Type')

    def _compute_purchase_performa_count(self):
        for rec in self:
            rec.purchase_performa_count = self.env['purchase.performa'].search_count([('request_id', '=', rec.name)])

    def purchase_performa_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Performa',
            'res_model': 'purchase.performa',
            'domain': [('request_id', '=', self.name)],
            'view_mode': 'tree,form',
            'target': 'current'
        }

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submit'),
        ('approve', 'Approve'),
        ('validate', 'Validate'),
        ('reject', 'Reject'),
    ], default="draft")

    def action_submit(self):
        self.ensure_one()
        self.state = 'submit'

    def action_approve(self):
        self.ensure_one()
        self.checked_manager_id = self.env.user or False
        self.checked_date = fields.date.today()
        self.state = 'approve'

    def action_validate(self):
        self.ensure_one()
        self.approved_manager_id = self.env.user or False
        self.approved_date = fields.date.today()
        self.state = 'validate'

    def action_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_reject(self):
        self.ensure_one()
        self.state = 'reject'


    @api.model
    def create(self, vals):
        if vals.get('name', ('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('purchase.request') or _('New')
            res = super(PurchaseRequest, self).create(vals)
            return res

    def create_purchase_performa(self):
        # Check if a purchase performa already exists for this purchase request
        existing_performa = self.env['purchase.performa'].search([('purchase_request_id', '=', self.id)], limit=1)
        if existing_performa:
            raise UserError(_('A purchase performa has already been created for this request.'))

        performa_vals = {
            'request_id': self.name,
            'store_request_id': self.store_request_id.id,
            'purchase_request_id': self.id,
            'performa_line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'product_qty': line.quantity,
                'product_uom': line.product_id.uom_id.id,
            }) for line in self.request_lines]
        }
        self.env['purchase.performa'].sudo().create(performa_vals)


    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_('You can not delete record that is not draft state.'))
            else:
                return super(PurchaseRequest, self).unlink()


class PurchaseRequestLine(models.Model):
    _name = 'purchase.request.line'
    _description = 'Purchase Request Line'
    _check_company_auto = True

    request_id = fields.Many2one('purchase.request', string='Purchase Request')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float(string='Quantity', required=True)
    uom_id = fields.Many2one('uom.uom', related="product_id.uom_po_id")
    remark = fields.Char(string="Remark")
    item_code = fields.Char(string='Item Code',readonly=True)
    sequence_number = fields.Integer(string='SN/NO', default=1, readonly=True)
    company_id = fields.Many2one('res.company',string='Company',related='request_id.company_id',  # Assuming request_id has company_id
        store=True,
        readonly=True
    )
    on_hand_qty = fields.Integer(string='On Hand qty', readonly=True, compute='_compute_on_hand_balance')
    product_uom_id = fields.Many2one('uom.uom', string="Unit of Measure")
    @api.depends('product_id')
    def _compute_on_hand_balance(self):
        for rec in self:
            if rec.product_id:
                stock_quants = self.env['stock.quant'].search([
                    ('product_id', '=', rec.product_id.id),
                ])
                sumed = 0
                for val in stock_quants:
                    sumed = val.quantity
                rec.on_hand_qty = sumed
            else:
                rec.on_hand_qty = 0


