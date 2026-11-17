"""Evidence-linked sustainability recommendations with explicit heuristics."""


def generate_recommendations(evidence):
    recommendations = []
    water = evidence.get("water_consumption") or {}
    wue = evidence.get("wue") or {}
    coverage = evidence.get("coverage") or {}

    if water.get("gallon_observations", 0) or water.get("litre_observations", 0):
        recommendations.append({
            "id": "unit-aware-monitoring", "category": "Water monitoring",
            "title": "Continue unit-aware water monitoring",
            "explanation": "Keep consumption observations attached to their reporting period, scope, and source unit so changes can be reviewed without combining incompatible quantities.",
            "supporting_evidence": {
                "million_gallons_total": water.get("million_gallons"),
                "million_gallon_observations": water.get("gallon_observations", 0),
                "million_litres_total": water.get("million_litres"),
                "million_litre_observations": water.get("litre_observations", 0),
            },
            "related_metric": "Reported water consumption by source unit",
            "location": None,
            "reason": "The loaded records contain consumption in more than one reported unit; preserving unit and period context makes future monitoring interpretable.",
            "evidence_level": "Directly observed; operational action is advisory",
            "limitations": "These totals remain separate and are not a normalized time series. This recommendation predicts no water savings.",
        })

    wue_values = wue.get("values") or []
    if len(wue_values) >= 8:
        ordered = sorted(float(row["value"]) for row in wue_values)
        q1 = _quantile(ordered, 0.25)
        q3 = _quantile(ordered, 0.75)
        fence = q3 + 1.5 * (q3 - q1)
        outliers = [row for row in wue_values if float(row["value"]) > fence]
        if outliers:
            recommendations.append({
                "id": "review-wue-outliers", "category": "Water efficiency",
                "title": "Review unusually high reported WUE observations",
                "explanation": "Verify the highest WUE observations against their source documents, scope, and reporting periods before prioritizing operational follow-up.",
                "supporting_evidence": {"observations": len(wue_values), "unit": "L/kWh", "internal_upper_fence": round(fence, 4),
                                        "flagged_observations": [{"value": row["value"], "location": row["place_name"], "country": row["country"], "period": row["measurement_period"]} for row in outliers]},
                "related_metric": "WUE (L/kWh)",
                "location": ", ".join(dict.fromkeys(row["place_name"] for row in outliers)),
                "reason": "Flagging uses the dataset's Tukey upper fence (Q3 plus 1.5 times the interquartile range), an internal screening heuristic rather than an external efficiency benchmark.",
                "evidence_level": "Statistical screening; medium",
                "limitations": "Records can represent different scopes, publishers, and years. An outlier is not proof of poor performance, an error, or a comparable peer result.",
            })

    if coverage.get("records_without_country", 0) > 0:
        recommendations.append({
            "id": "improve-location-coverage", "category": "Data quality",
            "title": "Improve location metadata coverage",
            "explanation": "Where source documentation supports it, add country information to future transformed records and preserve unknown values as unknown.",
            "supporting_evidence": {"records": coverage.get("total_records", 0), "records_with_country": coverage.get("records_with_country", 0),
                                    "records_without_country": coverage.get("records_without_country", 0)},
            "related_metric": "Country metadata completeness",
            "location": None,
            "reason": "Records with missing country metadata cannot participate in country-level comparisons.",
            "evidence_level": "Directly observed; high",
            "limitations": "A country should be added only when supported by the source. This recommendation makes no geographic inference.",
        })

    if coverage.get("records_without_consumption", 0) > 0 and coverage.get("total_records", 0) > 0:
        recommendations.append({
            "id": "improve-consumption-coverage", "category": "Water monitoring",
            "title": "Review water-consumption measurement coverage",
            "explanation": "Identify whether missing consumption measurements reflect a different metric scope or unavailable source reporting, and record that context in future data submissions.",
            "supporting_evidence": {"records": coverage.get("total_records", 0), "records_with_consumption": coverage.get("records_with_consumption", 0),
                                    "records_without_consumption": coverage.get("records_without_consumption", 0)},
            "related_metric": "Rows with an explicitly reported consumption measure",
            "location": None,
            "reason": "Rows without a consumption value cannot contribute to consumption totals or trend analysis.",
            "evidence_level": "Directly observed; high",
            "limitations": "Not every source row represents a consumption measurement; missing values are not treated as zero.",
        })

    return recommendations


def _quantile(values, fraction):
    """Linear interpolation equivalent to the common inclusive sample quantile."""
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)
