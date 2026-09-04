# EdgeCase Equalizer 2.0.2

A maintenance release with three fixes worth reading about before you upgrade,
plus two new features.

## Please read: two privacy fixes and a broken compliance feature

These affect every 2.0.x install. Nothing here requires action beyond
upgrading, but you should know what changed and why.

**Generated statement PDFs were stored under filenames containing the client
file number.** A statement saved to a client's file was written to disk as
`Statement_<file_number>_<date>.pdf`. The file contents were always
encrypted and were never at risk. The filename was not, and filenames travel:
they appear in backup archives (a backup's contents are encrypted, but a ZIP's
index of filenames is readable without a password), in cloud-sync folders, and
in search indexes. Depending on your file-number scheme this could disclose
client initials, intake dates, or — if you use client names as file numbers —
names. Uploaded attachments were never affected; they have always been stored
under random names.

Upgrading renames existing files automatically on first launch and updates
the records that point at them. **Backups already written keep the old
names.** If your backups sync to cloud storage and your file numbers contain
identifying information, consider taking a fresh backup after upgrading and
removing older ones once you're satisfied with the new restore point.

**Financial reports and payment records were left unencrypted in the system
temporary directory.** Generating either wrote a PDF — client name, file
number, payment history, in the clear — to the shared temp directory under a
predictable name, and never deleted it. On systems where that directory is
world-readable (`/tmp` on many setups), the document stayed readable by any
process or user on the machine until the operating system's cleaner removed
it, typically after some days. Reports are now rendered into a private,
randomly-named, owner-only directory that is deleted as soon as the file
reaches you.

**Retention deletion has not worked since 9 August 2026.** Disposing of a
client at the end of their retention period failed for any client who had
ever made a payment — in practice, all of them. The operation reported
failure and deleted nothing; no data was lost or partially removed. The cause
was a table added during the August payment-allocation work that the disposal
path was never told about. If you have attempted a disposal since that date
and it did not complete, it will work now.

## New: two-note system

Session entries can carry a second **Reflections** field for your own process
notes, alongside the clinical note. Off by default; enable it in
Settings › Note-Taking.

Reflections are stored with the session — so they are covered by encryption,
backup, retention and disposal like everything else — and are excluded from
client file exports and reports.

**They are not privileged.** Ontario has no equivalent of the US
psychotherapy-notes exemption. A PHIPA access request, a College
investigation, or a production order can reach process notes, and the
obligation to disclose that a second set exists rests with you. EdgeCase
treats the field the way a separate notebook behaves: it keeps them out of
routine exports. It does not make the disclosure decision for you.

Turning the setting off hides the field. It does not delete anything;
existing reflections remain in the record and reappear if you turn it back
on.

## New: insurance provider numbers

Settings › Insurance Providers holds a provider number for each network you
belong to, with the printed line in whatever format your insurer wants. Assign
one to a client on their profile, and their statements and payment record
carry it. Clients with no insurer are unaffected, and the business financial
report never carries a provider number.

## Also in this release

- **Master-key rotation** (Settings › Security). Changing your password or
  issuing a new recovery key replaces a wrapper; the key underneath does not
  change. That means neither operation revokes anything against someone
  holding an old backup *and* your old password. Rotation mints a fresh master
  key, re-encrypts every attachment, and rebuilds the database, after which
  every earlier key file, password and recovery key opens nothing current.
  It runs at your next login, behind a progress screen, and issues a new
  recovery key. It does not retroactively protect backups taken before it: a
  pre-rotation backup remains a complete snapshot that still opens with the
  old password, by design.
- **Ledger ordering.** Entries made on the same day now sort by when you
  entered them, consistently. Previously a payment recorded after a manually
  keyed expense could appear before it.
- **Startup checks** report attachment problems once rather than at every
  launch, and again whenever the situation changes.

## Verifying your download

Checksums are published on the download page and in the release assets. Two
independent sources for the same hash is what makes checking worthwhile.
