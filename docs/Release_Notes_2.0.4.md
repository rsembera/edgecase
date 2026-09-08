# EdgeCase Equalizer 2.0.4

A fix release. No new features, no data changes.

## Fixed: Absence and Item forms lost their date and time pickers

On the Absence Entry and Item Entry forms, the **Date** and **Time** labels
appeared with nothing under them — no calendar, no clock. The form could not
be filled in.

The cause was a template layout error that made the form's script load twice
and fail both times. The error is old, but it was masked by browser caching
until 2.0.1 began forcing fresh scripts on every upgrade, and Item and Absence
entries are less frequent than Sessions, so it went unnoticed until now. If
you have not opened an Absence or Item form since upgrading to 2.0.x, you
never saw it. Sessions, Communications and Uploads were never affected.

Along with the fix, every page template was checked for the same class of
mistake and two automated tests now guard against it recurring.

## Upgrading

Install over 2.0.3 as usual. Your data directory and backups are unaffected.
