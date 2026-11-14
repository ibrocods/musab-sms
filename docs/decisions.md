# Design decisions

## Flexibility rules

- **Tests run before every commit.** Any calculation change needs a test that proves the result.

- **School days are a setting.** Default Monday to Friday. Schools that open on Saturdays change it in the admin.
- **Holidays are data.** Each school enters its own non-school days. No holidays are hard-coded.
- **Excused absences need a note.** Parent letter references can be added as a field later if the school asks.
- **One audit entry per register save.** Lists only the students whose status or note changed.

- **Attendance percentage.** (Present + Late) divided by (days marked minus Excused). Late counts as attended. Excused days are removed from the calculation.
- **Reports use the view_attendance capability.** Anyone who can view attendance can also download the report as CSV. If a school wants export restricted, add a separate capability later.

- **Payments are never edited or deleted.** Corrections are reversals, which are rows with their own receipt numbers.
- **Receipt numbers are never reused.** Reversals consume numbers too. The pattern is set in the school profile.
- **Reversing a payment needs a reason** and the reverse_payments capability (bursar and head teacher by default).
- **Balances are calculated, never stored.** Balance = charges minus payments (net of reversals) minus discounts.
- **Charges follow the student's current class.** A mid-term transfer changes the charge. The school decides whether to pro-rate.
- **Students with no class are charged only the all-class fees.**
- **Archived students stay on the debtors list.** A student who leaves owing money is still owed.
- **A negative balance is a credit,** not a debt, and is excluded from debtors.
- **Discounts are recorded, never deleted.** Ending one sets an end date.
- **Percentage discounts apply to total term charges,** not to each fee item.
- **A discount can't exceed the charges.**
- **Only the head teacher and bursar can grant or end discounts.**
- **Fee setup belongs to the bursar.** The head teacher can view fees, reverse payments and grant discounts, but can't change fee items.

- **Demo tooling is the only place that crosses apps.** core/demo.py imports fees lazily, inside functions, so core still loads without fees. Nothing else in core imports fees.
- **Demo wipe removes money with queryset deletes,** in order: reversals, payments, discounts, fee items. These match only demo students and demo terms.
- **Stage 3 is complete:** fee items, payments with unique receipts and reversals, calculated balances, discounts, bursar pages, and end-to-end tests.