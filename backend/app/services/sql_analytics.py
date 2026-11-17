"""Parameterized read-only analytics over the normalized SQLite store."""
from app.database.connection import initialize_database, connect


def _rows(sql, params=(), path=None):
    initialize_database(path)
    conn = connect(path, readonly=True)
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def water_consumption(path=None):
    rows = _rows("""SELECT SUM(consumption_million_gal) AS million_gallons,
        SUM(consumption_million_litres) AS million_litres,
        COUNT(consumption_million_gal) AS gallon_observations,
        COUNT(consumption_million_litres) AS litre_observations
        FROM water_metrics""", path=path)[0]
    has_data = rows["gallon_observations"] or rows["litre_observations"]
    return {"data": rows, "message": None if has_data else "No water consumption records with known units are available."}


def wue_by_location(path=None):
    rows = _rows("""SELECT l.place_name, l.country, AVG(w.wue_l_per_kwh) AS average_wue_l_per_kwh,
        COUNT(w.wue_l_per_kwh) AS observations FROM water_metrics w
        JOIN locations l ON l.location_id=w.location_id WHERE w.wue_l_per_kwh IS NOT NULL
        GROUP BY l.location_id ORDER BY average_wue_l_per_kwh""", path=path)
    return {"data": rows, "message": None if rows else "No WUE observations are available."}


def country_comparison(path=None):
    rows = _rows("""SELECT l.country, SUM(w.consumption_million_gal) AS million_gallons,
        SUM(w.consumption_million_litres) AS million_litres, COUNT(*) AS observations
        FROM water_metrics w JOIN locations l ON l.location_id=w.location_id
        WHERE l.country IS NOT NULL AND (w.consumption_million_gal IS NOT NULL OR w.consumption_million_litres IS NOT NULL)
        GROUP BY l.country ORDER BY l.country""", path=path)
    return {"data": rows, "message": None if rows else "No country-linked consumption records are available."}


def site_distribution(path=None):
    rows = _rows("""SELECT l.country, COUNT(DISTINCT l.location_id) AS site_labels
        FROM water_metrics w JOIN locations l ON l.location_id=w.location_id
        WHERE w.scope='site' AND l.country IS NOT NULL GROUP BY l.country ORDER BY site_labels DESC,l.country""", path=path)
    return {"data": rows, "message": None if rows else "No country-linked site labels are available."}


def monthly_trends(path=None):
    rows = _rows("""SELECT measurement_month, SUM(consumption_million_gal) AS million_gallons,
        SUM(consumption_million_litres) AS million_litres, COUNT(*) AS observations
        FROM water_metrics WHERE measurement_month IS NOT NULL
        AND (consumption_million_gal IS NOT NULL OR consumption_million_litres IS NOT NULL)
        GROUP BY measurement_month ORDER BY measurement_month""", path=path)
    return {"data": rows, "message": None if rows else "No monthly consumption records with an explicit month are available."}


def annual_trends(path=None):
    rows = _rows("""SELECT reporting_year, SUM(consumption_million_gal) AS million_gallons,
        SUM(consumption_million_litres) AS million_litres, COUNT(*) AS observations
        FROM water_metrics WHERE reporting_year IS NOT NULL
        AND (consumption_million_gal IS NOT NULL OR consumption_million_litres IS NOT NULL)
        GROUP BY reporting_year ORDER BY reporting_year""", path=path)
    return {"data": rows, "message": None if rows else "No annual consumption records are available."}


def climate_analysis(path=None):
    tables = {r["name"] for r in _rows("SELECT name FROM sqlite_master WHERE type='table'", path=path)}
    if "climate_metrics" not in tables:
        return {"data": [], "message": "No transformed dataset contains compatible climate measurements."}
    rows = _rows("""SELECT l.place_name, l.country, AVG(c.temperature) AS average_temperature,
        COUNT(c.temperature) AS observations FROM climate_metrics c JOIN locations l USING(location_id)
        WHERE c.temperature IS NOT NULL GROUP BY l.location_id ORDER BY l.place_name""", path=path)
    return {"data": rows, "message": None if rows else "No compatible climate measurements are available."}


def stress_analysis(path=None):
    tables = {r["name"] for r in _rows("SELECT name FROM sqlite_master WHERE type='table'", path=path)}
    if "water_stress" not in tables:
        return {"data": [], "message": "No transformed dataset contains water-stress assessments linked to locations."}
    rows = _rows("""SELECT l.place_name,l.country,s.assessment_year,s.water_stress_level,s.water_risk_score
        FROM water_stress s JOIN locations l USING(location_id) ORDER BY s.water_risk_score DESC""", path=path)
    return {"data": rows, "message": None if rows else "No water-stress assessments are available."}


def summary(path=None):
    initialize_database(path)
    conn = connect(path, readonly=True)
    try:
        counts = {row["name"]: conn.execute(f'SELECT COUNT(*) FROM "{row["name"]}"').fetchone()[0]
                  for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        dataset_counts = [dict(row) for row in conn.execute("SELECT dataset_id,dataset_name,source_filename,source_type,source_record_count,record_count,upload_date,processing_status FROM datasets ORDER BY loaded_at DESC")]
        quality_metrics = [dict(row) for row in conn.execute("SELECT quality_metric,SUM(issue_count) AS issue_count,COUNT(DISTINCT dataset_id) AS datasets FROM data_quality_logs GROUP BY quality_metric ORDER BY quality_metric")]
        load_totals = dict(conn.execute("SELECT COUNT(*) AS attempts,COALESCE(SUM(records_read),0) AS records_read,COALESCE(SUM(records_inserted),0) AS records_inserted,COALESCE(SUM(records_rejected),0) AS records_rejected,COALESCE(SUM(duplicate_records),0) AS duplicate_records,COALESCE(SUM(CASE WHEN load_status IN ('loaded','loaded_with_rejections') THEN 1 ELSE 0 END),0) AS successful_loads FROM load_history").fetchone())
    finally:
        conn.close()
    return {"table_counts": counts, "datasets": dataset_counts, "total_stored_water_records": counts.get("water_metrics", 0),
            "quality_metrics": quality_metrics, "load_totals": load_totals}


def validate_database(path=None):
    initialize_database(path)
    conn = connect(path, readonly=True)
    try:
        table_names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        required = {"datasets", "locations", "water_metrics", "load_history", "data_quality_logs"}
        missing = sorted(required - table_names)
        fk = [dict(row) for row in conn.execute("PRAGMA foreign_key_check")]
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        null_checks = {}
        for table, columns in {"datasets": ("dataset_id", "source_filename", "processing_status"),
                               "locations": ("place_name",),
                               "water_metrics": ("dataset_id", "location_id", "source_record_id")}.items():
            if table in table_names:
                null_checks[table] = {column: conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL').fetchone()[0] for column in columns}
        duplicate_keys = {"dataset_id": conn.execute("SELECT COUNT(*)-COUNT(DISTINCT dataset_id) FROM datasets").fetchone()[0],
                          "water_source_record": conn.execute("SELECT COUNT(*)-COUNT(DISTINCT dataset_id || ':' || source_record_id) FROM water_metrics").fetchone()[0]}
        primary_key_checks = {}
        for table in sorted(table_names):
            pk_columns = [r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")') if r["pk"]]
            if pk_columns:
                key_expr = ",".join(f'"{column}"' for column in pk_columns)
                duplicates = conn.execute(f'SELECT COUNT(*) FROM (SELECT {key_expr} FROM "{table}" GROUP BY {key_expr} HAVING COUNT(*) > 1)').fetchone()[0]
                primary_key_checks[table] = {"columns": pk_columns, "duplicate_groups": duplicates, "passed": duplicates == 0}
        count_reconciliation = [dict(row) for row in conn.execute("""SELECT d.dataset_id,d.source_record_count,d.record_count,
             (SELECT COUNT(*) FROM water_metrics w WHERE w.dataset_id=d.dataset_id) AS actual_records,
             (SELECT h.records_read FROM load_history h WHERE h.dataset_id=d.dataset_id
                AND h.load_status IN ('loaded','loaded_with_rejections') ORDER BY h.loaded_at DESC,h.load_id DESC LIMIT 1) AS latest_records_read,
             (SELECT h.records_rejected FROM load_history h WHERE h.dataset_id=d.dataset_id
                AND h.load_status IN ('loaded','loaded_with_rejections') ORDER BY h.loaded_at DESC,h.load_id DESC LIMIT 1) AS latest_records_rejected,
             (SELECT h.duplicate_records FROM load_history h WHERE h.dataset_id=d.dataset_id
                AND h.load_status IN ('loaded','loaded_with_rejections') ORDER BY h.loaded_at DESC,h.load_id DESC LIMIT 1) AS latest_duplicate_records
             FROM datasets d""")]
        mismatches = [r for r in count_reconciliation if r["record_count"] != r["actual_records"] or
            (r["latest_records_read"] is not None and
             r["latest_records_read"] != r["record_count"] + r["latest_records_rejected"] + r["latest_duplicate_records"])]
    finally:
        conn.close()
    ok = not missing and not fk and integrity == ["ok"] and not any(any(v for v in row.values()) for row in null_checks.values()) and not any(duplicate_keys.values()) and not any(not item["passed"] for item in primary_key_checks.values()) and not mismatches
    return {"valid": ok, "tables_present": sorted(table_names), "missing_tables": missing,
            "foreign_key_violations": fk, "integrity_check": integrity, "required_null_counts": null_checks,
            "duplicate_key_counts": duplicate_keys, "primary_key_checks": primary_key_checks,
            "count_reconciliation": count_reconciliation,
            "count_mismatches": mismatches}
