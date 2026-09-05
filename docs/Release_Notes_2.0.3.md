# EdgeCase Equalizer 2.0.3

A same-day correction to 2.0.2. Everything else in 2.0.2 — the two privacy
fixes, the retention-disposal fix, master-key rotation, insurance provider
numbers — is unchanged and still applies. If you have not read the 2.0.2
notes, read those first.

## Withdrawn: the Reflections field

2.0.2 added an optional second notes field, **Reflections**, to session
entries. 2.0.3 removes it. It was released before it had been used in
practice, which is the wrong order, and it is gone until (and unless) it has
earned its place.

**If you never turned it on:** nothing changes.

**If you turned it on and wrote anything in it:** on first launch after
upgrading, the text of each Reflections field is moved to the end of that
session's Notes, under a divider that reads
`--- Reflections (moved from the withdrawn Reflections field) ---`. Nothing
is deleted. The move does not count as an amendment: the entry's modified
date and its edit history are left as they were.

Please review those entries. Reflections were designed to stay out of exports;
Notes are part of the clinical record and appear in the client file and
report. If something you wrote as a reflection should not be in the record,
edit it out now, the way you would any other note.

## Upgrading

Install over 2.0.2 as usual. Your data directory and backups are unaffected.
