from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RMATemplate(models.Model):
    _inherit = 'rma.template'

    usage = fields.Selection(selection_add=[('sale_order', 'Sale Order')])


class RMA(models.Model):
    _inherit = 'rma.rma'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    sale_order_rma_count = fields.Integer('Number of RMAs for this Sale Order', compute='_compute_sale_order_rma_count')
    company_id = fields.Many2one('res.company', 'Company',
                                 default=lambda self: self.env['res.company']._company_default_get('sale.order'))

    @api.multi
    @api.depends('sale_order_id')
    def _compute_sale_order_rma_count(self):
        for rma in self:
            if rma.sale_order_id:
                rma_data = self.read_group([('sale_order_id', '=', rma.sale_order_id.id), ('state', '!=', 'cancel')],
                                           ['sale_order_id'], ['sale_order_id'])
                if rma_data:
                    rma.sale_order_rma_count = rma_data[0]['sale_order_id_count']
            else:
                rma.sale_order_rma_count = 0.0


    @api.multi
    def open_sale_order_rmas(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order RMAs'),
            'res_model': 'rma.rma',
            'view_mode': 'tree,form',
            'context': {'search_default_sale_order_id': self[0].sale_order_id.id}
        }

    @api.onchange('template_usage')
    @api.multi
    def _onchange_template_usage(self):
        res = super(RMA, self)._onchange_template_usage()
        for rma in self.filtered(lambda rma: rma.template_usage != 'sale_order'):
            rma.sale_order_id = False
        return res

    @api.onchange('sale_order_id')
    @api.multi
    def _onchange_sale_order_id(self):
        for rma in self.filtered(lambda rma: rma.sale_order_id):
            rma.partner_id = rma.sale_order_id.partner_id
            rma.partner_shipping_id = rma.sale_order_id.partner_shipping_id


    @api.multi
    def action_add_so_lines(self):
        make_line_obj = self.env['rma.sale.make.lines']
        for rma in self:
            lines = make_line_obj.create({
                'rma_id': rma.id,
            })
            action = self.env.ref('rma_sale.action_rma_add_lines').read()[0]
            action['res_id'] = lines.id
            return action

    def _create_in_picking_sale_order(self):
        if not self.sale_order_id:
            raise UserError(_('You must have a sale order for this RMA.'))
        if not self.template_id.in_require_return:
            group_id = self.sale_order_id.procurement_group_id.id if self.sale_order_id.procurement_group_id else 0
            sale_id = self.sale_order_id
            values = self.template_id._values_for_in_picking(self)
            update = {'sale_id': sale_id, 'group_id': group_id}
            update_lines = {'group_id': group_id}
            return self._picking_from_values(values, update, update_lines)

        lines = self.lines.filtered(lambda l: l.product_uom_qty >= 1)
        if not lines:
            raise UserError(_('You have no lines with positive quantity.'))
        product_ids = lines.mapped('product_id.id')

        old_picking = self._find_candidate_return_picking(product_ids, self.sale_order_id.picking_ids, self.template_id.in_location_id.id)
        if not old_picking:
            raise UserError('No eligible pickings were found to return (you can only return products from the same initial picking).')

        new_picking = self._new_in_picking(old_picking)
        self._new_in_moves(old_picking, new_picking, {})
        return new_picking

    def _create_out_picking_sale_order(self):
        if not self.sale_order_id:
            raise UserError(_('You must have a sale order for this RMA.'))
        if not self.template_id.out_require_return:
            group_id = self.sale_order_id.procurement_group_id.id if self.sale_order_id.procurement_group_id else 0
            sale_id = self.sale_order_id
            values = self.template_id._values_for_out_picking(self)
            update = {'sale_id': sale_id, 'group_id': group_id}
            update_lines = {'to_refund_so': self.template_id.in_to_refund_so, 'group_id': group_id}
            return self._picking_from_values(values, update, update_lines)

        lines = self.lines.filtered(lambda l: l.product_uom_qty >= 1)
        if not lines:
            raise UserError(_('You have no lines with positive quantity.'))
        product_ids = lines.mapped('product_id.id')

        old_picking = self._find_candidate_return_picking(product_ids, self.sale_order_id.picking_ids, self.template_id.out_location_dest_id.id)
        if not old_picking:
            raise UserError(
                'No eligible pickings were found to duplicate (you can only return products from the same initial picking).')

        new_picking = self._new_out_picking(old_picking)
        self._new_out_moves(old_picking, new_picking, {})
        return new_picking


