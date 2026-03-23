# Security

## Reporting a Vulnerability

If you discover a security vulnerability in EdgeCase Equalizer, please report it responsibly by emailing the author directly. Please include a description of the issue, steps to reproduce, and any relevant details.

Do not open a public GitHub issue for security vulnerabilities.

## Security Architecture

EdgeCase Equalizer is designed as a **local-only, single-user** application for solo therapy practitioners. This architecture eliminates entire categories of risk common to cloud-based and multi-user systems.

### Threat Model

**What EdgeCase protects against:**

- Unauthorized access to client data at rest (SQLCipher encryption)
- Session hijacking on the local machine (configurable idle timeout, default 30 minutes)
- Accidental data loss (automated backup system with full and incremental backups)
- Backup tampering (zip integrity verification on every backup)
- Data exposure on shared networks (binds to 127.0.0.1 only — not accessible from other devices)
- CSRF attacks (Flask-WTF CSRF protection on all forms)
- Brute-force login attempts (progressive lockout after failed attempts)

**What is out of scope:**

- Physical access to an unlocked, logged-in machine (use your OS screen lock)
- Compromised operating system or malware on the host machine
- Lost or forgotten passphrase (data is irrecoverable by design — there is no backdoor)

### Encryption

- **Database:** SQLCipher (AES-256-CBC) encrypts all client data at rest. The database file is unreadable without the correct passphrase.
- **Key derivation:** SQLCipher internally derives the encryption key from the user's passphrase using PBKDF2-HMAC-SHA512 with 256,000 iterations (SQLCipher 4 defaults). No custom key derivation code is used — this is handled entirely by the proven SQLCipher library.
- **Flask session key:** Generated uniquely per installation using `os.urandom(24)`, stored in `data/.secret_key` with 0600 permissions (owner read/write only). Supports environment variable override for advanced users.
- **No plaintext secrets:** Neither the database passphrase nor any derived keys are stored in the codebase or configuration files. The SECRET_KEY and salt are generated at runtime on first launch.

### Network Exposure

- The application binds exclusively to `127.0.0.1` (localhost)
- It is **not accessible** from other devices on the local network
- No data is transmitted over the internet during normal operation
- The optional AI Scribe feature uses a local LLM (Hermes 3 8B) running on the same machine — no data is sent to external AI services

### Session Security

- Configurable idle timeout (default: 30 minutes, adjustable in Settings, with a "Never" option)
- Maximum cookie lifetime: 24 hours regardless of activity
- Session cookie flags: `HttpOnly=True`, `SameSite=Lax`
- `SESSION_COOKIE_SECURE` is set to `False` because the app runs over HTTP on localhost — there is no TLS to validate against. Setting this to `True` would break the application.
- Server-side session invalidation on logout
- Automatic backup triggered on session expiry and logout
- WAL checkpoint before all backup operations to ensure database consistency

### Backup System

- Full and incremental backups with zip integrity verification
- Pre-restore safety backups created automatically before any restore operation
- Configurable backup frequency and retention policies
- Support for local and cloud backup locations (iCloud, Dropbox, Google Drive, OneDrive)
- Backups contain the encrypted database file — the user's passphrase is required to restore and access the data

### Data Handling

- Soft deletes throughout (clinical records are never permanently removed from the database)
- Edit history tracked for session notes
- No telemetry, analytics, or usage data collection
- No external network calls during normal operation

## PHIPA Compliance

EdgeCase Equalizer is designed to make compliance with Ontario's *Personal Health Information Protection Act* (PHIPA) straightforward for solo practitioners. Whether a given practice is PHIPA-compliant depends on how the software is used — just as compliance with paper-based or Word document records depends on how those are used. EdgeCase provides the technical infrastructure to support compliance; the practitioner is responsible for using it in a compliant way.

**What EdgeCase provides:**

- **Data sovereignty:** All personal health information remains on the practitioner's own hardware. No cloud accounts, no third-party data processors, no cross-border transfers — this simplifies PHIPA obligations considerably.
- **Encryption at rest:** SQLCipher (AES-256) encrypts the database; Fernet encryption protects file attachments. Encrypted data on a local machine provides stronger protection than unencrypted digital or paper records.
- **Access control:** Single-user authentication with configurable idle timeout. Only the practitioner can access records.
- **Immutable clinical records:** Session notes, communications, and other clinical entries are locked after creation. Changes are tracked with a full edit history showing exactly what was changed and when. Clinical records are retained throughout the active life of a client file and are never deleted during the retention period. When the retention period expires, records can be permanently removed, leaving only a minimal archive stub (name, file number, first and last contact dates). A separate redaction mechanism allows free-text content to be cleared from individual entries in the event of a privacy incident, while preserving the structural record.
- **Record export:** Client records can be exported to PDF for access requests or transfers.
- **Backup and recovery:** Full and incremental backups support data integrity and availability requirements.

**What the practitioner is responsible for:**

- Obtaining informed consent for collection and use of personal health information
- Setting appropriate retention periods (Ontario regulations require a minimum of 10 years after last service for most records; longer for records involving minors)
- Secure physical access to the device running EdgeCase
- Breach identification and notification procedures
- Secure destruction of backups when retention periods expire

EdgeCase is not a multi-user system and does not include role-based access controls or audit logging of record views — consistent with the single-practitioner context it is designed for.

## Dependencies

EdgeCase uses well-established, actively maintained libraries. Key security-relevant dependencies:

| Library | Purpose |
|---------|---------|
| **SQLCipher** (via sqlcipher3) | AES-256 database encryption |
| **Flask-WTF** | CSRF protection on all forms |
| **cryptography** | Cryptographic operations |
| **Waitress** | Production WSGI server (no debug mode exposure) |

## License

EdgeCase Equalizer is open source under the AGPL-3.0 license. Security review and contributions are welcome.
