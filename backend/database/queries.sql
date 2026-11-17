-- PureFlow analytical SQL. Each consumption unit is kept separate; WUE is not a volume.
-- Total consumption, split by the source's explicitly reported unit.
SELECT SUM(consumption_million_gal) AS million_gallons,
       SUM(consumption_million_litres) AS million_litres
FROM water_metrics;

-- Average WUE by place; WUE remains in L/kWh and is not added to consumption.
SELECT l.place_name, l.country, AVG(w.wue_l_per_kwh) AS average_wue_l_per_kwh,
       COUNT(w.wue_l_per_kwh) AS observations
FROM water_metrics w JOIN locations l ON l.location_id = w.location_id
WHERE w.wue_l_per_kwh IS NOT NULL
GROUP BY l.location_id ORDER BY average_wue_l_per_kwh;

-- Water consumption by country, preserving unlike units separately.
SELECT l.country, SUM(w.consumption_million_gal) AS million_gallons,
       SUM(w.consumption_million_litres) AS million_litres, COUNT(*) AS observations
FROM water_metrics w JOIN locations l ON l.location_id = w.location_id
WHERE l.country IS NOT NULL AND (w.consumption_million_gal IS NOT NULL OR w.consumption_million_litres IS NOT NULL)
GROUP BY l.country ORDER BY million_litres DESC;

-- Distinct country-linked place labels with source scope='site'; these are not certified data-centre counts.
SELECT l.country, COUNT(DISTINCT l.location_id) AS site_labels
FROM water_metrics w JOIN locations l ON l.location_id=w.location_id
WHERE w.scope='site' AND l.country IS NOT NULL
GROUP BY l.country ORDER BY site_labels DESC, l.country;

-- Annual observations for source periods that contain an unambiguous year.
SELECT reporting_year, SUM(consumption_million_gal) AS million_gallons,
       SUM(consumption_million_litres) AS million_litres, COUNT(*) AS observations
FROM water_metrics WHERE reporting_year IS NOT NULL
AND (consumption_million_gal IS NOT NULL OR consumption_million_litres IS NOT NULL)
GROUP BY reporting_year ORDER BY reporting_year;

-- Month-level totals are available only for records with an explicit month.
SELECT measurement_month, SUM(consumption_million_gal) AS million_gallons,
       SUM(consumption_million_litres) AS million_litres, COUNT(*) AS observations
FROM water_metrics WHERE measurement_month IS NOT NULL
AND (consumption_million_gal IS NOT NULL OR consumption_million_litres IS NOT NULL)
GROUP BY measurement_month ORDER BY measurement_month;

-- Source dataset counts and load validation summary.
SELECT d.dataset_id, d.dataset_name, d.source_record_count, d.record_count,
       COUNT(DISTINCT w.metric_id) AS stored_metric_records
FROM datasets d LEFT JOIN water_metrics w ON w.dataset_id = d.dataset_id
GROUP BY d.dataset_id ORDER BY d.loaded_at DESC;
