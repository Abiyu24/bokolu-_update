from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class TransferNote(models.Model):
    _name = 'transfer.note'
    _description = "Transfer Note"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    requester_id = fields.Many2one('res.users', string='Requester', default=lambda self: self.env.user, tracking=True, readonly=True)
    name = fields.Char(string='Name', required=True, copy=False, default=lambda self: _('New'))
    date = fields.Date(string='Date', required=True, default=fields.Date.today())
    destination_location_id = fields.Many2one('stock.location', string='Destination Location', tracking=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    destination_warehouse_id = fields.Many2one('stock.warehouse', string='To Warehouse', required=True)
    location_id = fields.Many2one('stock.location', string='Location', tracking=True)
    voucher_lines = fields.One2many('transfer.note.line', 'voucher_id', string='Voucher Lines')

    remark = fields.Text(string="Remark")
    ref = fields.Char(string="Reference")
    reason = fields.Char(string="Reason")
    approved_manager_id = fields.Many2one('res.users', string='Approved by', readonly=True)
    approved_date = fields.Date(string='Approved Date', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submit'),
        ('approve', 'Approve'),
        ('validate', 'Validate'),
        ('reject', 'Reject'),
    ], default="draft", tracking=True)

    stock_pick_count = fields.Integer(string='Stock Pick Count', compute='_compute_stock_pick_count')
    transfer_id = fields.Many2one('stock.picking', string='Internal Transfer', readonly=True)
    transfer_count = fields.Integer(string='Transfer Count', compute='_compute_transfer_count')


    @api.onchange('destination_warehouse_id')
    def _onchange_destination_warehouse(self):
        if self.destination_warehouse_id:
            # Filter destination locations based on destination warehouse
            return {
                'domain': {
                    'destination_location_id': [('warehouse_id', '=', self.destination_warehouse_id.id)]
                }
            }
        else:
            # No destination warehouse selected, no filtering
            return {
                'domain': {
                    'destination_location_id': []
                }
            }

    @api.onchange('warehouse_id')
    def _onchange_warehouse(self):
        if self.warehouse_id:
            # Filter destination locations based on destination warehouse
            return {
                'domain': {
                    'location_id': [('warehouse_id', '=', self.warehouse_id.id)]
                }
            }
        else:
            # No destination warehouse selected, no filtering
            return {
                'domain': {
                    'location_id': []
                }
            }


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


    def _compute_stock_pick_count(self):
        for rec in self:
            rec.stock_pick_count = self.env['stock.picking'].search_count([('origin', '=', rec.name)])

    def stock_pick_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Stock Transfer',
            'res_model': 'stock.picking',
            'domain': [('origin', '=', self.name)],
            'view_mode': 'tree,form',
            'target': 'current'
        }

    def action_submit(self):
        self.ensure_one()
        self.state = 'submit'

    def action_reject(self):
        self.ensure_one()
        self.approved_manager_id = self.env.user or False
        self.approved_date = fields.date.today()
        self.state = 'reject'

    def action_approve(self):
        self.ensure_one()
        move_lines = []

        # Validate locations and warehouse
        if not self.location_id or not self.destination_location_id:
            raise ValidationError(_('Source and destination locations must be set.'))

        source_warehouse = self.location_id.get_warehouse()
        dest_warehouse = self.destination_location_id.get_warehouse()

        # Prepare move lines
        for line in self.voucher_lines:
            product = line.product_id
            if not product:
                raise ValidationError(_('Product is not set for one of the voucher lines.'))

            # Fetch available quantity for the product in the source location
            available_quantity = self.env['stock.quant']._get_available_quantity(
                product, self.location_id)

            # Check stock limit constraints
            stock_limit = self.env['stock.location.limit'].search([
                ('product_id', '=', product.id),
                ('location_id', '=', self.location_id.id)
            ], limit=1)

            if stock_limit and available_quantity < stock_limit.minimum_qty:
                raise ValidationError(_(
                    'The transfer of product "%s" falls below the minimum stock level for the location "%s".\n'
                    'Current stock: %.2f, Minimum required: %.2f.'
                ) % (product.display_name, self.location_id.display_name, available_quantity,
                     stock_limit.minimum_qty))

            # Check if available quantity is sufficient
            if available_quantity < line.quantity:
                raise ValidationError(_(
                    'Insufficient quantity of product "%s" in source location "%s".\n'
                    'Available: %.2f, Requested: %.2f.'
                ) % (product.display_name, self.location_id.display_name, available_quantity, line.quantity))

            move_lines.append((0, 0, {
                'name': product.name,
                'product_id': product.id,
                'location_id': self.location_id.id,
                'location_dest_id': self.destination_location_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': product.uom_id.id,
                'origin': self.requester_id.name,
            }))

        # Determine picking type based on warehouse context
        if source_warehouse and dest_warehouse and source_warehouse.id != dest_warehouse.id:
            # Cross-warehouse transfer: Use outgoing from source and incoming to destination
            picking_type = self.env['stock.picking.type'].search([
                ('warehouse_id', '=', source_warehouse.id),
                ('code', '=', 'outgoing')
            ], limit=1)
            if not picking_type:
                raise ValidationError(_(
                    'No outgoing picking type found for warehouse "%s". Please configure one in Inventory > Configuration > Operation Types.'
                ) % source_warehouse.name)
        else:
            # Internal transfer within the same warehouse
            picking_type = self.env['stock.picking.type'].search([
                ('warehouse_id', '=', source_warehouse.id if source_warehouse else False),
                ('code', '=', 'internal')
            ], limit=1)
            if not picking_type:
                raise ValidationError(_(
                    'No internal picking type found for warehouse "%s". Please configure one in Inventory > Configuration > Operation Types.'
                ) % (source_warehouse.name if source_warehouse else 'No Warehouse'))

        # Create picking for transfer
        picking_vals = {
            'partner_id': self.requester_id.partner_id.id if self.requester_id.partner_id else False,
            'location_id': self.location_id.id,
            'location_dest_id': self.destination_location_id.id,
            'move_ids_without_package': move_lines,
            'picking_type_id': picking_type.id,
            'origin': self.name,
        }

        picking = self.env['stock.picking'].sudo().create(picking_vals)

        # Confirm and assign the picking
        try:
            picking.sudo().action_confirm()
            picking.sudo().action_assign()
            picking.sudo().action_set_quantities_to_reservation()
            picking.sudo().button_validate()
        except UserError as e:
            raise ValidationError(_('Picking validation failed: %s') % str(e))

        # Link the created transfer and update state
        self.transfer_id = picking
        self.state = 'approve'

        return True
    #def action_approve(self):
     #  move_lines = []
      #  for line in self.voucher_lines:
       #     product = line.product_id
#
 #           # Fetch available quantity for the product in the source location
  #          available_quantity = self.env['stock.quant']._get_available_quantity(
   #             product, self.location_id)
#
 #           # Check stock limit constraints
  #          stock_limit = self.env['stock.location.limit'].search([
   #             ('product_id', '=', line.product_id.id),
    #          ('location_id', '=', self.location_id.id)  # Source location being checked
     #       ], limit=1)
#
 #           if stock_limit:
  #              #Validate against the minimum quantity
   #             if available_quantity < stock_limit.minimum_qty:
    #                raise ValidationError(_(
     #                  'The transfer of product "%s" falls below the minimum stock level for the location "%s".\n'
      #                 'Current stock: %.2f, Minimum required: %.2f.'
       #             ) % (product.display_name, self.location_id.display_name, available_quantity,
        #                 stock_limit.minimum_qty))
#
 #           # Check if available quantity is sufficient for the transfer
  #          if available_quantity < line.quantity:
   #             raise ValidationError(_(
    #                'Insufficient quantity of product "%s" in source location "%s".\n'
     #               'Available: %.2f, Requested: %.2f.'
      #          ) % (product.display_name, self.location_id.display_name, available_quantity, line.quantity))
#
 #           move_lines.append((0, 0, {
  #              'name': product.name,
    #            'product_id': product.id,
   #             'location_id': self.location_id.id,
     #           'location_dest_id': self.destination_location_id.id,
      #          'product_uom_qty': line.quantity,
       #         'product_uom': product.uom_id.id,
        #        'origin': self.requester_id.name,
         #   }))

        # Determine if it's an internal transfer between warehouses
       # source_warehouse = self.location_id.get_warehouse()
    #    dest_warehouse = self.destination_location_id.get_warehouse()

   #     if source_warehouse and dest_warehouse and source_warehouse.id != dest_warehouse.id:
    #        # Cross-warehouse transfer picking type
        #    picking_type_id = self.env.ref('stock.picking_type_internal').id
            # Find the receipt picking type based on the warehouse
         #   picking_type = self.env['stock.picking.type'].search([
       #         ('warehouse_id', '=', self.warehouse_id.id),
      ##          ('code', '=', 'internal')  # 'incoming' for receipt operations
     #       ], limit=1)
     #   else:
       #      # Internal transfer within the same warehouse
        #    picking_type_id = self.env.ref('stock.picking_type_internal').id
         ##   picking_type = self.env['stock.picking.type'].search([
       #         ('warehouse_id', '=', self.warehouse_id.id),
       ##         ('code', '=', 'internal')  # 'incoming' for operations
      #      ], limit=1)

        # Create picking for transfer
      #  picking = self.env['stock.picking'].sudo().create({
       #     'partner_id': self.requester_id.partner_id.id,
     #       'location_id': self.location_id.id,
      #      'location_dest_id': self.destination_location_id.id,
       #     'move_ids_without_package': move_lines,
       #     'picking_type_id': picking_type.id if picking_type else False,
       #     'origin': self.name,
      #  })

        # Confirm and assign the picking
       # picking.sudo().action_confirm()
      #  picking.sudo().action_assign()

        # Validate the picking by setting reserved quantities and calling button_validate
      #  try:
       #     picking.sudo().action_set_quantities_to_reservation()  # Set reserved quantities
        #    picking.sudo().button_validate()  # Validate the picking

      #  except UserError as e:
       #     raise ValidationError(_('Picking validation failed: %s' % str(e)))

        # Link the created transfer to the issue voucher
       # self.transfer_id = picking
       # self.state = 'approve'

    def action_validate(self):
        self.ensure_one()
        self.approved_manager_id = self.env.user or False
        self.approved_date = fields.date.today()
        self.state = 'validate'

    def action_draft(self):
        self.ensure_one()
        self.state = 'draft'

    @api.model
    def create(self, vals):
        if vals.get('name', ('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('transfer.note') or _('New')
            res = super(TransferNote, self).create(vals)
            return res

    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_('You can not delete record that is not draft state.'))
            else:
                return super(TransferNote, self).unlink()


class TransferNoteLine(models.Model):
    _name = 'transfer.note.line'
    _description = 'Transfer Note Line'

    voucher_id = fields.Many2one('transfer.note', string='Voucher')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float(string='Quantity', required=True)
    product_uom_id = fields.Many2one( 'uom.uom',readonly=True,  string='Product Unit', related='product_id.uom_id' )
    remark = fields.Char(string="Remark")
    product_catagory = fields.Many2one('product.category', 'Product Categories', related='product_id.categ_id')

    sequence_number = fields.Integer(string='SN/NO',readonly=True, default=1)

    _order = 'voucher_id, sequence_number'

    @api.model
    def create(self, values):
        if 'sequence' not in values:
            values['sequence_number'] = self._get_last_sequence(values.get('voucher_id')) + 1
        return super(TransferNoteLine, self).create(values)

    def _get_last_sequence(self, voucher_id):
        last_line = self.search([('voucher_id', '=', voucher_id)], order='sequence_number desc', limit=1)
        return last_line.sequence_number if last_line else 0


    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Update the UOM field based on the selected product."""
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id.id
        else:
            self.product_uom_id = False

    unit_price = fields.Float(string="Unit Price", related='product_id.list_price', store=True, readonly=True)
    total_price = fields.Float(string="Total Price", compute='_compute_total_price', store=True)

    @api.depends('quantity', 'unit_price')
    def _compute_total_price(self):
        """Compute the total price without tax."""
        for line in self:
            line.total_price = line.quantity * line.unit_price

    qty_available = fields.Float(
        string='Available Quantity',
        compute='_compute_qty_available',
        store=False
    )

    @api.depends('product_id', 'voucher_id.location_id')
    def _compute_qty_available(self):
        for line in self:
            if line.product_id and line.voucher_id.location_id:
                # Search for all stock quants that match the product and location
                stock_quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', line.voucher_id.location_id.id)
                ])
                # Sum the quantities of all matching stock quants
                line.qty_available = sum(stock_quants.mapped('quantity')) if stock_quants else 0
            else:
                line.qty_available = 0