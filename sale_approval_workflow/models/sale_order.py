from odoo import _,fields, models, api
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    credit_status = fields.Selection([
        ('within_limit', 'Within Limit'),
        ('exceeds_limit', 'Exceeds Limit'),
    ], string='Credit Status', compute='_compute_credit_status', store=True)
    credit_limit_approval_ids = fields.One2many(
        'credit.limit.approval',
        'sale_order_id',
        string='Credit Limit Approvals'
    )
    approval_workflow_ids = fields.One2many(
        'sale.approval.workflow',
        'sale_order_id',
        string='Approval Workflows'
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Quotation'),
            ('marketing_approval', 'SM approval'),
            ('technical_approval', 'TM approval'),
            ('approved', 'Approved'),
            ('sent', 'Quotation Sent'),
            ('sale', 'Sales Order'),
            ('done', 'Locked'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )

    @api.depends('partner_id', 'amount_total')
    def _compute_credit_status(self):
        for order in self:
            if order.partner_id and order.amount_total:
                partner = order.partner_id
                if order.amount_total > partner.credit_limit:
                    order.credit_status = 'exceeds_limit'
                else:
                    order.credit_status = 'within_limit'
            else:
                order.credit_status = False

    def action_submit_for_marketing_approval(self):
        if self.state != 'draft':
            raise UserError("Quotation must be in Draft state to submit for approval.")
        self.state = 'marketing_approval'
        marketing_group = self.env.ref('sale_approval_workflow.group_marketing_manager')
        users = marketing_group.users
        for user in users:
            self.message_notify(
                partner_ids=user.partner_id.ids,
                subject=f"Quotation {self.name} Awaiting Your Approval",
                body=f"Please review and approve quotation {self.name}."
            )
        return True

    def action_marketing_approve(self):
        if self.state != 'marketing_approval':
            raise UserError("Quotation must be in Waiting for Marketing Approval state.")
        self.state = 'technical_approval'
        technical_group = self.env.ref('sale_approval_workflow.group_technical_manager')
        users = technical_group.users
        for user in users:
            self.message_notify(
                partner_ids=user.partner_id.ids,
                subject=f"Quotation {self.name} Awaiting Your Approval",
                body=f"Please review and approve quotation {self.name} from a technical perspective."
            )
        return True

    def action_technical_approve(self):
        if self.state != 'technical_approval':
            raise UserError("Quotation must be in Waiting for Technical Approval state.")
        self.state = 'approved'
        return True

  #  def action_send_quotation(self):
   #     if self.state != 'approved':
    #        raise UserError("Quotation must be Approved before sending.")
     #   self.state = 'sent'
      #  return self.action_quotation_send()

    def action_confirm(self):
        for order in self:
            # Credit Sales check
            if order.credit_status == 'exceeds_limit' and not order.credit_limit_approval_ids.filtered(lambda a: a.state == 'approved'):
                raise UserError('Credit limit exceeded. Please request approval.')
            # Approval Workflow check
            if order.state not in ('sent', 'approved'):
                raise UserError("Quotation must be Sent or Approved before confirming.")

        # Default tax assignment
        default_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company_id.id),
            ('name', '!=', False)
        ], limit=1)
        if not default_tax:
            default_tax = self.env['account.tax'].create({
                'name': 'Default Sale Tax',
                'amount': 15.0,
                'type_tax_use': 'sale',
                'amount_type': 'percent',
                'company_id': self.company_id.id,
            })

        for line in self.order_line:
            if not line.tax_id:
                line.tax_id = default_tax

        return super().action_confirm()

    @api.constrains('state')
    def _check_rfq_send_state(self):
        for record in self:
            if record.state != 'approved' and record.env.context.get('mark_so_as_sent'):
                raise UserError(_("RFQ can only be sent after both marketing and technical approvals are completed!"))

    #def action_rfq_send(self):
     #   """ Send RFQ email to customer after approval is complete """
      #  self.ensure_one()

        # Check if we can send (both approvals done)
       # if self.state != 'approved':
        #    raise UserError(_("RFQ can only be sent after both marketing and technical approvals are completed!"))

        # Get the email template
       # template = self.env.ref('sale.email_template_edi_sale', False)

        # Prepare email composition context
        #ctx = {
         #   'default_model': 'sale.order',
          #  'default_res_ids': [self.id],
           # 'default_use_template': bool(template),
          #  'default_template_id': template and template.id or False,
         #   'default_composition_mode': 'comment',
          #  'mark_so_as_sent': True,
           # 'force_email': True,
         #   'active_ids': self.ids,
        #}

        # Return email composition action
       # return {
          #  'type': 'ir.actions.act_window',
          #  'res_model': 'mail.compose.message',
          #  'view_mode': 'form',
           # 'view_id': self.env.ref('mail.email_compose_message_wizard_form').id,
           # 'target': 'new',
           # 'context': ctx,
            #'name': _('Send RFQ'),
       # }