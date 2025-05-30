from odoo import models, fields, api,_
from odoo.exceptions import UserError

class ModelSignature(models.AbstractModel):
    _name = 'model.signature'
    _description = 'Model Signature'

    digitized_signature = fields.Binary('Receiver Signature')
    approved_digitized_signature = fields.Binary('Approver Signature')



class StoreRequest(models.Model):
    _name = 'store.request'
    _description = 'Store Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'model.signature']

    name = fields.Char(string='Name', required=True, copy=False, default=lambda self: _('New'), readonly=True)
    requested_date = fields.Date(string='Request date', required=True, default=fields.Date.today())
    request_lines = fields.One2many('store.request.line', 'request_id', string='Request Lines')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True)
    location_id = fields.Many2one('stock.location', string='Source Location', related='warehouse_id.lot_stock_id', readonly=True, store=True)
    requester_id = fields.Many2one('res.users', string='Requested by', default=lambda self: self.env.user)
    approved_manager_id = fields.Many2one('res.users', string='Approved by')
    received_manager_id = fields.Many2one('res.users', string='Received by')
    destination_location_id = fields.Many2one('stock.location', string='Destination Location', required=True, store=True)
    reason = fields.Char(string="Reason")

    received_date = fields.Date(string='Received Date', readonly=True)
    approved_date = fields.Date(string='Approved Date', readonly=True)

    remark = fields.Text(string="Remark")
    checked_manager_id = fields.Many2one('res.users', string='Checked by')
    checked_date = fields.Date(string='Checked Date', readonly=True)


    ref = fields.Char(string="Reference")
    state = fields.Selection([
        ('draft','Draft'),
        ('submit','Submit'),
        ('check', 'Check'),
        ('approve', 'Approve'),
        ('validate','Validate'),
        ('on_request', 'Request'),
        ('on_siv', 'SIV'),
        ('cancel', 'Cancel')
    ], default="draft", tracking=True)
    siv_count = fields.Integer(string='SIV Count', compute='_compute_siv_count')
    pr_count = fields.Integer(string='Purchase Request Count', compute='_compute_pr_count')
    approved_by = fields.Many2one('res.users', string="Approver", tracking=True)
    siv_ids = fields.One2many('store.issue.voucher', 'request_id', string='SIVs')
    transfer_count = fields.Integer(string='Transfer Count', compute='_compute_transfer_count')

    def _compute_siv_count(self):
        for rec in self:
            rec.siv_count = self.env['store.issue.voucher'].search_count([('request_id', '=', rec.id)])

    def _compute_pr_count(self):
        for rec in self:
            rec.pr_count = self.env['purchase.request'].search_count([('store_request_id', '=', rec.id)])

    def _compute_transfer_count(self):
        for record in self:
            transfer_ids = record.siv_ids.mapped('transfer_id').ids
            record.transfer_count = len(transfer_ids)

    def action_view_transfer(self):
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        pickings = self.siv_ids.mapped("transfer_id")
        if len(pickings) > 1:
            action["domain"] = [("id", "in", pickings.ids)]
        elif pickings:
            action["views"] = [(self.env.ref("stock.view_picking_form").id, "form")]
            action["res_id"] = pickings.id
        return action

    def pr_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Request',
            'res_model': 'purchase.request',
            'domain': [('store_request_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current'
        }

    def siv_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Store Issue Voucher',
            'res_model': 'store.issue.voucher',
            'domain': [('request_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current'
        }

    def action_submit(self):
        self.ensure_one()
        if not self.request_lines:
            raise UserError(
                _("There should be at least one request item for confirming the order.")
            )
        self.state = 'submit'

    def action_approve(self):
        self.ensure_one()
        self.approved_manager_id = self.env.user or False
        self.approved_date = fields.date.today()
        self.state = 'approve'

    def action_reject(self):
        self.ensure_one()
        self.approved_manager_id = self.env.user or False
        self.approved_date = fields.date.today()
        self.state = 'reject'

    def action_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancel'

    def action_receive(self):
        self.ensure_one()
        self.received_manager_id = self.env.user  or False
        self.received_date = fields.date.today()
        self.state = 'validate'

    def action_check(self):
        self.ensure_one()
        self.checked_manager_id = self.env.user  or False
        self.checked_date = fields.date.today()
        self.state = 'check'


    def create_purchase_request(self):
        PurchaseRequest = self.env['purchase.request']
        PurchaseRequestLine = self.env['purchase.request.line']
        for request in self:
            if request.state=="approve":
                request.state = "on_request"
                purchase_request = PurchaseRequest.create({
                    'store_request_id': request.id,
                    'requester_id': request.requester_id.id,
                    'warehouse_id': request.warehouse_id.id,
                    'location_id': request.location_id.id,
                    'destination_location_id': request.destination_location_id.id,
                    'reason': request.reason,
                    'ref': request.ref,
                    'state': 'submit',
                })
                for line in request.request_lines:
                    PurchaseRequestLine.create({
                        'request_id': purchase_request.id,
                        'product_id': line.product_id.id,
                        'quantity': line.quantity,
                        'item_code': line.item_code,
                        'sequence_number': line.sequence_number,
                    })


    def check_product_availability(self):
        """ Check if products in request lines exist in the specified warehouse and location. """
        for request in self:
            for line in request.request_lines:
                product = line.product_id
                location = request.location_id

                # Get available quantity of the product in the warehouse location
                stock_quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location.id)
                ], limit=1)

                if not stock_quant or stock_quant.quantity < line.quantity:
                    raise UserError(_(
                        "Not enough quantity for product '%s' in location '%s'. "
                        "Available: %s, Requested: %s" % (
                            product.name, location.name, stock_quant.quantity if stock_quant else 0, line.quantity)
                    ))


    def create_issue_voucher(self):
        self.check_product_availability()  # Check if products are available in the location

        # Check if a purchase performa already exists for this purchase request
        existing_tender_order = self.env['store.issue.voucher'].search([('request_id', '=', self.id)], limit=1)
        if existing_tender_order:
            raise UserError(_('A SIV has already been created for this request.'))

        StoreIssueVoucher = self.env['store.issue.voucher']
        StoreIssueVoucherLine = self.env['store.issue.voucher.line']
        for request in self:
            if request.state=="approve" or request.state=="on_request":
                request.state = "on_siv"

            issue_voucher = StoreIssueVoucher.create({
                'requester_id': request.requester_id.id,
                'request_id': request.id,
                'location_id':request.location_id.id,
                'destination_location_id':request.destination_location_id.id,
                'warehouse_id':request.warehouse_id.id,
                'remark':request.remark,
                'ref': request.ref,
                'reason': request.reason,
                'state': 'submit',
            })
            for line in request.request_lines:
                StoreIssueVoucherLine.create({
                    'voucher_id': issue_voucher.id,
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                })

    def create_issue_voucher_finished(self):
        StoreIssueVoucher = self.env['store.issue.voucher']
        StoreIssueVoucherLine = self.env['store.issue.voucher.line']
        for request in self:
            if request.state=="approve":
                request.state = "on_siv"

            issue_voucher = StoreIssueVoucher.create({
                'request_id': request.id,
                'location_id':request.location_id.id,
                'destination_location_id':request.destination_location_id.id,
                'warehouse_id':request.warehouse_id.id,
            })
            for line in request.request_lines:
                StoreIssueVoucherLine.create({
                    'voucher_id': issue_voucher.id,
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                })

    def create_issue_voucher_asset(self):
        StoreIssueVoucher = self.env['store.issue.voucher']
        StoreIssueVoucherLine = self.env['store.issue.voucher.line']
        for request in self:
            if request.state=="approve":
                request.state = "on_siv"

            issue_voucher = StoreIssueVoucher.create({
                'request_id': request.id,
                'location_id':request.location_id.id,
                'destination_location_id':request.destination_location_id.id,
                'warehouse_id':request.warehouse_id.id,
            })
            for line in request.request_lines:
                StoreIssueVoucherLine.create({
                    'voucher_id': issue_voucher.id,
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                })


    @api.model
    def create(self, vals):
        if vals.get('name', ('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('store.request') or _('New')
            res = super(StoreRequest, self).create(vals)
            return res

    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_('You can not delete record that is not draft state.'))
            else:
                return super(StoreRequest, self).unlink()


class StoreRequestLine(models.Model):
    _name = 'store.request.line'
    _description = 'Store Request Line'
    _order = 'request_id'

    request_id = fields.Many2one('store.request', string='Store Request')
    product_id = fields.Many2one('product.product', string='Product Description', required=True)
    quantity = fields.Float(string='Quantity', required=True)
    uom_id = fields.Many2one('uom.uom', related="product_id.uom_po_id")
    remark = fields.Char(string="Remark")
    item_code = fields.Char(string='Item Code')
    sequence_number = fields.Integer(string='SN/NO',readonly=True, default=1)

    qty_available = fields.Float(
        string='Available Quantity',
        compute='_compute_qty_available',
        store=False
    )

    _order = 'request_id, sequence_number'

    @api.depends('product_id', 'request_id.location_id')
    def _compute_qty_available(self):
        for line in self:
            if line.product_id and line.request_id.location_id:
                stock_quant = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', line.request_id.location_id.id)
                ], limit=1)
                line.qty_available = stock_quant.quantity if stock_quant else 0
            else:
                line.qty_available = 0

    @api.model
    def create(self, values):
        if 'sequence' not in values:
            values['sequence_number'] = self._get_last_sequence(values.get('request_id')) + 1
        return super(StoreRequestLine, self).create(values)

    def _get_last_sequence(self, request_id):
        last_line = self.search([('request_id', '=', request_id)], order='sequence_number desc', limit=1)
        return last_line.sequence_number if last_line else 0


from odoo import models, fields, api
from datetime import datetime, timedelta

class SlowMovingProductsReport(models.Model):
    _name = 'inventory.slow.moving.report'
    _description = 'Slow Moving Products Report'
    _rec_name = 'product_id'
    _auto = False  # This is a report model; no physical table in the database

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    last_movement_date = fields.Date(string='Last Movement Date', readonly=True)
    days_since_last_movement = fields.Integer(string='Days Since Last Movement', readonly=True)
    default_code = fields.Char(string='Reference', readonly=True)

    def init(self):
        # Create the SQL query for the report
        query = """
        CREATE OR REPLACE VIEW inventory_slow_moving_report AS (
            SELECT
                row_number() OVER () AS id,
                pp.id AS product_id,  
                pp.default_code AS default_code,  
                MAX(
                    COALESCE(
                        sm.date,  -- Date from stock movements
                        po.date_order  -- Date from purchase orders
                    )
                ) AS last_movement_date,
                DATE_PART('day', CURRENT_DATE - MAX(
                    COALESCE(
                        sm.date,
                        po.date_order
                    )
                )) AS days_since_last_movement
            FROM
                product_product pp
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            JOIN product_category pc ON pt.categ_id = pc.id
            LEFT JOIN stock_quant sq ON pp.id = sq.product_id
            LEFT JOIN stock_move sm ON sm.product_id = pp.id AND sm.state = 'done'
            LEFT JOIN stock_location sl ON sm.location_id = sl.id
            LEFT JOIN stock_warehouse sw ON sl.warehouse_id = sw.id
            LEFT JOIN purchase_order_line pol ON pol.product_id = pp.id
            LEFT JOIN purchase_order po ON pol.order_id = po.id AND po.state IN ('purchase', 'done')
            WHERE
                pt.type != 'service'  -- Exclude service-type products
                AND pt.active = True  -- Exclude archived products
            GROUP BY
                pp.id
        );
        """
        self.env.cr.execute(query)

    @api.model
    def notify_slow_moving_products(self):
        threshold = int(self.env['ir.config_parameter'].sudo().get_param('slow_moving_days', 30))
        slow_moving_products = self.search([('days_since_last_movement', '>=', threshold)])
        if slow_moving_products:
            # Logic to send notification or email
            message = "The following products are classified as slow-moving:\n" + \
                      "\n".join([product.product_id.display_name for product in slow_moving_products])
            self.env['mail.message'].create({
                'subject': 'Slow-Moving Products Alert',
                'body': message,
                'model': 'inventory.slow.moving.report',
            })



class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    slow_moving_days = fields.Integer(string="Slow-Moving Threshold (Days)", default=30)
    slow_moving_frequency = fields.Integer(string="Low Transaction Frequency (Movements)", default=5)

    def set_values(self):
        res = super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param('slow_moving_days', self.slow_moving_days)
        self.env['ir.config_parameter'].sudo().set_param('slow_moving_frequency', self.slow_moving_frequency)
        return res

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res.update({
            'slow_moving_days': int(self.env['ir.config_parameter'].sudo().get_param('slow_moving_days', 30)),
            'slow_moving_frequency': int(self.env['ir.config_parameter'].sudo().get_param('slow_moving_frequency', 5)),
        })
        return res


#
# class VendorType(models.Model):
#     _name = 'vendor.type'
#     _description = 'Vendor Type'
#     _rec_name = "vendor_id"
#     _inherit = ["mail.thread", "mail.activity.mixin"]
#
#     vendor_id = fields.Many2one('res.partner', string='Vendor')
#     vendor_type = fields.Selection(
#         [
#             ('wholesale', 'Wholesale Supplier'),
#             ('import', 'Direct Importer')
#         ],
#         string="Vendor Type",
#         help="Classify the vendor as either a Wholesale Supplier or a Direct Importer"
#     )
#     description = fields.Text(string='Description')
#
#     _sql_constraints = [
#         (
#             'unique_vendor',
#             'UNIQUE(vendor_id)',
#             'A partner can only be assigned once!'
#         )
#     ]