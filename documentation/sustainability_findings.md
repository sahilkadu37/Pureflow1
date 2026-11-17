# Sustainability findings from the loaded dataset

These results describe the current SQLite snapshot and are recalculated in report exports. They are not a complete industry benchmark.

## Water consumption

- The database has 42 source observations with consumption explicitly reported in million gallons; their arithmetic sum is **21,045.95 million gallons**.
- It has 43 source observations with consumption explicitly reported in million litres; their arithmetic sum is **82,641.9 million litres**.
- These values are reported separately. They must not be added: they represent different observation subsets and may include overlapping source records.
- The annual grouping reports 2025 consumption of 21,045.95 million gallons and 79,667.9 million litres across their respective eligible observations. A 2024 source record reports 2,974 million litres and no gallon value.

## WUE

There are 35 source WUE observations. Their mean is approximately **0.377 L/kWh**, median **0.18 L/kWh**, minimum **0.02 L/kWh**, and maximum **2.85 L/kWh**. The values include different publishers, scopes, and periods, so they are not presented as directly comparable facility performance.

For a review-only outlier screen, the report uses the inclusive sample quartiles Q1 = 0.06 and Q3 = 0.36 L/kWh. The Tukey upper fence is 0.36 + 1.5 × (0.36 − 0.06) = **0.81 L/kWh**. Five values exceed that fence: 0.91, 1.15, 1.22, 1.57, and 2.85 L/kWh. The recommendation is to verify the source, scope, and period, not to label these locations inefficient.

## Geography, quality, and missing context

- 26 of 85 rows have no country code. 59 retain country metadata and support country grouping.
- The source quality report reports 569 missing cells across the 85 × 21 input, 68.1232% completeness, and zero exact duplicate rows.
- Cleaning validation remains flagged: 25 `source_date` values were invalid for the configured date rule and 7 `water_scope` values failed a numerical validation rule. Values were preserved, not guessed.
- The database has 74 distinct place labels. A place label is not a validated data-centre inventory entry.
- No climate measurements or linked water-stress assessments are stored. Climate and regional stress conclusions therefore cannot be drawn from this dataset.

## Recommendations generated for the current snapshot

1. Continue unit-aware water monitoring and retain period/scope context.
2. Review five WUE observations that exceed the dataset-internal Tukey screening fence.
3. Improve country metadata where source records support it.
4. Review why many rows have no consumption measure, while distinguishing expected non-consumption scopes from missing reporting.

No recommendation claims a specific water saving. No composite sustainability score is produced because comparable benchmarks, climate, and water-stress context are absent.
