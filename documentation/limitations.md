# PureFlow limitations

- **Heterogeneous source compilation:** records describe different publishers, facilities, regions, fleets, AI prompt estimates, and policy/study contexts. A single database table does not imply a common population or measurement protocol.
- **Incomplete quality checks:** the source cleaning report has 68.1232% completeness and failed configured validation for 25 date values and 7 water-scope values. These values remain as supplied.
- **Missing geography:** 26/85 source rows have no country code. Place labels are not reverse-geocoded and are not guaranteed to identify data centres.
- **Units and measurement meaning:** consumption is reported separately in million gallons and million litres; WUE is in L/kWh; prompt-level water and training values are separate fields. PureFlow does not combine unlike units or metrics.
- **Time coverage:** many `period` fields are annual or descriptive. Date filters operate at year granularity, and monthly consumption trends are empty unless a source explicitly supplies a parseable month.
- **Climate and risk:** no compatible climate or water-stress records or valid location/time relationships are currently loaded. Those analyses return empty states.
- **No external baseline:** no official benchmark, target, or certification schema is stored. A sustainability score is intentionally not calculated.
- **Recommendation scope:** the WUE Tukey fence is an internal statistical screen only. Scope/time differences can make flagged values unsuitable for direct peer comparisons. Recommendations do not estimate savings.
- **Licenses:** source URLs are retained as provenance, but the upload has no machine-readable license or complete rights assessment. Reuse terms must be checked with each source.
- **PDF rendering:** exports include text and annual chart summaries, not rendered chart images. Page numbers are included; PDF generation uses built-in Python functionality rather than a dedicated PDF layout package.
