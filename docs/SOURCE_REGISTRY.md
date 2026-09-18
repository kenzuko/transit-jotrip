# Source registry

Last reviewed: 2026-09-18

| Source | What Transit uses | Classification | Automation |
| --- | --- | --- | --- |
| Thạnh Thới public homepage | Daily ferry schedule, vessel, public status such as Đã xuất bến / booking open | Operational public | Low-frequency GET, 30 min |
| Superdong public ScheduleBoat page | Published Phú Quốc route timetable | Schedule | Low-frequency GET, 30 min |
| Phú Quốc Express public schedule page | Monthly schedule reference | Schedule image | Reference only for now |
| Phú Quốc Express booking system | Nothing | Excluded | No automated collection |
| Superdong booking system | Nothing | Excluded | No automated collection |
| VinWonders / VinBus public 2026 schedule | Routes 17, 19, 20, operating window and frequency | Schedule / frequency | Curated public schedule |

## Rules

- Booking-system inventory is not a production dependency unless JoTrip receives explicit partner/B2B permission.
- Exact seat counts are never written to the public snapshot.
- No passenger or booking data is collected.
- Missing data stays missing. The system does not translate missing data into "Normal".
- Operational status, timetable and frequency are separate data kinds and must remain distinguishable in the UI.
