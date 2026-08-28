import base64
import copy
import io
import logging

from odoo import models
from odoo.tools import pdf

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _is_letterhead_report(self, report):
        xmlids = (
            'invoice_company_letterhead.action_report_invoice_letterhead',
            'invoice_company_letterhead.action_report_invoice_design_preview',
        )
        actions = [self.env.ref(xmlid, raise_if_not_found=False) for xmlid in xmlids]
        return bool(report and report in [action for action in actions if action])

    def _get_rendering_context(self, report, docids, data):
        values = super()._get_rendering_context(report, docids, data)
        values['company_letterhead_print'] = self._is_letterhead_report(report)
        return values

    def _design_from_request(self, report, data, res_ids):
        design_id = (data or {}).get('design_id') or self.env.context.get('letterhead_design_id')
        design = self.env['invoice.letterhead.design'].browse(design_id).exists() if design_id else False
        if design:
            return design
        if report.model == 'account.move' and res_ids:
            move = self.env['account.move'].browse(res_ids[:1]).exists()
            if move:
                return self.env['invoice.letterhead.design'].search([
                    ('company_id', '=', move.company_id.id),
                    ('active', '=', True), ('is_default', '=', True),
                ], limit=1)
        if report.model == 'invoice.print.wizard' and res_ids:
            wizard = self.env['invoice.print.wizard'].browse(res_ids[:1]).exists()
            return wizard.design_id if wizard else False
        return False

    def _run_wkhtmltopdf(self, bodies, report_ref=False, header=None, footer=None,
                         landscape=False, specific_paperformat_args=None,
                         set_viewport_size=False):
        args = dict(specific_paperformat_args or {})
        if self.env.context.get('_company_letterhead_real_margins'):
            args.update({
                'data-report-margin-top': float(self.env.context.get('_company_letterhead_margin_top', 0.0)),
                'data-report-margin-bottom': float(self.env.context.get('_company_letterhead_margin_bottom', 0.0)),
                'data-report-header-spacing': 0,
            })
        return super()._run_wkhtmltopdf(
            bodies, report_ref=report_ref, header=header, footer=footer,
            landscape=landscape, specific_paperformat_args=args,
            set_viewport_size=set_viewport_size,
        )

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        report = self._get_report(report_ref)
        ids = [res_ids] if isinstance(res_ids, int) else list(res_ids or [])
        design = self._design_from_request(report, data, ids)
        if (self._is_letterhead_report(report) and design and design.letterhead_pdf
                and not self.env.context.get('_company_letterhead_real_margins')):
            return self.with_context(
                _company_letterhead_real_margins=True,
                _company_letterhead_margin_top=design.top_offset or 0.0,
                _company_letterhead_margin_bottom=design.bottom_offset or 0.0,
                letterhead_design_id=design.id,
            )._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=ids)

        streams = super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=ids)
        if not self._is_letterhead_report(report) or not design or not design.letterhead_pdf:
            return streams

        letterhead_bytes = base64.b64decode(design.letterhead_pdf)
        for stream_info in streams.values():
            if not stream_info or not stream_info.get('stream'):
                continue
            try:
                merged = self._merge_invoice_with_letterhead(
                    stream_info['stream'].getvalue(), letterhead_bytes
                )
                stream_info['stream'].close()
                stream_info['stream'] = io.BytesIO(merged)
            except Exception:
                _logger.exception('Could not apply invoice letterhead design %s', design.display_name)
        return streams

    @staticmethod
    def _merge_invoice_with_letterhead(invoice_bytes, letterhead_bytes):
        invoice_reader = pdf.PdfFileReader(io.BytesIO(invoice_bytes), strict=False)
        letterhead_reader = pdf.PdfFileReader(io.BytesIO(letterhead_bytes), strict=False)
        if not invoice_reader.getNumPages() or not letterhead_reader.getNumPages():
            return invoice_bytes
        writer = pdf.PdfFileWriter()
        for page_index in range(invoice_reader.getNumPages()):
            invoice_page = invoice_reader.getPage(page_index)
            background = copy.deepcopy(letterhead_reader.getPage(
                min(page_index, letterhead_reader.getNumPages() - 1)
            ))
            width, height = float(invoice_page.mediaBox.getWidth()), float(invoice_page.mediaBox.getHeight())
            if (abs(float(background.mediaBox.getWidth()) - width) > 0.5
                    or abs(float(background.mediaBox.getHeight()) - height) > 0.5):
                if hasattr(background, 'scaleTo'):
                    background.scaleTo(width, height)
                else:
                    background.scale_to(width, height)
            if hasattr(background, 'mergePage'):
                background.mergePage(invoice_page)
            else:
                background.merge_page(invoice_page)
            writer.addPage(background)
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
