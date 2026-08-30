import base64
import copy
import io
import logging

from odoo import models
from odoo.tools import pdf

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    _LETTERHEAD_ACTION_XMLIDS = (
        'invoice_company_letterhead.action_report_saleorder_letterhead',
        'invoice_company_letterhead.action_report_delivery_letterhead',
        'invoice_company_letterhead.action_report_invoice_letterhead',
        'invoice_company_letterhead.action_report_purchase_letterhead',
    )

    def _is_letterhead_report(self, report):
        actions = [
            self.env.ref(xmlid, raise_if_not_found=False)
            for xmlid in self._LETTERHEAD_ACTION_XMLIDS
        ]
        return bool(report and report in [action for action in actions if action])

    def _get_rendering_context(self, report, docids, data):
        values = super()._get_rendering_context(report, docids, data)
        values['company_letterhead_print'] = self._is_letterhead_report(report)
        return values

    def _company_for_record(self, report, record_id):
        record = self.env[report.model].browse(record_id).exists()
        if not record:
            return self.env.company
        return record.company_id.sudo() if 'company_id' in record._fields else self.env.company

    def _run_wkhtmltopdf(self, bodies, report_ref=False, header=None, footer=None,
                         landscape=False, specific_paperformat_args=None,
                         set_viewport_size=False):
        args = dict(specific_paperformat_args or {})
        if self.env.context.get('_company_letterhead_real_margins'):
            args.update({
                'data-report-margin-top': float(
                    self.env.context.get('_company_letterhead_margin_top', 0.0)
                ),
                'data-report-margin-bottom': float(
                    self.env.context.get('_company_letterhead_margin_bottom', 0.0)
                ),
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
        company = self._company_for_record(report, ids[0]) if ids else self.env.company

        if (self._is_letterhead_report(report) and ids
                and company.invoice_letterhead_enabled
                and company.invoice_letterhead_pdf
                and not self.env.context.get('_company_letterhead_real_margins')):
            return self.with_context(
                _company_letterhead_real_margins=True,
                _company_letterhead_margin_top=company.invoice_letterhead_top_offset or 0.0,
                _company_letterhead_margin_bottom=company.invoice_letterhead_bottom_offset or 0.0,
            )._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=ids)

        streams = super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=ids)
        if not self._is_letterhead_report(report):
            return streams

        for record_id, stream_info in streams.items():
            if not stream_info or not stream_info.get('stream') or not record_id:
                continue
            record_company = self._company_for_record(report, record_id)
            if (not record_company.invoice_letterhead_enabled
                    or not record_company.invoice_letterhead_pdf):
                continue
            try:
                letterhead_bytes = base64.b64decode(record_company.invoice_letterhead_pdf)
                merged = self._merge_report_with_letterhead(
                    stream_info['stream'].getvalue(), letterhead_bytes
                )
                stream_info['stream'].close()
                stream_info['stream'] = io.BytesIO(merged)
            except Exception:
                _logger.exception(
                    'Could not apply company letterhead to %s record %s',
                    report.model, record_id,
                )
        return streams

    @staticmethod
    def _merge_report_with_letterhead(report_bytes, letterhead_bytes):
        report_reader = pdf.PdfFileReader(io.BytesIO(report_bytes), strict=False)
        letterhead_reader = pdf.PdfFileReader(io.BytesIO(letterhead_bytes), strict=False)
        if not report_reader.getNumPages() or not letterhead_reader.getNumPages():
            return report_bytes

        writer = pdf.PdfFileWriter()
        for page_index in range(report_reader.getNumPages()):
            report_page = report_reader.getPage(page_index)
            background = copy.deepcopy(letterhead_reader.getPage(
                min(page_index, letterhead_reader.getNumPages() - 1)
            ))
            width = float(report_page.mediaBox.getWidth())
            height = float(report_page.mediaBox.getHeight())
            if (abs(float(background.mediaBox.getWidth()) - width) > 0.5
                    or abs(float(background.mediaBox.getHeight()) - height) > 0.5):
                if hasattr(background, 'scaleTo'):
                    background.scaleTo(width, height)
                else:
                    background.scale_to(width, height)
            if hasattr(background, 'mergePage'):
                background.mergePage(report_page)
            else:
                background.merge_page(report_page)
            writer.addPage(background)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
