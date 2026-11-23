# Changelog

Changes that restate results I published earlier.

## 2026-11-22: empty readings no longer split outages (D64)

Runs of empty readings of up to 24 hours between two outage readings no longer end an event. No
state or county rank changes, and total customer-hours are unchanged.

| Measure | Before | After |
|---|---|---|
| Events in 2025 | 156,218 | 156,094 |
| Customer-hours in 2024 | 1,689.5 M | 1,691.4 M |
| Customer-hours in 2025 | 695.6 M | 693.7 M |
| Ponce PR blackout (2025-04-16) | 2 events, largest 3.07 M | 1 event, 4.06 M (2025 rank 9 to 5) |
| Mayagüez PR blackout (2025-04-16) | 2 events, largest 2.19 M | 1 event, 3.16 M (enters the 2025 top 10) |

The 2024 change is three Puerto Rico events of the 2024-12-31 blackout (San Juan, Caguas, Ponce
regions) that now continue into 2025-01-02. Cheboygan MI 26047-00141 leaves the 2025 top 10.

## 2026-11-22: county reliability rows start at the first reported year (D61)

A county now gets reliability rows only from the first year EAGLE-I reports it. Before, a county
first reported later appeared in earlier years with zero outage hours, which lowered its state's
rate. This restates the 2022 and 2023 rankings; 2024 is unchanged and no rank 1 changed.

| Measure | Year | Before | After |
|---|---|---|---|
| Ranked counties | 2022 | 3,009 | 3,004 |
| Ranked counties | 2023 | 3,009 | 3,006 |
| Mississippi state rank | 2022 | 18 | 17 |
| Mississippi hours per 1,000 customers | 2022 | 4,451 | 4,666 |
| Mississippi state rank | 2023 | 11 | 10 |
| Mississippi hours per 1,000 customers | 2023 | 8,820 | 9,169 |
| Washington state rank | 2022 | 14 | 13 |

Removed county-years (coverage-gap zeros): 2022 Chugach AK, Lee, Prentiss and Tishomingo MS,
Garfield MT, Okanogan WA; 2023 Chugach AK, Lee and Tishomingo MS, Okanogan WA. Arkansas and
Kentucky 2022 and Hawaii 2023 each move down one rank as a result.
