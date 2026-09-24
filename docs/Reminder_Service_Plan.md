# Text Appointment Reminders — Exploratory Plan

**Status:** EXPLORATORY, 2026-09-24. Not scheduled. Written to capture the
design constraints while they are fresh; revisit after the intake service
(`Intake_Service_Plan.md`) ships, since this would reuse its Sentinel
deployment, repo pattern and consent capture.

## The idea

A client gets a text the day before a session: "Reminder: your appointment
with Richard is tomorrow at 2:00 pm." Sent automatically, only to clients who
opted in.

## Why it is not a small feature

Sending a text is trivial: one API call to a provider, a few cents. The
difficulty is entirely in *knowing what to send and when*.

1. **EdgeCase does not hold appointments.** Deliberate, see
   Architecture_Decisions → CALENDAR INTEGRATION: the calendar app is the
   source of truth, EdgeCase only generates events. Reschedules and
   cancellations happen in the calendar. Anything queued inside EdgeCase at
   scheduling time is stale the first time a session moves.
2. **The Mac is not always on.** Reminders fire at a fixed time whether or
   not the laptop is open. The sender has to live on Sentinel.
3. **So Sentinel needs to read the calendar**, which gives it a live view of
   when sessions happen. That is more sensitive than anything the intake
   service stores, and the design has to keep it minimal.

## Options considered

**A. Sentinel reads a calendar feed. (Recommended.)**
Sentinel polls a dedicated calendar (see below) every few minutes, finds
events 24 h out that carry a reminder marker, and sends. Reschedules and
cancellations are picked up automatically because the calendar is what's
read. Keeps the existing architecture decision intact.

**B. EdgeCase stores appointments.**
Reverses the calendar decision and reintroduces dual maintenance and sync
problems. Rejected.

**C. EdgeCase pushes reminder jobs to Sentinel at scheduling time.**
Simple, but wrong the moment anything is rescheduled in the calendar.
Would need reconciliation against the calendar anyway, which is option A with
extra steps. Rejected.

## Design sketch for option A

**Dedicated calendar.** A "Sessions" calendar containing only session events
EdgeCase generated. Sentinel reads only that one. It should never see
personal appointments.

**Feed access.** Two ways, to be decided:
- A secret subscription URL (e.g. iCloud "public" calendar by unguessable
  link). No credentials on Sentinel, but the URL itself is the secret and
  the feed is readable by anyone holding it.
- CalDAV with an app-specific password. Stronger, but a credential for the
  calendar account lives on Sentinel.

**Machine-readable marker.** EdgeCase already writes the client's contact
info into event notes, preferred method first. Parsing free text is fragile,
so instead EdgeCase adds one structured line when, and only when, the client
has consented to text reminders:

    SMS-Reminder: +16135551234

No line, no reminder. Consent revoked means future events are generated
without the line; existing recurring series need regenerating (EdgeCase
could flag them).

**What Sentinel stores:** a sent-log keyed by
`event UID + recurrence ID + start time`, so a rescheduled session gets a
fresh reminder and an unchanged one is never texted twice. Entries purged
after the session date passes. It does not store names; the event title is
already the file number, and nothing else is needed.

**Message.** Neutral, because SMS is plaintext through carriers and shows on
lock screens: no "therapy," probably no practice name.
"Reminder: your appointment with Richard is tomorrow (Tue) at 2:00 pm.
This number does not receive replies; please call or email to reschedule."
Online sessions could append the meeting link, or not; decide later.

**Timing.** 24 h before by default; quiet hours (no texts before 9:00 or
after 20:00; a 9:00 session gets its reminder the previous afternoon).

**Replies and opt-out.** Clients will reply "can't make it." Either the
number forwards replies to Richard, or the message says it is unmonitored.
STOP handling is mostly done by the provider; the service must also honour
it locally and tell Richard (so EdgeCase stops writing the marker).

**Failure alerting.** If a poll or a send fails, email Richard. A silently
broken reminder service is worse than none, because clients start relying
on it.

## Consent

Text reminders need explicit opt-in, separate from "preferred contact."
The natural place is an optional checkbox on the online intake form (open
question 5 in `Intake_Service_Plan.md`), stored in a new Profile field.
Adding the checkbox before this service exists costs nothing and means
consent is on file when it arrives.

## Provider

Candidates: **VoIP.ms** (Canadian, inexpensive, SMS API), **Telnyx**,
**Twilio**. Carrier rules for automated texts from long-code numbers have
been tightening in North America; verify current Canadian sender
registration requirements at build time rather than trusting this note.

## Estimate

3–5 sessions once the intake service exists: feed reader and recurrence
expansion (the fiddly part), sent-log, provider integration, EdgeCase marker
and consent field, alerting, tests. Plus a few days of calendar time for
provider account and number setup, independent of the code.

## Open questions

1. Is there a real use case? (How often do clients forget sessions today?)
2. Secret feed URL or CalDAV credential?
3. Replies: forward to Richard or unmonitored?
4. Include the meeting link for online sessions?
5. One reminder (24 h) or also a same-day one?
