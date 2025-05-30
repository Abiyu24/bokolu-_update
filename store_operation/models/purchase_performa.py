from odoo import models, fields, api,_
from odoo.exceptions import ValidationError, UserError
from dateutil.relativedelta import relativedelta


class PurchasePerforma(models.Model):
    _name = 'purchase.performa'
    _description = 'Purchase Performa'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, copy=False, default=lambda self: _('New'), readonly=True)
    partner_id = fields.Many2one('res.partner', string='Vendor')
    representative_id = fields.Many2many('res.users', string='Representative', required=False)
    request_id = fields.Char(string='Store Request', readonly=True)
    store_request_id = fields.Many2one('store.request', string='Store Request', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', related='store_request_id.warehouse_id', string='Warehouse')
    purchase_request_id = fields.Many2one('purchase.request', string='Purchase Request', readonly=True)
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string="End Date")
    performa_status = fields.Boolean(string="Status", default=False)
    performa_line_ids = fields.One2many('purchase.performa.line', 'purchase_performa_id', string='Performa Lines')
    purchase_order_count = fields.Integer(string='Purchase Order Count', compute='_compute_purchase_order_count')

    state = fields.Selection([
        ('draft','Draft'),
        ('won','Won'),
        ('lost', 'Closed'),
        ('cancel','Cancel')
    ], default="draft", tracking=True)

    compare_performa = fields.Selection([
        ('draft','Draft'),
        ('computed','computed'),
        ('cancel', 'cancelled')
    ], default="draft", tracking=True)


    def _compute_purchase_order_count(self):
            for rec in self:
                rec.purchase_order_count = self.env['purchase.order'].search_count([('performa_id', '=', rec.name)])

    def purchase_order_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'target': 'current',
            'views': [
                [self.env.ref('purchase.purchase_order_kpis_tree').id, 'tree'],
                [self.env.ref('purchase.purchase_order_form').id, 'form']
            ],
            'domain': [('is_foreign_purchase', '=', False),('performa_id', '=', self.name)],
        }

    def action_calculate_performa(self):
        for performa in self:
            # Group performa lines by product_id
            product_line_map = {}
            for line in performa.performa_line_ids:
                if line.product_id.id not in product_line_map:
                    product_line_map[line.product_id.id] = []
                product_line_map[line.product_id.id].append(line)

            performa.compare_performa = 'computed'

            # Loop through each product group and find the line with the least price
            for product_id, lines in product_line_map.items():
                # Sort the lines by price_unit to find the least priced line
                lines_sorted_by_price = sorted(lines, key=lambda l: l.price_unit)
                # The first line in the sorted list has the least price
                winning_line = lines_sorted_by_price[0]
                for line in lines:
                    if line == winning_line:
                        # Set the least priced line to 'won'
                        if line.state != 'won':
                            line.state = 'won'
                    else:
                        # Set all other lines to 'lost'
                        if line.state != 'lost':
                            line.state = 'lost'

    @api.onchange('performa_line_ids', 'state')
    def _compute_performa_status(self):
        for rec in self:
            purchase_orders = self.env['purchase.order'].search([('ref', '=', rec.request_id)])
            if len(purchase_orders)>0:
                rec.performa_status = True
            else:
                rec.performa_status = False

    def update_product_template_vendor_info(self):
        for performa in self:
            for line in performa.performa_line_ids:
                product = line.product_id.product_tmpl_id
                product.vendor_id = line.partner_id.id or False
                product.vendor_price_unit = line.price_unit or False


    def create_purchase_order(self):
        # Check if a purchase performa already exists for this purchase request
        existing_performa_order = self.env['purchase.order'].search([('performa_id', '=', self.id)], limit=1)
        if existing_performa_order:
            raise UserError(_('A purchase order has already been created for this performa.'))

        for performa in self:
            # Get winning performa lines (state == 'won')
            winning_lines = performa.performa_line_ids.filtered(lambda line: line.state == 'won')

            if not winning_lines:
                raise ValidationError(_("No winning lines found to create Purchase Orders."))

            # Check if each winning line has a vendor (partner_id) selected
            for line in winning_lines:
                if not line.partner_id:
                    raise ValidationError(
                        _("Please select a vendor (partner) for the performa line: %s") % line.product_id.display_name)


            # Group the winning lines by vendor (partner_id)
            vendor_line_map = {}
            for line in winning_lines:
                if line.partner_id.id not in vendor_line_map:
                    vendor_line_map[line.partner_id.id] = []
                vendor_line_map[line.partner_id.id].append(line)

            # Create a purchase order for each vendor
            for vendor_id, lines in vendor_line_map.items():
                # Check if a purchase order already exists for this vendor and performa
                existing_purchase_orders = self.env['purchase.order'].search([
                    ('performa_id', '=', performa.id),
                    ('partner_id', '=', vendor_id),
                ])

                if existing_purchase_orders:
                    continue

                # Find the receipt picking type based on the warehouse
                picking_type = self.env['stock.picking.type'].search([
                    ('warehouse_id', '=', performa.warehouse_id.id),
                    ('code', '=', 'incoming')  # 'incoming' for receipt operations
                ], limit=1)

                # Prepare the order values
                order_vals = {
                    'is_foreign_purchase': False,
                    'partner_id': vendor_id,
                    'ref': performa.request_id,
                    'performa_id': performa.id,
                    'picking_type_id': picking_type.id if picking_type else False,
                }

                # Prepare the order lines
                order_lines = []
                for line in lines:
                    order_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'product_qty': line.product_qty,
                        'price_unit': line.price_unit,
                        'product_uom': line.product_id.uom_id.id,
                    }))

                order_vals['order_line'] = order_lines

                # Create the purchase order for the vendor
                self.env['purchase.order'].sudo().create(order_vals)
                performa.state = 'won'
                self.update_product_template_vendor_info()

    def action_won(self):
        self.ensure_one()
        self.state = 'won'

    def action_done(self):
        self.ensure_one()
        self.state = 'lost'

    def action_reject(self):
        self.ensure_one()
        self.state = 'cancel'

    @api.model
    def create(self, vals):
        if vals.get('name', ('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('purchase.performa') or _('New')
            res = super(PurchasePerforma, self).create(vals)
            return res



class PurchasePerformaLine(models.Model):
    _name = 'purchase.performa.line'
    _description = 'Purchase Performa Line'

    purchase_performa_id = fields.Many2one('purchase.performa', string='Performa')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    vendor_tag = fields.Many2one('vendor.tag', string='Vendor Status')
    product_qty = fields.Float(string='Quantity', required=True)
    product_quality = fields.Float(string='Quality' )

    product_quality_range = fields.Selection(
        [('1', 'One'), ('2', 'Two'), ('3', 'Three'), ('4', 'Four'), ('5', 'Five')],
        string='Quality',
        required=True,
        default='1'
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    product_uom = fields.Many2one('uom.uom', string='UOM',related = 'product_id.uom_id')
    price_unit = fields.Float(string='Unit Price')
    last_vendor_id = fields.Many2one('res.partner', string='Partner', readonly=True,compute='_compute_last_vendor_info', store=True)
    last_vendor_price_unit = fields.Float(string='Unit Price', readonly=True,compute='_compute_last_vendor_info', store=True)
    response = fields.Integer(string='Response Time', help="Number of days taken by vendor to response")
    warranty = fields.Char(string='Warranty Term')

    @api.depends('product_id')
    def _compute_last_vendor_info(self):
        for line in self:
            if line.product_id:
                # Fetch the last vendor and price for the product from purchase order lines
                purchase_line = self.env['purchase.order.line'].search([
                    ('product_id', '=', line.product_id.id)
                ], limit=1)

                if purchase_line:
                    line.last_vendor_id = purchase_line.partner_id
                    line.last_vendor_price_unit = purchase_line.price_unit
                # else:
                #     # Fallback to product supplier info if no purchase order lines found
                #     supplier_info = self.env['product.supplierinfo'].search([
                #         ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id)
                #     ], order="create_date desc", limit=1)
                #
                #     line.last_vendor_id = supplier_info.name if supplier_info else False
                #     line.last_vendor_price_unit = supplier_info.price if supplier_info else 0.0


    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Update the UOM field based on the selected product."""
        if self.product_id:
            self.product_uom = self.product_id.uom_id.id
        else:

            self.product_uom = False

    partner_id = fields.Many2one('res.partner', string='Vendor')
    representative_id = fields.Many2many('res.users', string='Representative', required=False)
    vendor_types = fields.Many2one('vendor.types', string='Vendor Types', required=False, related='partner_id.vendor_type_id')


    state = fields.Selection([
        ('draft','Draft'),
        ('won','Won'),
        ('lost', 'Lost'),
        ('cancel','Cancel')
    ], default="draft", tracking=True)


class PurchaseOrderPerforma(models.Model):
    _inherit = 'purchase.order'

    performa_id = fields.Many2one('purchase.performa', string='Purchase Performa', readonly=True)
    ref = fields.Char(string="Ref", readonly=True)
    partner_id = fields.Many2one('res.partner', required=True)

    #vendor_type = fields.Selection(
       # [
           # ('wholesale', 'Wholesale Supplier'),
         #   ('import', 'Direct Importer')
      #  ],
     #   string="Vendor Type",
     #   compute="_compute_vendor_type",
     #   store=True
    #)
    vendor_types = fields.Many2one('vendor.types', string='Vendor Types', required=False,
                                   related='partner_id.vendor_type_id')

   # @api.depends('partner_id')
   # def _compute_vendor_type(self):
       # for order in self:
       #     order.vendor_type = order.partner_id.vendor_type_id.name or 'Standard'

    def button_confirm(self):
        # Confirm the purchase order as usual
        res = super(PurchaseOrderPerforma, self).button_confirm()

        # Update the last vendor and last vendor price for each purchase order line's product
        for order in self:
            for line in order.order_line:
                product = line.product_id.product_tmpl_id
                # Set the last vendor and price on the product template
                product.vendor_id = order.partner_id
                product.vendor_price_unit = line.price_unit

        return res


    contract_id = fields.Many2one('vendor.contract', string="Vendor Contract", readonly=True)

    def action_create_vendor_contract(self):
        self.ensure_one()
        for order in self:
            # Ensure the order has a vendor
            if not order.partner_id:
                raise ValidationError(_("Please specify a vendor for the purchase order before creating a contract."))

            # Check if a contract already exists for this purchase order
            if order.contract_id:
                raise UserError(_("A contract has already been created for this purchase order."))

        contract_vals = {
            'vendor_id': order.partner_id.id,
            'purchase_order_id': order.id,
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today() + relativedelta(years=1),  # Example: 1-year contract
            'pricing_terms': f'Pricing terms based on Purchase Order {order.name}',
            'payment_terms': order.payment_term_id.name if order.payment_term_id else '',
            'delivery_schedule': f'Delivery schedule as per Purchase Order {order.name}',
            'quality_requirements': 'Quality expectations to match PO requirements.',
        }
        # Create the vendor contract
        contract = self.env['vendor.contract'].create(contract_vals)

        # Link the contract to the purchase order
        order.contract_id = contract.id

        # Update the contract state
        contract.state = 'active'



class VendorTag(models.Model):
    _name = 'vendor.tag'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'Vendor Status'

    name = fields.Char(string='Type Name', required=True, help='Name of the vendor status.')
    description = fields.Text(string='Description', help='Description of the vendor status.')


class VendorContract(models.Model):
    _name = 'vendor.contract'
    _description = 'Vendor Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Contract Name', required=True, tracking=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', required=True, domain="[('supplier_rank', '>', 0)]",
                                tracking=True)
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    start_date = fields.Date(string='Start Date', required=True, tracking=True)
    end_date = fields.Date(string='End Date', required=True, tracking=True)
    pricing_terms = fields.Text(string='Pricing Terms', help="Details about pre-negotiated pricing, bulk discounts, or special rates.")
    payment_terms = fields.Text(string='Payment Terms', help="Details about payment schedules or requirements.")
    delivery_schedule = fields.Text(string='Delivery Schedule', help="Details about expected delivery timelines.")
    quality_requirements = fields.Text(string='Quality Requirements', help="Details about product or service quality expectations.")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    @api.depends('start_date', 'end_date')
    def _compute_state(self):
        today = fields.Date.today()
        for record in self:
            if record.end_date and record.end_date < today:
                record.state = 'expired'

    @api.model
    def create(self, vals):
        vals['name'] = self.env['ir.sequence'].next_by_code('vendor.contract') or 'New'
        return super(VendorContract, self).create(vals)


    def action_expire(self):
        self.ensure_one()
        self.state = 'expired'

    def action_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_active(self):
        self.ensure_one()
        self.state = 'active'

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancel'