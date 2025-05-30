from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class GoodRecivingNoteTransfer(models.Model):
    _name = 'good.reciving.note.transfer'
    _description = 'good receiving note'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    request_id = fields.Many2one('good.reciving.note.transfer', string='Good Reciving Note', ondelete='cascade')
    #name = fields.Char(required=True, copy=False, default=lambda self: _('New'), states={"draft": [("readonly", False)]})
    name = fields.Char(required=True, copy=False, default=lambda self: _('New'))
    #name = fields.Char(  required=True, copy=False,default=lambda self: _('New'),compute="_compute_name_readonly", store=False) # Optional: Store in DB only if needed)
    requester_id = fields.Many2one('res.users', string='Received by', default=lambda self: self.env.user)
   # dest_location_id = fields.Many2one('stock.location', string='Location of Store', readonly=True,store=True)
    #line_ids = fields.One2many('good.reciving.note.transfer', 'request_id', string='Request Lines')
    location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        help='Source location for the transfer.'
    )
    destination_location_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        required=True,
        help='Destination location for the transfer.'
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('approved', 'Approved'),
        ('done', 'Validated'),
        ('recieve', 'Received'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True, default='draft', tracking=True)
    line_ids = fields.One2many('good.reciving.note.transfer.line', 'request_id', string='Request Lines')
    transfer_id = fields.Many2one('stock.picking', string='Internal Transfer', readonly=True)
    transfer_count = fields.Integer(string='Transfer Count', compute='_compute_transfer_count',store=False)

   # expected_date = fields.Datetime(default=fields.Datetime.now,index=True, required=True,readonly=True,compute="_compute_expected_date_readonly",store=False
     #   ,help="Date when you expect to receive the goods.",
   # )
    expected_date = fields.Datetime(default=fields.Datetime.now, index=True, required=True, readonly=True,
                                   store=False
                                    , help="Date when you expect to receive the goods.",
                                    )
    # categ_id = fields.Many2one('product.category', 'Product Categories')
    invoice_id = fields.Many2one('account.move', string='Invoice')
    invoice_id_char = fields.Char(string='Invoice')
    purchase_order = fields.Char(string='Purchase Order No')
    # purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order')
    inspected_manager_id = fields.Many2one('res.users', string='Delivered by')
    inspected_date = fields.Date(string='Date', readonly=True)
    checked_manager_id = fields.Many2one('res.users', string='Approved by')
    checked_date = fields.Date(string='Date', readonly=True)
    recieved_manager_id = fields.Many2one('res.users', string='Received by')
    recieved_date = fields.Date(string='Date', readonly=True)

    remark = fields.Text(string="Remark")
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')

    partner_id = fields.Many2one('res.partner', string='Customer')
    # Existing fields...
   # name_readonly = fields.Char(string='Readonly Name',compute='_compute_name_readonly',store=True,help="Automatic name based on state", compute_sudo=True )

   # @api.depends('state')
  #  def _compute_name_readonly(self):
        #for record in self:
           # if record.state != 'draft':
       #         record.name_readonly = "Record is not in draft state"  # Or your actual naming logic
       #     else:
        #        record.name_readonly = "Draft Record"

    def _compute_expected_date_readonly(self):
        for record in self:
            record.expected_date_readonly = record.state != 'draft'


    @api.model
    def create(self, vals):
        if vals.get('name', ('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('good.reciving.note.transfer') or _('New')
            res = super(GoodRecivingNoteTransfer, self).create(vals)
            return res

    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_('You can not delete record that is not draft state.'))
            else:
                return super(GoodRecivingNoteTransfer, self).unlink()


    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(
                _("There should be at least one request item for confirming the order.")
            )
        self.state = 'confirm'

    def action_draft(self):
        self.ensure_one()
        self.state = 'draft'

    #def action_approve(self):
       # self.ensure_one()
       # self.checked_manager_id = self.env.user  or False
       # self.checked_date = fields.date.today()
      #  self._create_internal_transfer()
      #  self.state = 'approved'

    def action_done(self):
        self.ensure_one()
        self.inspected_manager_id = self.env.user or False
        self.inspected_date = fields.date.today()
        self.state = 'done'

    def action_recieve(self):
        self.ensure_one()
        self.recieved_manager_id = self.env.user  or False
        self.recieved_date = fields.date.today()
        self.state = 'recieve'

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancel'

   # def _create_internal_transfer(self):
   #     move_lines = []
      #  partner_location = self.env.ref('stock.stock_location_suppliers')

      #  for line in self.line_ids:
       #     product = line.product_id
       #     # Get available quantity for the product in the source location
       #     available_quantity = self.env['stock.quant']._get_available_quantity(
         #       product, self.dest_location_id)

        #    stock_limit = self.env['stock.location.limit'].search([
         #       ('product_id', '=', line.product_id.id),
         #       ('location_id', '=', self.dest_location_id.id)  # Destination location being checked
       #     ], limit=1)

          #  if stock_limit:
           #     if available_quantity + line.product_qty > stock_limit.qty:
           #         raise ValidationError(_(
            #            'The transfer of product "%s" exceeds the maximum stock limit for the location "%s".\n'
            #            'Current stock: %.2f, Maximum allowed: %.2f.'
            #        ) % (line.product_id.display_name, self.dest_location_id.display_name, available_quantity,
                  #       stock_limit.qty))

           # move_lines.append((0, 0, {
          #      'name': line.product_id.name,
            #    'product_id': line.product_id.id,
           #     'partner_id': self.partner_id.id,
          #      'location_id': partner_location.id,
          #      'location_dest_id': self.dest_location_id.id,
            #    'product_uom': line.product_id.uom_id.id,
          #      'product_uom_qty': line.product_qty,
        #        'origin': self.name,
      #      }))

     #   if self.dest_location_id:
       #     picking_type = self.env['stock.picking.type'].search([
          #      ('warehouse_id', '=', self.warehouse_id.id),
        #        ('code', '=', 'incoming')  # 'incoming' for receipt operations
        #    ], limit=1)

      #  picking = self.env['stock.picking'].sudo().create({
       #     'partner_id': self.partner_id.id,
      #      'location_id': partner_location.id,
      #      'location_dest_id': self.dest_location_id.id,
       #     'move_ids_without_package': move_lines,
      #      'picking_type_id': picking_type.id if picking_type else False,
      #      'origin': self.name,
      #  })
      #  # Add prefix to the picking sequence
      #  picking.sudo().write({
      #      'name': f"CENTER-{picking.name}"
      #  })

    #    picking.sudo().action_confirm()
    #    picking.sudo().action_assign()
        # Validate the picking by setting reserved quantities and calling button_validate
     #   try:
      #      picking.sudo().action_set_quantities_to_reservation()  # Set reserved quantities
       #     picking.sudo().button_validate()  # Validate the picking

        #except UserError as e:
         #   raise ValidationError(_('Picking validation failed: %s' % str(e)))

       # self.transfer_id = picking
    def _create_internal_transfer(self):
        self.ensure_one()
        move_lines = []
        partner_location = self.env.ref('stock.stock_location_suppliers', raise_if_not_found=False)
        if not partner_location:
            raise ValidationError(
                _('Supplier location not found. Please ensure the stock module is properly configured.'))

        # Validate warehouse
        if not self.warehouse_id:
            raise ValidationError(_('Warehouse must be set.'))

        # Validate source and destination locations
        source_location = self.location_id
        dest_location = self. destination_location_id
        if not source_location:
            raise ValidationError(_('Source location must be set.'))
        if not dest_location:
            raise ValidationError(_('Destination location must be set.'))

        # Prepare move lines
        for line in self.line_ids:  # Use line_ids
            product = line.product_id
            if not product:
                raise ValidationError(_('Product is not set for one of the transfer lines.'))

            # Fetch available quantity at source
            available_quantity = self.env['stock.quant']._get_available_quantity(product, source_location)

            # Check stock limit constraints (minimum stock)
            stock_limit = self.env['stock.location.limit'].search([
                ('product_id', '=', product.id),
                ('location_id', '=', source_location.id)
            ], limit=1)
            if stock_limit and available_quantity < stock_limit.minimum_qty:
                raise ValidationError(_(
                    'The transfer of product "%s" falls below the minimum stock level for the location "%s".\n'
                    'Current stock: %.2f, Minimum required: %.2f.'
                ) % (product.display_name, source_location.display_name, available_quantity, stock_limit.minimum_qty))

            # Check if available quantity is sufficient
            if available_quantity < line.product_qty:
                raise ValidationError(_(
                    'Insufficient quantity of product "%s" in source location "%s".\n'
                    'Available: %.2f, Requested: %.2f.'
                ) % (product.display_name, source_location.display_name, available_quantity, line.product_qty))

            move_lines.append((0, 0, {
                'name': product.name,
                'product_id': product.id,
                'location_id': partner_location.id,  # Use supplier location for GRN
                'location_dest_id': dest_location.id,
                'product_uom_qty': line.product_qty,
                'product_uom': product.uom_id.id,
                'origin': self.requester_id.name if self.requester_id else self.name,
            }))

        # Determine picking type
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', self.warehouse_id.id),
            ('code', '=', 'incoming')
        ], limit=1)
        if not picking_type:
            raise ValidationError(_(
                'No incoming picking type found for warehouse "%s". Please configure one in Inventory > Configuration > Operation Types.'
            ) % self.warehouse_id.name)

        # Create picking
        picking_vals = {
            'partner_id': self.requester_id.partner_id.id if self.requester_id and self.requester_id.partner_id else False,
            'location_id': partner_location.id,
            'location_dest_id': dest_location.id,
            'move_ids_without_package': move_lines,
            'picking_type_id': picking_type.id,
            'origin': self.name,
        }

        picking = self.env['stock.picking'].sudo().create(picking_vals)
        picking.sudo().write({'name': f"CENTER-{picking.name}"})

        try:
            picking.sudo().action_confirm()
            picking.sudo().action_assign()
            picking.sudo().button_validate()
        except UserError as e:
            raise ValidationError(_('Picking validation failed: %s') % str(e))

        return picking

    def action_approve(self):
        self.ensure_one()
        self.checked_manager_id = self.env.user
        self.checked_date = fields.Date.today()
        picking = self._create_internal_transfer()
        self.transfer_id = picking
        self.state = 'approved'  # Fix state
        return True

    def _compute_transfer_count(self):
        for record in self:
            record.transfer_count = self.env['stock.picking'].search_count([('id', '=', record.transfer_id.id)])

    def action_view_transfer(self):
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        pickings = self.mapped("transfer_id")
        if len(pickings) > 1:
            action["domain"] = [("id", "in", pickings.ids)]
        elif pickings:
            action["views"] = [(self.env.ref("stock.view_picking_form").id, "form")]
            action["res_id"] = pickings.id
        return action

class GoodRecivingNoteTransferLine(models.Model):
    _name = 'good.reciving.note.transfer.line'
    _description = 'Good receiving note'
    _order = "id desc"



    name = fields.Char(required=True, copy=False, default=lambda self: _('New'))

    #name = fields.Char( required=True, copy=False, default=lambda self: _('New'),  states={"draft": [("readonly", False)]})
    #name = fields.Char(
     #   required=True,
        #copy=False,
       # default=lambda self: _('New'),
     #   compute='_compute_name_readonly',
       # store=False,  # Don't store in database
   # )

    product_id = fields.Many2one('product.product', string='Description', required=True)
    product_qty = fields.Float(string='Qty', required=True)
    product_qty_done = fields.Float(string='Qty Approved', required=False)
    request_id = fields.Many2one('good.reciving.note.transfer', string='Good Reciving Note', ondelete='cascade')
    uom_id = fields.Many2one('uom.uom', string='Unit',related='product_id.uom_id')
    remark = fields.Char(string="Remark")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('approved', 'Checked'),
        ('done', 'Approved'),
        ('recieve', 'Recieved'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True, default='draft', related="request_id.state" )
    product_catagory = fields.Many2one('product.category', 'Product Categories', related='product_id.categ_id')

    sequence_number = fields.Integer(string='SN/NO',readonly=True, default=1)

    _order = 'request_id, sequence_number'

    @api.depends('state')
    def _compute_name_readonly(self):
        for record in self:
            if record.state != 'draft':
                record.name_readonly = "Record is not in draft state"  # Or your actual naming logic
            else:
                record.name_readonly = "Draft Record"


    @api.model
    def create(self, values):
        if 'sequence' not in values:
            values['sequence_number'] = self._get_last_sequence(values.get('request_id')) + 1
        return super(GoodRecivingNoteTransferLine, self).create(values)

    def _get_last_sequence(self, request_id):
        last_line = self.search([('request_id', '=', request_id)], order='sequence_number desc', limit=1)
        return last_line.sequence_number if last_line else 0


    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Update the UOM field based on the selected product."""
        if self.product_id:
            self.uom_id = self.product_id.uom_id.id
        else:
            self.uom_id = False

    unit_price = fields.Float(string="Unit Price", related='product_id.list_price', store=True, readonly=True)
    total_price = fields.Float(string="Total Price", compute='_compute_total_price', store=True)

    @api.depends('product_qty', 'unit_price')
    def _compute_total_price(self):
        """Compute the total price without tax."""
        for line in self:
            line.total_price = line.product_qty * line.unit_price


