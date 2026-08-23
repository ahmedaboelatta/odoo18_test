def migrate(cr, version):
    """Normalize stored campaign rates to percentage points (0..100)."""
    cr.execute("""
        UPDATE bird_bulk_send
           SET submission_rate = CASE WHEN total_count > 0 THEN submitted_count * 100.0 / total_count ELSE 0 END,
               delivery_rate   = CASE WHEN total_count > 0 THEN delivered_count * 100.0 / total_count ELSE 0 END,
               failure_rate    = CASE WHEN total_count > 0 THEN failed_count * 100.0 / total_count ELSE 0 END
    """)
