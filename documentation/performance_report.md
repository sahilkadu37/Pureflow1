# PureFlow Performance Report

**Measurement date:** 2026-11-14

## Measured results

| Workload | Measurement |
|---|---|
| Complete backend unittest suite | 20 tests in 3.341 seconds |
| Actual-source E2E test | Included in suite; previous isolated run completed in about 2.25 seconds (timing varies by machine) |
| Source CSV | 33,794 bytes, 85 rows |
| Vite production build | 1.49 seconds; 2,962 modules transformed |
| Production assets | JS 963.14 kB minified / 285.90 kB gzip; CSS 64.23 kB / 13.88 kB gzip |

These are local measurements on the current workspace and sample, not service-level guarantees. No representative high-volume or concurrent workload was measured.

## Observations

- The JavaScript bundle is above Vite's 500 kB advisory threshold. Route-level code splitting is a likely next optimization; measure initial-load performance after splitting before adjusting the warning threshold.
- The report screen now obtains findings, recommendations, and sustainability values from its overview response, reducing its initial analytics calls from five backend requests to two (overview and history).
- SQLite analytics use aggregate SQL queries and open read-only connections for query operations. Custom SQL has a capped result size (500 server-side rows; the UI uses a smaller cap).
- Database loading uses batched inserts, but the transformed file is read into a Pandas frame before insertion. Memory use therefore scales with transformed file size and was not benchmarked at the upload limit.
- Upload parsing and cleaning also materialize tabular data in memory. The approximately 100 MiB request limit is only a transport cap, not a tested safe processing size.

## Recommended next measurements

1. Measure frontend initial route load and route transitions with browser performance tooling; split charts and rarely used pages if the bundle cost is material.
2. Benchmark upload, profile, clean, standardise, load, and report generation at representative row/column counts while recording peak RSS and elapsed time.
3. Measure concurrent read and write behavior and define acceptable SQLite busy/latency thresholds before choosing a multi-user deployment topology.
4. Repeat benchmarks on the target deployment hardware; keep sample size, runtime, and memory alongside each result.
