import base64
import copy
import io
import logging

from odoo import models
from odoo.tools import pdf

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _is_company_letterhead_action(self, report):
        try:
            action = self.env.ref(
                'invoice_company_letterhead.action_report_invoice_letterhead',
                raise_if_not_found=False,
            )
            return bool(action and report and report.id == action.id)
        except Exception:
            return False

    def _get_rendering_context(self, report, docids, data):
        values = super()._get_rendering_context(report, docids, data)
        values['company_letterhead_print'] = self._is_company_letterhead_action(report)
        return values

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        report = self._get_report(report_ref)
        streams = super()._render_qweb_pdf_prepare_streams(
            report_ref, data, res_ids=res_ids
        )

        # Absolutely no change to Odoo's normal Print > PDF action.
        if not self._is_company_letterhead_action(report) or not res_ids:
            return streams
        if report.model != 'account.move':
            return streams

        moves = self.env['account.move'].browse(res_ids).exists()
        for move in moves:
            if move.move_type not in ('out_invoice', 'out_refund', 'out_receipt'):
                continue

            company = move.company_id.sudo()
            if not company.invoice_letterhead_enabled or not company.invoice_letterhead_pdf:
                continue

            stream_info = streams.get(move.id)
            if not stream_info or not stream_info.get('stream'):
                continue

            try:
                invoice_bytes = stream_info['stream'].getvalue()
                letterhead_bytes = base64.b64decode(company.invoice_letterhead_pdf)
                merged = self._merge_invoice_with_letterhead(invoice_bytes, letterhead_bytes)

                try:
                    stream_info['stream'].close()
                except Exception:
                    pass
                stream_info['stream'] = io.BytesIO(merged)
            except Exception:
                _logger.exception(
                    'Could not apply PDF letterhead for company %s on invoice %s',
                    company.display_name, move.display_name
                )

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
            bg_index = min(page_index, letterhead_reader.getNumPages() - 1)
            background = copy.deepcopy(letterhead_reader.getPage(bg_index))

            iw = float(invoice_page.mediaBox.getWidth())
            ih = float(invoice_page.mediaBox.getHeight())
            bw = float(background.mediaBox.getWidth())
            bh = float(background.mediaBox.getHeight())

            # Only the stationery is fitted to the invoice paper.
            # The invoice content is NEVER scaled, preserving table/font/QR dimensions.
            if abs(bw - iw) > 0.5 or abs(bh - ih) > 0.5:
                if hasattr(background, 'scaleTo'):
                    background.scaleTo(iw, ih)
                elif hasattr(background, 'scale_to'):
                    background.scale_to(iw, ih)

            if hasattr(background, 'mergePage'):
                background.mergePage(invoice_page)
            else:
                background.merge_page(invoice_page)

            writer.addPage(background)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
