# Design decisions

## Flexibility rules

- **Tests run before every commit.** Any calculation change needs a test that proves the result.

- **School days are a setting.** Default Monday to Friday. Schools that open on Saturdays change it in the admin.
- **Holidays are data.** Each school enters its own non-school days. No holidays are hard-coded.
- **Excused absences need a note.** Parent letter references can be added as a field later if the school asks.
- **One audit entry per register save.** Lists only the students whose status or note changed.

- **Attendance percentage.** (Present + Late) divided by (days marked minus Excused). Late counts as attended. Excused days are removed from the calculation.
- **Reports use the view_attendance capability.** Anyone who can view attendance can also download the report as CSV. If a school wants export restricted, add a separate capability later.