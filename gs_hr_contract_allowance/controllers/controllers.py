# -*- coding: utf-8 -*-
# from odoo import http


# class GsContractAllowance(http.Controller):
#     @http.route('/gs_hr_contract_allowance/gs_hr_contract_allowance/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/gs_hr_contract_allowance/gs_hr_contract_allowance/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('gs_hr_contract_allowance.listing', {
#             'root': '/gs_hr_contract_allowance/gs_hr_contract_allowance',
#             'objects': http.request.env['gs_hr_contract_allowance.gs_hr_contract_allowance'].search([]),
#         })

#     @http.route('/gs_hr_contract_allowance/gs_hr_contract_allowance/objects/<model("gs_hr_contract_allowance.gs_hr_contract_allowance"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('gs_hr_contract_allowance.object', {
#             'object': obj
#         })
