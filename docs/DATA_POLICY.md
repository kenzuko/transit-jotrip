# Transit data policy

## Public operational view

The public page may show route, operator, vessel/service, scheduled departure, operational status, service alerts and high-level demand or capacity signals when permitted.

Exact seat inventory is not published. Seat maps, passenger data, booking identifiers and personally identifiable information must never be exposed.

When an upstream source does not explicitly permit automated reuse, it must not become a hard production dependency. Prefer official public feeds, published schedules, licensed partner/B2B access, or low-frequency compliant retrieval.

## Demand signal

Any capacity signal shown publicly must be transformed into broad categories such as:

- Còn nhiều
- Còn ít
- Gần hết
- Hết chỗ
- Nhu cầu cao / bình thường / thấp

Internal analytical values, when lawfully obtained, remain private and are not copied into the public snapshot.

## Data integrity

No synthetic departures are allowed in production. If a source is missing or stale, the UI must say so. "Normal" is never inferred from missing data.
