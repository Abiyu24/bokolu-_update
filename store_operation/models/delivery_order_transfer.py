from odoo import models, fields, api, _
from odoo.exceptions import UserError


class DeliveryOrderTransfer(models.Model):
    _name = 'delivery.order.transfer'
    _description = 'Delivery Order Transfer'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(required=True, copy=False, default=lambda self: _('New'))
    # name = fields.Char(required=True, copy=False, default=lambda self: _('New' ),compute="_compute_name_readonly")
    request_id = fields.Many2one('res.partner', string='Received From', required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('checked', 'Checked'),
        ('approved', 'Approved'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True, default='draft', tracking=True)

    line_ids = fields.One2many('delivery.order.transfer.line', 'request_id', string='Request Lines')

    delivery_order_id = fields.Many2one(
        'stock.picking',
        string='Delivery Transfer',
        domain="[('picking_type_code', '=', 'outgoing'), ('state', 'not in', ['cancel'])]",
        help="Select a delivery order to fill products."
    )
    transfer_count = fields.Integer(string='Transfer Count', compute='_compute_transfer_count')

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        domain="[('state', 'in', ['sale', 'sent'])]"
    )
    expected_date = fields.Datetime(default=fields.Datetime.now, index=True, required=True, readonly=True,
                                    help="Date when you expect to receive the goods.")
    # expected_date = fields.Datetime(   default=fields.Datetime.now,  index=True,  required=True,compute="_compute_expected_date_readonly", readonly=True,help="Date when you expect to receive the goods.")

    approved_manager_id = fields.Many2one('res.users', string='Approved by')
    checked_manager_id = fields.Many2one('res.users', string='Checked by')
    arranged_manager_id = fields.Many2one('res.users', string='Arranged by')
    receive_manager_id = fields.Many2one('res.users', string='Received by')
    arranged_date = fields.Date(string='Date', readonly=True)
    checked_date = fields.Date(string='Date', readonly=True)
    approved_date = fields.Date(string='Date', readonly=True)
    receiver_date = fields.Date(string='Date', readonly=True)
    receiver_signature = fields.Char(string='Signature', readonly=True)

    driver_name = fields.Char(string='Driver Name')
    truck_plate_no = fields.Char(string='Truck Plate No')
    received_date = fields.Date(string='Received Date')
    signature = fields.Char(string='Signature')

    remark = fields.Text(string="Remark")
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    dest_location_id = fields.Many2one('stock.location', string='Location of Store', required=True,
                                       related='warehouse_id.lot_stock_id')

    # def _compute_expected_date_readonly(self):
    #   for record in self:
    #        record.expected_date_readonly = record.state != 'draft'

    @api.model
    def create(self, vals):
        if vals.get('name', ('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('delivery.order.transfer') or _('New')
        return super(DeliveryOrderTransfer, self).create(vals)

    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_('You cannot delete a record that is not in draft state.'))
        return super(DeliveryOrderTransfer, self).unlink()

    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("There should be at least one request item for confirming the order."))
        self.arranged_manager_id = self.env.user or False
        self.arranged_date = fields.Date.today()
        self.state = 'confirm'

    def action_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_check(self):
        if not self.env.user.has_group('afro_stock_request.group_afro_stock_do_checker'):
            raise UserError('Only a manager can approve this request.')
        self.ensure_one()
        self.checked_manager_id = self.env.user or False
        self.checked_date = fields.Date.today()
        self.state = 'checked'

    def action_approve(self):
        if not self.env.user.has_group('afro_stock_request.group_afro_stock_do_user'):
            raise UserError('Only a do manager can approve this request.')
        self.ensure_one()
        self.approved_manager_id = self.env.user or False
        self.approved_date = fields.Date.today()
        self.state = 'approved'

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancel'

    def _compute_transfer_count(self):
        for record in self:
            record.transfer_count = self.env['stock.picking'].search_count([('id', '=', record.delivery_order_id.id)])

    def action_view_transfer(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("stock.action_picking_tree_all")
        pickings = self.mapped("delivery_order_id")
        if len(pickings) > 1:
            action["domain"] = [("id", "in", pickings.ids)]
        elif pickings:
            action["views"] = [(self.env.ref("stock.view_picking_form").id, "form")]
            action["res_id"] = pickings.id
        return action

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id(self):
        """Filter delivery orders based on the selected sale order."""
        if self.sale_order_id:
            delivery_orders = self.env['stock.picking'].search([
                ('origin', '=', self.sale_order_id.name),
                ('picking_type_code', '=', 'outgoing'),
                ('state', 'not in', ['cancel'])
            ])
            return {'domain': {'delivery_order_id': [('id', 'in', delivery_orders.ids)]}}
        else:
            return {'domain': {
                'delivery_order_id': [('picking_type_code', '=', 'outgoing'), ('state', 'not in', ['cancel'])]}}

    @api.onchange('delivery_order_id')
    def _onchange_delivery_order_id(self):
        """Fill the line items and set request_id based on the selected delivery order."""
        self.line_ids = [(5, 0, 0)]  # Clear existing lines
        if self.delivery_order_id:
            lines = []
            for move in self.delivery_order_id.move_ids_without_package:
                if move.state not in ['cancel']:
                    lines.append((0, 0, {
                        'product_id': move.product_id.id,
                        'product_qty': move.product_uom_qty,
                        'uom_id': move.product_uom.id,
                        'remark': move.name or 'No remark',
                    }))
            self.line_ids = lines

            # Set request_id based on the salesperson from the linked sale order
            sale_order = self.env['sale.order'].search([('name', '=', self.delivery_order_id.origin)], limit=1)
            self.request_id = sale_order.user_id.partner_id if sale_order and sale_order.user_id else False
            self.partner_id = sale_order.partner_id if sale_order and sale_order.partner_id else False

            # Set warehouse_id and dest_location_id based on the selected delivery order
            self.warehouse_id = self.delivery_order_id.picking_type_id.warehouse_id.id
            self.dest_location_id = self.delivery_order_id.location_dest_id.id


class DeliveryOrderTransferLine(models.Model):
    _name = 'delivery.order.transfer.line'
    _description = 'Delivery order note'
    _order = "id desc"

    name = fields.Char(required=True, copy=False, default=lambda self: _('New'))

    product_id = fields.Many2one('product.product', string='Description', required=True)
    product_qty = fields.Float(string='Qty Reserved', required=True)
    product_qty_done = fields.Float(string='Qty Done', required=False)
    uom_id = fields.Many2one('uom.uom', string='Unit', related='product_id.uom_id')
    remark = fields.Char(string="Remark")
    request_id = fields.Many2one('delivery.order.transfer', string='Delivery Order Note', ondelete='cascade')
    state_bool = fields.Boolean(string="State", default=True, required=True)


    @api.model
    def create(self, vals):
        if vals.get('name', ('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('delivery.order.transfer.line') or _('New')
            res = super(DeliveryOrderTransferLine, self).create(vals)
        return res
