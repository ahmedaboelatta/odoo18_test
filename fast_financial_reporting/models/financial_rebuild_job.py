import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class FastFinancialRebuildJob(models.Model):
    _name = "fast.financial.rebuild.job"
    _description = "Fast Financial Reporting Rebuild Job"
    _order = "create_date desc"

    name = fields.Char(required=True, readonly=True)
    company_id = fields.Many2one(
        "res.company", required=True, index=True,
        default=lambda self: self.env.company, ondelete="cascade", readonly=True,
    )
    date_from = fields.Date(required=True, readonly=True)
    date_to = fields.Date(required=True, readonly=True)
    next_date = fields.Date(readonly=True)
    current_date = fields.Date(readonly=True)
    state = fields.Selection(
        [
            ("queued", "Queued"),
            ("running", "Running"),
            ("done", "Done"),
            ("error", "Error"),
            ("cancelled", "Cancelled"),
        ],
        required=True, default="queued", index=True, readonly=True,
    )
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    processed_days = fields.Integer(readonly=True, default=0)
    total_days = fields.Integer(readonly=True)
    source_line_count = fields.Integer(readonly=True, default=0)
    daily_rows = fields.Integer(readonly=True, default=0)
    monthly_rows = fields.Integer(readonly=True, default=0)
    last_error = fields.Text(readonly=True)

    def action_cancel(self):
        for job in self.filtered(lambda j: j.state in ("queued", "running")):
            job.write({"state": "cancelled", "finished_at": fields.Datetime.now()})
        return True

    def action_process_next_batch(self):
        self.ensure_one()
        if self.state in ("queued", "running"):
            config = self.env["fast.financial.report.config"].sudo().get_for_company(self.company_id)
            self._process_batch(max_days=config.days_per_cron or 1)
        return True

    @api.model
    def _cron_process_jobs(self):
        job = self.search(
            [("state", "in", ("queued", "running"))],
            order="create_date asc",
            limit=1,
        )
        if job:
            config = self.env["fast.financial.report.config"].sudo().get_for_company(job.company_id)
            job._process_batch(max_days=config.days_per_cron or 1)

    def _process_batch(self, max_days=1):
        self.ensure_one()
        if self.state not in ("queued", "running"):
            return True

        sync_state = self.env["fast.financial.sync.state"].sudo().get_or_create_for_company(self.company_id)

        if not self.started_at:
            self.write({
                "state": "running",
                "started_at": fields.Datetime.now(),
                "next_date": self.next_date or self.date_from,
            })

        sync_state.write({
            "state": "running",
            "last_error": False,
            "last_rebuild_from": self.date_from,
            "last_rebuild_to": self.date_to,
        })

        current = self.next_date or self.date_from
        done_now = 0

        try:
            while current <= self.date_to and done_now < max_days:
                stats = self._rebuild_one_day(current)
                self.write({
                    "current_date": current,
                    "next_date": current + timedelta(days=1),
                    "processed_days": self.processed_days + 1,
                    "source_line_count": self.source_line_count + stats["source_line_count"],
                    "daily_rows": self.daily_rows + stats["daily_rows"],
                })
                self.env.cr.commit()
                current = current + timedelta(days=1)
                done_now += 1

            if current > self.date_to:
                monthly_rows = self._rebuild_monthly_for_period()
                self.write({
                    "state": "done",
                    "finished_at": fields.Datetime.now(),
                    "monthly_rows": monthly_rows,
                    "next_date": False,
                })
                sync_state.write({
                    "state": "ready",
                    "last_sync_at": fields.Datetime.now(),
                    "last_error": False,
                })
                self.env.cr.commit()

        except Exception as exc:
            self.env.cr.rollback()
            _logger.exception("Fast Financial Reporting rebuild failed for job %s", self.id)
            self.write({
                "state": "error",
                "finished_at": fields.Datetime.now(),
                "last_error": str(exc),
            })
            sync_state.write({"state": "error", "last_error": str(exc)})
            self.env.cr.commit()

        return True

    def _rebuild_one_day(self, target_date):
        self.ensure_one()
        cr = self.env.cr
        company_id = self.company_id.id
        uid = self.env.uid

        cr.execute("""
            SELECT COUNT(*)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE aml.company_id = %s
              AND aml.date = %s
              AND am.state = 'posted'
        """, [company_id, target_date])
        source_line_count = cr.fetchone()[0] or 0

        cr.execute("""
            DELETE FROM fast_financial_daily_summary
            WHERE company_id = %s AND date = %s
        """, [company_id, target_date])

        # Consolidated total: each posted journal item contributes exactly once.
        cr.execute("""
            INSERT INTO fast_financial_daily_summary
                (date, company_id, account_id, scope, analytic_account_id, analytic_key,
                 debit, credit, balance, source_line_count,
                 create_uid, create_date, write_uid, write_date)
            SELECT
                aml.date, aml.company_id, aml.account_id,
                'total', NULL, 'TOTAL',
                SUM(aml.debit), SUM(aml.credit), SUM(aml.balance), COUNT(*),
                %s, NOW(), %s, NOW()
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE aml.company_id = %s
              AND aml.date = %s
              AND am.state = 'posted'
            GROUP BY aml.date, aml.company_id, aml.account_id
        """, [uid, uid, company_id, target_date])

        # Lines without analytic distribution.
        cr.execute("""
            INSERT INTO fast_financial_daily_summary
                (date, company_id, account_id, scope, analytic_account_id, analytic_key,
                 debit, credit, balance, source_line_count,
                 create_uid, create_date, write_uid, write_date)
            SELECT
                aml.date, aml.company_id, aml.account_id,
                'none', NULL, 'NONE',
                SUM(aml.debit), SUM(aml.credit), SUM(aml.balance), COUNT(*),
                %s, NOW(), %s, NOW()
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE aml.company_id = %s
              AND aml.date = %s
              AND am.state = 'posted'
              AND (
                    aml.analytic_distribution IS NULL
                    OR aml.analytic_distribution = '{}'::jsonb
              )
            GROUP BY aml.date, aml.company_id, aml.account_id
        """, [uid, uid, company_id, target_date])

        # Analytic rows, apportioned by Odoo's percentage distribution.
        # Comma-separated analytic ids are expanded independently.
        cr.execute("""
            INSERT INTO fast_financial_daily_summary
                (date, company_id, account_id, scope, analytic_account_id, analytic_key,
                 debit, credit, balance, source_line_count,
                 create_uid, create_date, write_uid, write_date)
            SELECT
                x.date, x.company_id, x.account_id,
                'analytic', x.analytic_account_id,
                'AA:' || x.analytic_account_id::text,
                SUM(x.debit_part), SUM(x.credit_part), SUM(x.balance_part),
                COUNT(DISTINCT x.aml_id),
                %s, NOW(), %s, NOW()
            FROM (
                SELECT
                    aml.id AS aml_id,
                    aml.date,
                    aml.company_id,
                    aml.account_id,
                    aa.id AS analytic_account_id,
                    aml.debit * (j.dist_value::numeric / 100.0) AS debit_part,
                    aml.credit * (j.dist_value::numeric / 100.0) AS credit_part,
                    aml.balance * (j.dist_value::numeric / 100.0) AS balance_part
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                CROSS JOIN LATERAL jsonb_each_text(aml.analytic_distribution)
                    AS j(dist_key, dist_value)
                CROSS JOIN LATERAL regexp_split_to_table(j.dist_key, ',')
                    AS split_id
                JOIN account_analytic_account aa
                  ON aa.id = trim(split_id)::integer
                WHERE aml.company_id = %s
                  AND aml.date = %s
                  AND am.state = 'posted'
                  AND aml.analytic_distribution IS NOT NULL
                  AND aml.analytic_distribution <> '{}'::jsonb
            ) x
            GROUP BY x.date, x.company_id, x.account_id, x.analytic_account_id
        """, [uid, uid, company_id, target_date])

        cr.execute("""
            SELECT COUNT(*)
            FROM fast_financial_daily_summary
            WHERE company_id = %s AND date = %s
        """, [company_id, target_date])
        daily_rows = cr.fetchone()[0] or 0

        return {
            "source_line_count": source_line_count,
            "daily_rows": daily_rows,
        }

    def _rebuild_monthly_for_period(self):
        self.ensure_one()
        cr = self.env.cr
        uid = self.env.uid
        company_id = self.company_id.id

        cr.execute("""
            SELECT date_trunc('month', %s::date)::date,
                   date_trunc('month', %s::date)::date
        """, [self.date_from, self.date_to])
        first_month, last_month = cr.fetchone()

        cr.execute("""
            DELETE FROM fast_financial_monthly_summary
            WHERE company_id = %s
              AND month_start BETWEEN %s AND %s
        """, [company_id, first_month, last_month])

        cr.execute("""
            INSERT INTO fast_financial_monthly_summary
                (month_start, company_id, account_id, scope, analytic_account_id, analytic_key,
                 debit, credit, balance, source_line_count,
                 create_uid, create_date, write_uid, write_date)
            SELECT
                date_trunc('month', d.date)::date,
                d.company_id, d.account_id, d.scope,
                d.analytic_account_id, d.analytic_key,
                SUM(d.debit), SUM(d.credit), SUM(d.balance),
                SUM(d.source_line_count),
                %s, NOW(), %s, NOW()
            FROM fast_financial_daily_summary d
            WHERE d.company_id = %s
              AND date_trunc('month', d.date)::date BETWEEN %s AND %s
            GROUP BY
                date_trunc('month', d.date)::date,
                d.company_id, d.account_id, d.scope,
                d.analytic_account_id, d.analytic_key
        """, [uid, uid, company_id, first_month, last_month])

        cr.execute("""
            SELECT COUNT(*)
            FROM fast_financial_monthly_summary
            WHERE company_id = %s
              AND month_start BETWEEN %s AND %s
        """, [company_id, first_month, last_month])
        return cr.fetchone()[0] or 0
