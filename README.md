# JoTrip Transit Live

Public transit operations dashboard for Phu Quoc.

Production: https://transit.openphuquoc.com/

## Scope

- Fast ferry and vehicle ferry
- Public bus and fixed-route shuttle services
- Service disruption and data freshness
- Aggregated demand/capacity signals only

Taxi, private transfer, rental vehicles and destination-planning content are intentionally out of scope so Transit Live does not duplicate Open Phu Quoc.

## Data contract

The frontend reads `data/network.json`. Production collectors must write verified data to that snapshot. Missing data must remain missing rather than being replaced by synthetic values.

See `docs/DATA_POLICY.md`.
