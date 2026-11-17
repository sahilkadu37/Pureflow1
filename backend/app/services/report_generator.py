"""Build evidence-based PureFlow reports and safe PDF/CSV/JSON exports."""
import csv
from datetime import datetime, timezone
import io
import json
import math
import re
import shutil
import textwrap
import unicodedata
import uuid
from pathlib import Path

from app.database.connection import connect, initialize_database
from app.services.recommendation_engine import generate_recommendations
from app.services.sql_analytics import climate_analysis, stress_analysis, validate_database

REPORT_TYPES = {"comprehensive", "water", "sustainability"}
REPORT_ID = re.compile(r"^[a-f0-9]{32}$")


def _filters(dataset_ids=None, start_date=None, end_date=None, location=None):
    return {"dataset_ids": sorted(set(dataset_ids or [])), "start_date": start_date or None,
            "end_date": end_date or None, "location": (location or "").strip() or None}


def _where(filters, alias="w"):
    clauses, params = [], []
    if filters["dataset_ids"]:
        clauses.append(f"{alias}.dataset_id IN ({','.join('?' for _ in filters['dataset_ids'])})")
        params.extend(filters["dataset_ids"])
    period_year = f"COALESCE(CAST({alias}.reporting_year AS TEXT), substr({alias}.measurement_month,1,4))"
    if filters["start_date"]:
        clauses.append(f"{period_year} >= ?")
        params.append(filters["start_date"][:4])
    if filters["end_date"]:
        clauses.append(f"{period_year} <= ?")
        params.append(filters["end_date"][:4])
    if filters["location"]:
        clauses.append("(instr(lower(l.place_name),lower(?)) > 0 OR instr(lower(COALESCE(l.country,'')),lower(?)) > 0)")
        params.extend([filters["location"], filters["location"]])
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def _source_details(transformed_dir, filename):
    path = (Path(transformed_dir).resolve() / Path(filename).name).resolve()
    if path.parent != Path(transformed_dir).resolve() or not path.is_file():
        return []
    sources = {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                title, url = row.get("source_title", "").strip(), row.get("source_url", "").strip()
                if title or url:
                    sources[(title, url)] = {"title": title or None, "url": url or None}
                if len(sources) >= 30:
                    break
    except (OSError, UnicodeError, csv.Error):
        return []
    return list(sources.values())


def _quality_report(quality_dir, dataset_id):
    root = Path(quality_dir).resolve()
    path = (root / f"{dataset_id}_quality.json").resolve()
    if path.parent != root:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"summary": data.get("summary"), "validation": data.get("validation"),
                "cleaning_history": data.get("cleaning_history", [])}
    except (OSError, json.JSONDecodeError):
        return None


def _transform_history(transformed_dir, dataset_ids):
    try:
        history = json.loads((Path(transformed_dir) / "transformation_history.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [{"job_id": item.get("job_id"), "operation": item.get("operation"),
             "generated_at": item.get("generated_at"), "dataset_ids": item.get("dataset_ids", []),
             "output_filename": item.get("output_filename"), "output_rows": item.get("output_rows"),
             "validation": item.get("validation")}
            for item in history if set(item.get("dataset_ids", [])) & set(dataset_ids)]


def build_report(db_path=None, *, dataset_ids=None, start_date=None, end_date=None, location=None,
                 quality_dir=None, transformed_dir=None, report_type="comprehensive"):
    if report_type not in REPORT_TYPES:
        raise ValueError(f"report_type must be one of: {', '.join(sorted(REPORT_TYPES))}")
    filters = _filters(dataset_ids, start_date, end_date, location)
    initialize_database(db_path)
    conn = connect(db_path, readonly=True)
    try:
        all_datasets = [dict(row) for row in conn.execute("SELECT dataset_id,dataset_name,source_filename,transformed_filename,source_type,source_record_count,record_count,upload_date,loaded_at,processing_status FROM datasets ORDER BY dataset_name")]
        known = {row["dataset_id"] for row in all_datasets}
        unknown = set(filters["dataset_ids"]) - known
        if unknown:
            raise ValueError(f"Selected dataset(s) are not loaded in the database: {', '.join(sorted(unknown))}")
        selected = [d for d in all_datasets if not filters["dataset_ids"] or d["dataset_id"] in filters["dataset_ids"]]
        if filters["dataset_ids"]:
            filters["dataset_ids"] = [d["dataset_id"] for d in selected]
        where, params = _where(filters)
        join = " FROM water_metrics w JOIN locations l ON l.location_id=w.location_id"
        totals = dict(conn.execute("SELECT COUNT(*) AS records, COUNT(w.consumption_million_gal) AS gallon_observations, COUNT(w.consumption_million_litres) AS litre_observations, COUNT(w.wue_l_per_kwh) AS wue_observations, SUM(w.consumption_million_gal) AS million_gallons, SUM(w.consumption_million_litres) AS million_litres, COUNT(CASE WHEN w.consumption_million_gal IS NOT NULL OR w.consumption_million_litres IS NOT NULL THEN 1 END) AS records_with_consumption, COUNT(CASE WHEN l.country IS NOT NULL THEN 1 END) AS records_with_country FROM water_metrics w JOIN locations l ON l.location_id=w.location_id" + where, params).fetchone())
        wue_rows = [dict(row) for row in conn.execute("SELECT w.wue_l_per_kwh AS value,l.place_name,l.country,w.measurement_period,w.publisher,w.scope,w.dataset_id FROM water_metrics w JOIN locations l ON l.location_id=w.location_id WHERE w.wue_l_per_kwh IS NOT NULL" + (" AND " + where[7:] if where else "") + " ORDER BY w.wue_l_per_kwh", params)]
        # The shared WHERE builder starts with WHERE; strip it above when appending to the WUE predicate.
        wue_filter = (where + " AND w.wue_l_per_kwh IS NOT NULL") if where else " WHERE w.wue_l_per_kwh IS NOT NULL"
        location_sql = ("SELECT l.place_name,l.country,AVG(w.wue_l_per_kwh) AS average_wue_l_per_kwh,"
                        "COUNT(w.wue_l_per_kwh) AS observations FROM water_metrics w "
                        "JOIN locations l ON l.location_id=w.location_id" + wue_filter +
                        " GROUP BY l.location_id ORDER BY average_wue_l_per_kwh")
        locations = [dict(row) for row in conn.execute(location_sql, params)]
        annual_where = where
        annual = [dict(row) for row in conn.execute("SELECT w.reporting_year,SUM(w.consumption_million_gal) AS million_gallons,SUM(w.consumption_million_litres) AS million_litres,COUNT(*) AS observations FROM water_metrics w JOIN locations l ON l.location_id=w.location_id" + annual_where + (" AND " if annual_where else " WHERE ") + "w.reporting_year IS NOT NULL AND (w.consumption_million_gal IS NOT NULL OR w.consumption_million_litres IS NOT NULL) GROUP BY w.reporting_year ORDER BY w.reporting_year", params)]
        countries = [dict(row) for row in conn.execute("SELECT l.country,SUM(w.consumption_million_gal) AS million_gallons,SUM(w.consumption_million_litres) AS million_litres,COUNT(*) AS observations FROM water_metrics w JOIN locations l ON l.location_id=w.location_id" + where + (" AND " if where else " WHERE ") + "l.country IS NOT NULL AND (w.consumption_million_gal IS NOT NULL OR w.consumption_million_litres IS NOT NULL) GROUP BY l.country ORDER BY l.country", params)]
        monthly = [dict(row) for row in conn.execute("SELECT w.measurement_month,SUM(w.consumption_million_gal) AS million_gallons,SUM(w.consumption_million_litres) AS million_litres,COUNT(*) AS observations FROM water_metrics w JOIN locations l ON l.location_id=w.location_id" + where + (" AND " if where else " WHERE ") + "w.measurement_month IS NOT NULL AND (w.consumption_million_gal IS NOT NULL OR w.consumption_million_litres IS NOT NULL) GROUP BY w.measurement_month ORDER BY w.measurement_month", params)]
        quality_rows = []
        for dataset in selected:
            quality_rows.extend(dict(row) for row in conn.execute("SELECT quality_metric,issue_count,report_date,details FROM data_quality_logs WHERE dataset_id=? ORDER BY report_date", (dataset["dataset_id"],)))
        latest_loads = []
        for dataset in selected:
            row = conn.execute("SELECT records_read,records_inserted,records_rejected,duplicate_records,loaded_at,load_status,message FROM load_history WHERE dataset_id=? ORDER BY loaded_at DESC,load_id DESC LIMIT 1", (dataset["dataset_id"],)).fetchone()
            if row:
                latest_loads.append({"dataset_id": dataset["dataset_id"], **dict(row)})
        table_counts = {row["name"]: conn.execute(f'SELECT COUNT(*) FROM "{row["name"]}"').fetchone()[0]
                        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        schema = {}
        for table in table_counts:
            schema[table] = [{"name": row["name"], "type": row["type"], "primary_key": bool(row["pk"]), "required": bool(row["notnull"])} for row in conn.execute(f'PRAGMA table_info("{table}")')]
    finally:
        conn.close()

    total_records = totals["records"] or 0
    coverage = {"total_records": total_records, "records_with_country": totals["records_with_country"] or 0,
                "records_without_country": total_records - (totals["records_with_country"] or 0),
                "records_with_consumption": totals["records_with_consumption"] or 0,
                "records_without_consumption": total_records - (totals["records_with_consumption"] or 0),
                "wue_observations": totals["wue_observations"] or 0}
    water = {key: totals[key] for key in ("records", "million_gallons", "million_litres", "gallon_observations", "litre_observations", "records_with_consumption")}
    values = [row["value"] for row in wue_rows]
    wue = {"observations": len(values), "average_l_per_kwh": sum(values) / len(values) if values else None,
           "median_l_per_kwh": _median(values), "minimum_l_per_kwh": min(values) if values else None,
           "maximum_l_per_kwh": max(values) if values else None, "by_location": locations, "values": wue_rows}
    # Reuse the established services for the unfiltered climate/stress checks. Their actual tables are absent in the current store.
    climate = climate_analysis(db_path)
    stress = stress_analysis(db_path)
    quality_reports = [{"dataset_id": d["dataset_id"], **(_quality_report(quality_dir, d["dataset_id"]) or {"summary": None, "validation": None, "cleaning_history": []})} for d in selected] if quality_dir else []
    transformations = _transform_history(transformed_dir, [d["dataset_id"] for d in selected]) if transformed_dir else []
    sources = [{"dataset_id": d["dataset_id"], "source_filename": d["source_filename"], "source_type": d["source_type"],
                "sources": _source_details(transformed_dir, d["transformed_filename"]) if transformed_dir else []} for d in selected]
    validation = validate_database(db_path)
    evidence = {"water_consumption": water, "wue": wue, "coverage": coverage}
    recommendations = generate_recommendations(evidence)
    findings = _findings(water, wue, countries, coverage, climate, stress)
    missing_context = []
    if not climate["data"]:
        missing_context.append("No compatible climate measurements are stored.")
    if not stress["data"]:
        missing_context.append("No linked water-stress assessments are stored.")
    readiness = {"indicator_available": False,
                 "status": "data_readiness_assessment_only",
                 "message": "Available evidence is not sufficient for a comparable sustainability score. No score is calculated.",
                 "variables_assessed": [
                     {"metric": "Reported water consumption", "available": bool(water["gallon_observations"] or water["litre_observations"]), "coverage": "Reported volumes retain their source units."},
                     {"metric": "WUE", "available": bool(wue["observations"]), "coverage": f"{wue['observations']} observations in L/kWh."},
                     {"metric": "Climate", "available": bool(climate["data"]), "coverage": climate["message"]},
                     {"metric": "Water stress", "available": bool(stress["data"]), "coverage": stress["message"]},
                     {"metric": "Comparable benchmark", "available": False, "coverage": "No external benchmark or certification target is encoded."},
                 ],
                 "calculation": None, "weighting": None,
                 "missing_context": missing_context + ["The available observations combine different scopes and periods; no complete peer comparison is supported."]}
    report = {
        "report_id": None, "report_type": report_type, "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {"name": "PureFlow", "overview": "PureFlow is a data analytics platform designed to analyse water consumption in data centres, assess data quality, identify missing values and duplicates, clean and transform datasets, and generate meaningful insights to support sustainable water management."},
        "filters": filters,
        "selected_datasets": selected,
        "available_datasets": all_datasets,
        "sources": sources,
        "ingestion": {"latest_loads": latest_loads, "records_read": sum(x["records_read"] for x in latest_loads if x["load_status"] in {"loaded", "loaded_with_rejections"}),
                       "records_inserted": sum(x["records_inserted"] for x in latest_loads if x["load_status"] in {"loaded", "loaded_with_rejections"}),
                       "records_rejected": sum(x["records_rejected"] for x in latest_loads if x["load_status"] in {"loaded", "loaded_with_rejections"}),
                       "duplicate_records": sum(x["duplicate_records"] for x in latest_loads if x["load_status"] in {"loaded", "loaded_with_rejections"})},
        "data_quality": {"database_logs": quality_rows, "source_quality_reports": quality_reports, "coverage": coverage,
                         "database_validation": validation},
        "cleaning_and_transformation": {"cleaning": quality_reports, "transformations": transformations},
        "database": {"table_counts": table_counts, "schema": schema},
        "analysis": {"water_consumption": water, "wue": {k: v for k, v in wue.items() if k != "values"},
                     "wue_observations": wue_rows, "annual_trends": annual, "monthly_trends": monthly, "country_comparison": countries,
                     "climate": climate, "water_stress": stress},
        "findings": findings,
        "recommendations": recommendations,
        "sustainability": readiness,
        "limitations": _limitations(coverage, climate, stress),
        "conclusion": _conclusion(water, wue, coverage, climate, stress),
    }
    return report


def _median(values):
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def _findings(water, wue, countries, coverage, climate, stress):
    findings = []
    if water["gallon_observations"]:
        findings.append({"title": "Consumption reported in million gallons", "value": water["million_gallons"],
                         "unit": "million gallons", "observations": water["gallon_observations"],
                         "text": f"The selected records contain {water['gallon_observations']} explicitly reported million-gallon consumption values."})
    if water["litre_observations"]:
        findings.append({"title": "Consumption reported in million litres", "value": water["million_litres"],
                         "unit": "million litres", "observations": water["litre_observations"],
                         "text": f"The selected records contain {water['litre_observations']} explicitly reported million-litre consumption values. This total is not added to the gallon total."})
    if wue["observations"]:
        findings.append({"title": "Reported WUE distribution", "average_l_per_kwh": wue["average_l_per_kwh"],
                         "median_l_per_kwh": wue["median_l_per_kwh"], "minimum_l_per_kwh": wue["minimum_l_per_kwh"],
                         "maximum_l_per_kwh": wue["maximum_l_per_kwh"], "observations": wue["observations"],
                         "text": f"{wue['observations']} WUE observations are stored in L/kWh; their periods and scopes are not uniformly comparable."})
    if countries:
        findings.append({"title": "Country-linked consumption records", "countries": len(countries),
                         "text": f"Consumption can be grouped for {len(countries)} country-coded groups; missing country codes remain excluded from this grouping."})
    if coverage["records_without_country"]:
        findings.append({"title": "Geographic metadata gaps", "records_without_country": coverage["records_without_country"],
                         "records": coverage["total_records"], "text": f"{coverage['records_without_country']} of {coverage['total_records']} selected observations have no country code."})
    if not climate["data"]:
        findings.append({"title": "Climate analysis unavailable", "text": climate["message"]})
    if not stress["data"]:
        findings.append({"title": "Water-stress analysis unavailable", "text": stress["message"]})
    return findings


def _limitations(coverage, climate, stress):
    return [
        "Consumption totals are kept in source units. Million gallons and million litres are reported separately and must not be added together.",
        "WUE is reported in L/kWh and is not a water volume. The records include varying scopes, publishers, and periods, limiting direct comparison.",
        f"Country is missing for {coverage['records_without_country']} of {coverage['total_records']} selected observations; missing geography was not inferred.",
        climate["message"], stress["message"],
        "Source quality reports may flag incomplete or invalid fields. Cleaning preserves missing and ambiguous source values rather than imputing or guessing.",
        "No sustainability score is calculated because comparable benchmarks and complete climate and water-stress context are unavailable.",
    ]


def _conclusion(water, wue, coverage, climate, stress):
    parts = []
    if water["gallon_observations"] or water["litre_observations"]:
        parts.append(f"The database contains water-consumption evidence in {int(bool(water['gallon_observations'])) + int(bool(water['litre_observations']))} explicitly reported unit group(s).")
    if wue["observations"]:
        parts.append(f"It also contains {wue['observations']} WUE observations in L/kWh.")
    parts.append("These results demonstrate how dataset provenance, cleaning, relational storage, and SQL analysis can support sustainability review.")
    if not climate["data"] or not stress["data"]:
        parts.append("The current evidence supports data-readiness findings and targeted monitoring recommendations, but not a complete sustainability rating or climate/stress comparison.")
    parts.append(f"Country metadata is absent on {coverage['records_without_country']} selected observations; improving source coverage and adding linked climate and water-risk assessments would strengthen future analysis.")
    return " ".join(parts)


def report_rows(report):
    """Flatten report facts and recommendations into a portable CSV table."""
    rows = []
    def add(section, metric, value, unit=None, evidence=None):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=True, sort_keys=True)
        rows.append({"section": section, "metric": metric, "value": "" if value is None else value,
                     "unit": unit or "", "evidence": evidence or ""})
    add("report", "report_id", report.get("report_id")); add("report", "generated_at", report.get("generated_at"))
    add("filters", "selected_datasets", [d["dataset_id"] for d in report.get("selected_datasets", [])])
    for key, value in report["ingestion"].items():
        if isinstance(value, (int, float)):
            add("ingestion", key, value, evidence="Latest successful load per selected dataset")
    for key, value in report["analysis"]["water_consumption"].items():
        unit = "million gallons" if key == "million_gallons" else "million litres" if key == "million_litres" else "observations" if key.endswith("observations") or key == "records_with_consumption" else None
        add("water_consumption", key, value, unit)
    for key, value in report["analysis"]["wue"].items():
        add("wue", key, value, "L/kWh" if "l_per_kwh" in key else "observations" if key == "observations" else None)
    for finding in report["findings"]:
        add("finding", finding.get("title", "finding"), finding)
    for item in report["recommendations"]:
        add("recommendation", item["title"], item["supporting_evidence"], evidence=item["reason"])
    for limitation in report["limitations"]:
        add("limitation", "limitation", limitation)
    return rows


def render_csv(report):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["section", "metric", "value", "unit", "evidence"])
    writer.writeheader()
    for row in report_rows(report):
        for key, value in row.items():
            if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
                row[key] = "'" + value
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def _pdf_text(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_lines(report):
    lines = ["PureFlow Sustainability Report", f"Report type: {report['report_type']}", f"Reporting date: {report['generated_at']}",
             "", "PROJECT OVERVIEW", report["project"]["overview"], "", "SELECTED DATASETS"]
    if report["selected_datasets"]:
        for dataset in report["selected_datasets"]:
            lines.append(f"{dataset['source_filename']} | {dataset['source_type']} | {dataset['record_count']} stored / {dataset['source_record_count']} source")
            for source in next((x["sources"] for x in report["sources"] if x["dataset_id"] == dataset["dataset_id"]), []):
                lines.append(f"Source: {source.get('title') or 'Untitled'} {source.get('url') or ''}")
    else:
        lines.append("No dataset matches the selected filters.")
    lines.extend(["", "INGESTION AND DATA QUALITY", f"Latest successful records read: {report['ingestion']['records_read']}",
                  f"Inserted: {report['ingestion']['records_inserted']} | Rejected: {report['ingestion']['records_rejected']} | Duplicates: {report['ingestion']['duplicate_records']}",
                  f"Database validation: {'passed' if report['data_quality']['database_validation']['valid'] else 'issues found'}"])
    for item in report["data_quality"]["source_quality_reports"]:
        if item.get("summary"):
            summary = item["summary"]
            lines.append(f"Source quality: completeness {summary.get('completeness_after')}%; missing values {summary.get('missing_values_after')}; duplicates {summary.get('duplicates_after')}.")
            if item.get("validation"):
                lines.append(f"Cleaning validation passed: {item['validation'].get('passed')}")
    lines.extend(["", "CLEANING AND TRANSFORMATION SUMMARY"])
    for item in report["cleaning_and_transformation"]["cleaning"]:
        for operation in item.get("cleaning_history", []):
            validation_result = operation.get("validation", {}).get("passed")
            lines.append(f"Cleaning operation {operation.get('operation')} at {operation.get('timestamp')}; validation passed: {validation_result}.")
    for item in report["cleaning_and_transformation"]["transformations"]:
        validation_result = item.get("validation", {}).get("passed")
        lines.append(f"Transformation {item.get('operation')} at {item.get('generated_at')}; {item.get('output_rows')} output rows; validation passed: {validation_result}.")
    lines.extend(["", "DATABASE TABLE COUNTS"])
    lines.extend(f"{table}: {count} records" for table, count in report["database"]["table_counts"].items())
    lines.extend(["", "KEY PERFORMANCE INDICATORS", f"Consumption: {report['analysis']['water_consumption']['million_gallons']} million gallons ({report['analysis']['water_consumption']['gallon_observations']} observations)",
                  f"Consumption: {report['analysis']['water_consumption']['million_litres']} million litres ({report['analysis']['water_consumption']['litre_observations']} observations)",
                  f"WUE: {report['analysis']['wue']['observations']} observations; average {report['analysis']['wue']['average_l_per_kwh']} L/kWh; median {report['analysis']['wue']['median_l_per_kwh']} L/kWh"])
    lines.extend(["", "ANNUAL CHART SUMMARY"])
    for row in report["analysis"]["annual_trends"]:
        lines.append(f"{row['reporting_year']}: {row['million_gallons']} million gallons; {row['million_litres']} million litres")
    if not report["analysis"]["monthly_trends"]:
        lines.append("Monthly consumption summary: unavailable; no explicit compatible month is present in the selected records.")
    lines.extend(["", "ANALYTICAL FINDINGS"])
    for item in report["findings"]:
        lines.append(f"- {item['title']}: {item.get('text','')}")
    lines.extend(["", "SUSTAINABILITY RECOMMENDATIONS"])
    if report["recommendations"]:
        for item in report["recommendations"]:
            lines.extend([f"- {item['title']} ({item['evidence_level']})", f"  {item['explanation']}", f"  Evidence: {json.dumps(item['supporting_evidence'], ensure_ascii=True)}", f"  Limits: {item['limitations']}"])
    else:
        lines.append("No recommendations were generated from the selected records.")
    lines.extend(["", "SUSTAINABILITY DATA READINESS", report["sustainability"]["message"], "No composite sustainability score was calculated.", "", "LIMITATIONS"])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", "CONCLUSION", report["conclusion"]])
    wrapped = []
    for line in lines:
        if not line:
            wrapped.append("")
        else:
            wrapped.extend(textwrap.wrap(str(line), width=96, subsequent_indent="  ", break_long_words=True, break_on_hyphens=False) or [""])
    return wrapped


def render_pdf(report):
    """Create a dependency-free, paginated PDF with readable text and chart summaries."""
    lines = _pdf_lines(report)
    pages = [lines[index:index + 48] for index in range(0, len(lines), 48)] or [[]]
    objects = [None, None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    page_ids = []
    for page_num, page_lines in enumerate(pages, start=1):
        content_id = len(objects) + 1
        page_id = content_id + 1
        page_ids.append(page_id)
        commands = ["BT /F2 17 Tf 48 804 Td (PureFlow Sustainability Report) Tj ET",
                    "0.25 w 48 792 m 547 792 l S"]
        y = 774
        for line in page_lines:
            if line.isupper() and len(line) < 65:
                commands.append(f"BT /F2 11 Tf 48 {y} Td ({_pdf_text(line)}) Tj ET")
                y -= 18
                continue
            commands.append(f"BT /F1 9 Tf 48 {y} Td ({_pdf_text(line)}) Tj ET")
            y -= 14
        commands.append(f"BT /F1 8 Tf 48 28 Td (PureFlow | Page {page_num} of {len(pages)}) Tj ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>".encode())
    objects[0] = f"<< /Type /Catalog /Pages 2 0 R >>".encode()
    objects[1] = (f"<< /Type /Pages /Count {len(page_ids)} /Kids [{ ' '.join(f'{page_id} 0 R' for page_id in page_ids) }] >>").encode()
    output = bytearray(b"%PDF-1.4\n% PureFlow\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode()); output.extend(obj); output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def write_report_exports(report, storage_dir):
    root = Path(storage_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    report_id = uuid.uuid4().hex
    temporary = root / f".{report_id}.tmp"
    destination = root / report_id
    temporary.mkdir()
    report["report_id"] = report_id
    payload = json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False).encode("utf-8")
    try:
        (temporary / "report.json").write_bytes(payload)
        (temporary / "report.csv").write_bytes(render_csv(report))
        (temporary / "report.pdf").write_bytes(render_pdf(report))
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {"report_id": report_id, "generated_at": report["generated_at"], "report_type": report["report_type"],
            "filters": report["filters"], "formats": ["pdf", "csv", "json"], "selected_datasets": report["selected_datasets"]}


def list_report_history(storage_dir):
    root = Path(storage_dir).resolve()
    if not root.exists():
        return []
    history = []
    for directory in root.iterdir():
        if not directory.is_dir() or not REPORT_ID.fullmatch(directory.name):
            continue
        if directory.resolve().parent != root:
            continue
        path = directory / "report.json"
        if path.resolve().parent != directory.resolve():
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        history.append({"report_id": directory.name, "generated_at": report.get("generated_at"),
                        "report_type": report.get("report_type"), "filters": report.get("filters"),
                        "selected_datasets": report.get("selected_datasets", []),
                        "formats": [ext for ext in ("pdf", "csv", "json") if (directory / f"report.{ext}").is_file()]})
    return sorted(history, key=lambda item: item.get("generated_at") or "", reverse=True)


def report_download_path(storage_dir, report_id, output_format):
    if not REPORT_ID.fullmatch(report_id or "") or output_format not in {"pdf", "csv", "json"}:
        return None
    root = Path(storage_dir).resolve()
    directory = (root / report_id).resolve()
    if directory.parent != root:
        return None
    path = (directory / f"report.{output_format}").resolve()
    if path.parent != directory or not path.is_file():
        return None
    return path
