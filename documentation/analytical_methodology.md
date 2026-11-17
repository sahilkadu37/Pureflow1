# PureFlow analytical methodology

## SQL-backed measures

- **Water consumption:** `SUM(consumption_million_gal)` and `SUM(consumption_million_litres)` are calculated independently. Each has its own non-null observation count. PureFlow does not add these totals or infer a conversion.
- **WUE:** stored and reported in L/kWh. Summary statistics include observation count, arithmetic mean, median, minimum, and maximum. Location summaries use SQL `AVG` and `COUNT`; they are descriptive and may mix scopes or periods.
- **Annual trend:** records with an unambiguous four-digit source period year are grouped by year. Million-gallon and million-litre totals remain separate.
- **Monthly trend:** only explicit parseable month/year or year-month source periods participate. None of the currently stored consumption records provides an eligible explicit month, so the current monthly API returns an empty-state message.
- **Country comparison:** only records with a country code are grouped. Missing country codes remain NULL and are excluded; PureFlow does not geocode place names.
- **Climate and water stress:** APIs return a clear no-compatible-data response when their measurement tables or valid relationships are absent.

The reusable SQL examples are in `backend/database/queries.sql`; Flask analytics use parameterized SQL in `backend/app/services/sql_analytics.py`.

## Recommendation rules

Recommendations are generated only when supporting values exist:

1. Unit-aware consumption monitoring is suggested when consumption observations exist. It does not claim a reduction or savings amount.
2. WUE values are screened for high outliers only when at least eight observations exist. The flag is the Tukey upper fence, Q3 + 1.5 × IQR, calculated over selected raw WUE observations. This is an internal review trigger, not an official benchmark or proof of inefficiency.
3. Geographic metadata coverage is flagged when selected records lack country codes.
4. Consumption coverage is flagged when selected rows have no explicitly reported consumption value. Missing values are not treated as zero, and non-consumption rows may be expected for their source scope.

Each recommendation includes its evidence values, metric, reason, evidence level, and limitations. Climate and water-stress recommendations are omitted when those metrics are unavailable.

## Sustainability indicator decision

PureFlow does not calculate a sustainability score. The current dataset has water volume and WUE measures but no compatible climate or linked water-stress records, no encoded external benchmark, and heterogeneous scope and periods. Combining or weighting these incomplete inputs would create an unsupported comparison. The report provides a data-readiness checklist instead; it does not define a weighting scheme or certify sustainability.

## Report filter semantics

Dataset IDs restrict selected loaded datasets. Location matching is case-insensitive substring matching over place labels and country codes. `start_date` and `end_date` are validated as ISO dates, but filtering is performed at source-period year granularity. For example, a selected calendar year may include annual source rows that do not have month-level timing. This limitation is included in the UI and report documentation.

## Export methodology

JSON preserves the complete structured report. CSV exports a normalized `section, metric, value, unit, evidence` table and prefixes spreadsheet formula-like text to reduce formula injection risk. PDF uses a dependency-free text layout with page breaks, page numbers, KPI sections, annual chart summaries, findings, recommendations, and limitations. It does not fabricate plot images when a compatible time series is unavailable.
