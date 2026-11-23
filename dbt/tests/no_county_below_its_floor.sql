-- Mirrors the D35 quality gate: no county of a calibrated state has a denominator below its
-- highest reading in the denominator base years (D58), unless D36 skipped its floor.
SELECT fips_code, customers, base_peak_customers_out
FROM {{ ref('dim_county') }}
WHERE is_calibrated
  AND customers < base_peak_customers_out
  AND NOT peak_floor_skipped
