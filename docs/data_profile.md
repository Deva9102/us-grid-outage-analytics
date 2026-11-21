# EAGLE-I Data Profile

Profiled on 2026-11-20 with DuckDB 2.0.1, using `scripts/profile_eaglei.py`. Raw files are read only. `fips_code` is read as text so leading zeros are preserved; the auto-detected type is shown next to it.

## Column comparison across years

| Column | 2022 | 2023 | 2024 |
|---|---|---|---|
| `fips_code` | VARCHAR | VARCHAR | VARCHAR |
| `county` | VARCHAR | VARCHAR | VARCHAR |
| `state` | VARCHAR | VARCHAR | VARCHAR |
| `customers_out` | BIGINT | - | BIGINT |
| `run_start_time` | TIMESTAMP | TIMESTAMP | TIMESTAMP |
| `sum` | - | BIGINT | - |
| `total_customers` | - | - | BIGINT |

| Metric | 2022 | 2023 | 2024 |
|---|---|---|---|
| Rows | 25,796,465 | 26,101,051 | 27,701,334 |
| Distinct FIPS | 3,057 | 3,058 | 3,061 |
| Distinct states | 53 | 53 | 53 |
| Distinct timestamps | 35,037 | 35,024 | 35,095 |
| Max customers out | 456,573 | 348,829 | 1,660,703 |
| Duplicate keys | 0 | 0 | 0 |
| Missing 15-min slots | 3 | 17 | 41 |
| Off-grid rows | 0 | 819 | 0 |
| Panel density | 24.1% | 24.4% | 25.8% |

## 2022

File: `data/raw/eaglei/2022/eaglei_outages_2022.csv` (1.19 GB)

| Metric | Value |
|---|---|
| Rows | 25,796,465 |
| Distinct FIPS codes | 3,057 |
| Distinct states | 53 |
| Min timestamp | 2022-01-01 00:00:00 |
| Max timestamp | 2022-12-31 23:45:00 |
| Distinct timestamps | 35,037 |
| Customers-out column | `customers_out` |
| Max customers out | 456,573 |
| Min customers out | 0 |
| Mean customers out | 192.73 |
| Rows with 0 customers out | 1,280,476 |
| Rows with negative customers out | 0 |
| Duplicate (fips_code, run_start_time) keys | 0 |
| Rows with timestamps off the 15-minute grid | 0 |
| Expected 15-minute slots in year | 35,040 |
| 15-minute slots with no rows at all | 3 |
| Panel density (rows / counties x slots) | 24.1% |

### Columns

| Column | Auto-detected type | Type used | Nulls |
|---|---|---|---|
| `fips_code` | VARCHAR | VARCHAR | 0 |
| `county` | VARCHAR | VARCHAR | 0 |
| `state` | VARCHAR | VARCHAR | 0 |
| `customers_out` | BIGINT | BIGINT | 0 |
| `run_start_time` | TIMESTAMP | TIMESTAMP | 0 |

### FIPS code format

| Length | Distinct codes | Rows |
|---|---|---|
| 5 | 3,057 | 25,796,465 |

- Leading zeros lost in the raw text: **no** (0 codes shorter than 5 characters).
- 5-digit codes starting with 0 (states 01-09): 291.
- Non-numeric codes: 0.
- Auto-detected type for `fips_code` is VARCHAR.

### Largest single readings

| FIPS | County | State | Customers out | Time |
|---|---|---|---|---|
| 12071 | Lee | Florida | 456,573 | 2022-09-29 00:00:00 |
| 12071 | Lee | Florida | 456,323 | 2022-09-28 23:45:00 |
| 12071 | Lee | Florida | 454,611 | 2022-09-28 23:30:00 |
| 12071 | Lee | Florida | 454,291 | 2022-09-28 23:15:00 |
| 12071 | Lee | Florida | 454,176 | 2022-09-28 23:00:00 |

## 2023

File: `data/raw/eaglei/2023/eaglei_outages_2023.csv` (1.20 GB)

| Metric | Value |
|---|---|
| Rows | 26,101,051 |
| Distinct FIPS codes | 3,058 |
| Distinct states | 53 |
| Min timestamp | 2023-01-01 00:00:00 |
| Max timestamp | 2023-12-31 23:45:00 |
| Distinct timestamps | 35,024 |
| Customers-out column | `sum` |
| Max customers out | 348,829 |
| Min customers out | 0 |
| Mean customers out | 162.32 |
| Rows with 0 customers out | 1,306,670 |
| Rows with negative customers out | 0 |
| Duplicate (fips_code, run_start_time) keys | 0 |
| Rows with timestamps off the 15-minute grid | 819 |
| Expected 15-minute slots in year | 35,040 |
| 15-minute slots with no rows at all | 17 |
| Panel density (rows / counties x slots) | 24.4% |
| Off-grid timestamp 2023-03-22 20:31:00 | 819 rows |

### Columns

| Column | Auto-detected type | Type used | Nulls |
|---|---|---|---|
| `fips_code` | VARCHAR | VARCHAR | 0 |
| `county` | VARCHAR | VARCHAR | 0 |
| `state` | VARCHAR | VARCHAR | 0 |
| `sum` | BIGINT | BIGINT | 0 |
| `run_start_time` | TIMESTAMP | TIMESTAMP | 0 |

### FIPS code format

| Length | Distinct codes | Rows |
|---|---|---|
| 5 | 3,058 | 26,101,051 |

- Leading zeros lost in the raw text: **no** (0 codes shorter than 5 characters).
- 5-digit codes starting with 0 (states 01-09): 291.
- Non-numeric codes: 0.
- Auto-detected type for `fips_code` is VARCHAR.

### Largest single readings

| FIPS | County | State | Customers out | Time |
|---|---|---|---|---|
| 06067 | Sacramento | California | 348,829 | 2023-01-08 11:00:00 |
| 06067 | Sacramento | California | 347,618 | 2023-01-08 10:00:00 |
| 06067 | Sacramento | California | 347,315 | 2023-01-08 09:45:00 |
| 06067 | Sacramento | California | 346,955 | 2023-01-08 09:30:00 |
| 06067 | Sacramento | California | 346,850 | 2023-01-08 10:45:00 |

## 2024

File: `data/raw/eaglei/2024/eaglei_outages_2024.csv` (1.44 GB)

| Metric | Value |
|---|---|
| Rows | 27,701,334 |
| Distinct FIPS codes | 3,061 |
| Distinct states | 53 |
| Min timestamp | 2024-01-01 00:00:00 |
| Max timestamp | 2024-12-31 23:45:00 |
| Distinct timestamps | 35,095 |
| Customers-out column | `customers_out` |
| Max customers out | 1,660,703 |
| Min customers out | 0 |
| Mean customers out | 273.15 |
| Rows with 0 customers out | 1,085,214 |
| Rows with negative customers out | 0 |
| Duplicate (fips_code, run_start_time) keys | 0 |
| Rows with timestamps off the 15-minute grid | 0 |
| Expected 15-minute slots in year | 35,136 |
| 15-minute slots with no rows at all | 41 |
| Panel density (rows / counties x slots) | 25.8% |
| Rows where customers out > total_customers | 8,441 |
| Sum of total_customers (max per county) | 176,634,874 |

### Columns

| Column | Auto-detected type | Type used | Nulls |
|---|---|---|---|
| `fips_code` | VARCHAR | VARCHAR | 0 |
| `county` | VARCHAR | VARCHAR | 0 |
| `state` | VARCHAR | VARCHAR | 0 |
| `customers_out` | BIGINT | BIGINT | 0 |
| `run_start_time` | TIMESTAMP | TIMESTAMP | 0 |
| `total_customers` | BIGINT | BIGINT | 73 |

### FIPS code format

| Length | Distinct codes | Rows |
|---|---|---|
| 5 | 3,061 | 27,701,334 |

- Leading zeros lost in the raw text: **no** (0 codes shorter than 5 characters).
- 5-digit codes starting with 0 (states 01-09): 291.
- Non-numeric codes: 0.
- Auto-detected type for `fips_code` is VARCHAR.

### Largest single readings

| FIPS | County | State | Customers out | Time |
|---|---|---|---|---|
| 48201 | Harris | Texas | 1,660,703 | 2024-07-08 19:15:00 |
| 48201 | Harris | Texas | 1,660,703 | 2024-07-08 19:30:00 |
| 48201 | Harris | Texas | 1,660,701 | 2024-07-08 19:45:00 |
| 48201 | Harris | Texas | 1,652,421 | 2024-07-08 20:45:00 |
| 48201 | Harris | Texas | 1,652,419 | 2024-07-08 20:30:00 |

## Reference: MCC.csv (modeled customers per county)

- Columns: `County_FIPS`, `Customers`
- County rows: 3,233
- Non-county rows (exclude when loading): Grand Total = 154451840
- FIPS codes shorter than 5 characters: 312 (leading zeros lost; pad to 5 before joining)
- Total modeled customers (county rows only): 154,451,840
