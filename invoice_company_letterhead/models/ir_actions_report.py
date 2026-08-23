import base64
import copy
import io
import logging

from odoo import models
from odoo.tools import pdf

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        """Render normally, then put the generated invoice PDF on top of the company's PDF letterhead.

        Doing the merge after QWeb/wkhtmltopdf makes this independent from the exact Saudi/custom invoice
        template and from the company's selected Odoo external report layout.
        """
        collected_streams = super()._render_qweb_pdf_prepare_streams(
            report_ref, data, res_ids=res_ids
        )

        if not collected_streams or not res_ids:
            return collected_streams

        report = self._get_report(report_ref)
        if report.model != 'account.move':
            return collected_streams

        moves = self.env['account.move'].browse(res_ids).exists()
        for move in moves:
            # Customer invoices / credit notes / receipts only.
            if move.move_type not in ('out_invoice', 'out_refund', 'out_receipt'):
                continue

            company = move.company_id.sudo()
            if not company.invoice_letterhead_enabled or not company.invoice_letterhead_pdf:
                continue

            stream_info = collected_streams.get(move.id)
            if not stream_info or not stream_info.get('stream'):
                continue

            try:
                invoice_bytes = stream_info['stream'].getvalue()
                letterhead_bytes = base64.b64decode(company.invoice_letterhead_pdf)
                merged_bytes = self._merge_invoice_with_letterhead(
                    invoice_bytes,
                    letterhead_bytes,
                )
                try:
                    stream_info['stream'].close()
                except Exception:
                    pass
                stream_info['stream'] = io.BytesIO(merged_bytes)
            except Exception:
                # Never make invoice printing unusable because of a malformed letterhead.
                # The original generated invoice stays available in the stream.
                _logger.exception(
                    'Could not apply invoice letterhead for company %s on invoice %s',
                    company.display_name,
                    move.display_name,
                )

        return collected_streams

    @staticmethod
    def _merge_invoice_with_letterhead(invoice_bytes, letterhead_bytes):
        invoice_reader = pdf.PdfFileReader(io.BytesIO(invoice_bytes), strict=False)
        letterhead_reader = pdf.PdfFileReader(io.BytesIO(letterhead_bytes), strict=False)

        invoice_count = invoice_reader.getNumPages()
        letterhead_count = letterhead_reader.getNumPages()
        if not invoice_count or not letterhead_count:
            return invoice_bytes

        writer = pdf.PdfFileWriter()

        for page_index in range(invoice_count):
            invoice_page = invoice_reader.getPage(page_index)

            # One-page letterhead => repeat it. Multi-page letterhead => first page for first
            # invoice page, then use the corresponding page and keep reusing the last page.
            bg_index = min(page_index, letterhead_count - 1)
            background_page = copy.deepcopy(letterhead_reader.getPage(bg_index))

            invoice_width = float(invoice_page.mediaBox.getWidth())
            invoice_height = float(invoice_page.mediaBox.getHeight())
            bg_width = float(background_page.mediaBox.getWidth())
            bg_height = float(background_page.mediaBox.getHeight())

            if abs(bg_width - invoice_width) > 0.5 or abs(bg_height - invoice_height) > 0.5:
                if hasattr(background_page, 'scaleTo'):
                    background_page.scaleTo(invoice_width, invoice_height)
                elif hasattr(background_page, 'scale_to'):
                    background_page.scale_to(invoice_width, invoice_height)

            # Background first, invoice content second.
            if hasattr(background_page, 'mergePage'):
                background_page.mergePage(invoice_page)
            else:
                background_page.merge_page(invoice_page)

            writer.addPage(background_page)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
