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
        """Return True only for our additional Print menu action."""
        try:
            letterhead_action = self.env.ref(
                'invoice_company_letterhead.action_report_invoice_letterhead',
                raise_if_not_found=False,
            )
            return bool(letterhead_action and report and report.id == letterhead_action.id)
        except Exception:
            return False

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        report = self._get_report(report_ref)
        is_letterhead_print = self._is_company_letterhead_action(report)

        # The context flag is used only while rendering our extra report action. It lets
        # the inherited web.external_layout remove Odoo's visual header/footer while
        # preserving the original invoice document body.
        render_self = self.with_context(company_letterhead_print=True) if is_letterhead_print else self
        collected_streams = super(IrActionsReport, render_self)._render_qweb_pdf_prepare_streams(
            report_ref,
            data,
            res_ids=res_ids,
        )

        # IMPORTANT: the normal Odoo invoice print action returns exactly what Odoo made.
        if not is_letterhead_print or not res_ids:
            return collected_streams

        if report.model != 'account.move':
            return collected_streams

        moves = self.env['account.move'].browse(res_ids).exists()
        for move in moves:
            if move.move_type not in ('out_invoice', 'out_refund', 'out_receipt'):
                continue

            company = move.company_id.sudo()
            if not company.invoice_letterhead_enabled or not company.invoice_letterhead_pdf:
                # If no company letterhead is configured, keep the generated invoice PDF.
                continue

            stream_info = collected_streams.get(move.id)
            if not stream_info or not stream_info.get('stream'):
                continue

            try:
                invoice_bytes = stream_info['stream'].getvalue()
                letterhead_bytes = base64.b64decode(company.invoice_letterhead_pdf)
                merged_bytes = self._merge_invoice_with_letterhead(invoice_bytes, letterhead_bytes)

                try:
                    stream_info['stream'].close()
                except Exception:
                    pass
                stream_info['stream'] = io.BytesIO(merged_bytes)
            except Exception:
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

            # One-page letterhead repeats on every invoice page. With a multi-page PDF,
            # corresponding pages are used and the final letterhead page is then reused.
            bg_index = min(page_index, letterhead_count - 1)
            background_page = copy.deepcopy(letterhead_reader.getPage(bg_index))

            invoice_width = float(invoice_page.mediaBox.getWidth())
            invoice_height = float(invoice_page.mediaBox.getHeight())
            bg_width = float(background_page.mediaBox.getWidth())
            bg_height = float(background_page.mediaBox.getHeight())

            # Scale ONLY the background to the invoice paper size. Never scale the invoice
            # page itself, which is what keeps the Odoo invoice body at its normal size.
            if abs(bg_width - invoice_width) > 0.5 or abs(bg_height - invoice_height) > 0.5:
                if hasattr(background_page, 'scaleTo'):
                    background_page.scaleTo(invoice_width, invoice_height)
                elif hasattr(background_page, 'scale_to'):
                    background_page.scale_to(invoice_width, invoice_height)

            if hasattr(background_page, 'mergePage'):
                background_page.mergePage(invoice_page)
            else:
                background_page.merge_page(invoice_page)

            writer.addPage(background_page)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
