# EdgeCase Equalizer - Security Overview

EdgeCase Equalizer is designed with privacy and data protection as core principles. This document describes the security measures in place.

## Encryption

### Database Encryption (SQLCipher)

The database uses **SQLCipher** for transparent AES-256 encryption at rest. All client data, session notes, billing records, and settings are encrypted with your master password.

- **Algorithm:** AES-256 in CBC mode
- **Key derivation:** PBKDF2-HMAC-SHA512 with 256,000 iterations
- **Page size:** 4096 bytes with 16-byte HMAC

The database file (`data/edgecase.db`) is unreadable without the correct password.

### Attachment Encryption (Fernet)

All file attachments (uploaded documents, logos, signatures) are encrypted using **Fernet** (AES-128-CBC with HMAC-SHA256).

- **Algorithm:** AES-128 in CBC mode with PKCS7 padding
- **Authentication:** HMAC-SHA256
- **Key derivation:** PBKDF2-HMAC-SHA256 with 480,000 iterations
- **Salt:** Unique per-installation, stored in `data/.salt`

Files are encrypted on upload and decrypted only when accessed through the application.

## Authentication

### Master Password

- Minimum 8 characters required
- Used to derive both database and attachment encryption keys
- Never stored—only the encrypted database validates it
- Can be changed via Settings (re-encrypts all files)

### Session Management

- Configurable session timeout (15, 30, 60, 120 minutes, or never)
- Sessions stored server-side with secure cookies
- Automatic logout after inactivity
- Client-side activity tracking with keepalive

## Data Storage

### Local-Only Architecture

EdgeCase stores all data locally on your machine:

- **No cloud sync** by default
- **No external API calls** (except optional AI model download)
- **No telemetry or analytics**
- You control where backups are stored

### File Locations

| Data | Location | Encrypted |
|------|----------|-----------|
| Database | `data/edgecase.db` | Yes (SQLCipher) |
| Attachments | `attachments/` | Yes (Fernet) |
| Logo/Signature | `assets/` | Yes (Fernet) |
| Backups | `backups/` or custom | Yes (contains encrypted files) |
| Encryption salt | `data/.salt` | N/A (random bytes) |
| Session key | `data/.secret_key` | N/A (random bytes) |

### Backup Security

Backups contain encrypted files—they remain encrypted in the backup. The backup ZIP itself is not additionally encrypted, but the contents require your master password to read.

**Important:** Backups include `data/.salt` and `data/.secret_key`, which are required to decrypt attachments and maintain sessions after restore.

## Network Security

### Default Configuration

EdgeCase runs on `localhost:8080` by default, accessible only from your machine.

### Local Network Access

When accessed via local network (e.g., from iPad on same WiFi), traffic is unencrypted HTTP. For sensitive deployments:

1. Use a reverse proxy (nginx) with TLS
2. Restrict access to trusted networks
3. Consider VPN for remote access

### Not Recommended

EdgeCase is designed for local/trusted network use. Exposing it to the public internet is **not recommended** without:

- TLS encryption (HTTPS)
- Firewall rules
- Additional authentication layer
- Regular security updates

## Audit Trail

### Edit History

Clinical records (sessions, communications, absences) maintain an immutable edit history:

- Original content preserved
- All changes timestamped
- Word-level diff tracking
- Entries lock after first save

This supports PHIPA compliance requirements for healthcare record-keeping.

### Archived Clients

When clients are deleted after retention period expiry, minimal audit information is preserved:

- File number
- Full name
- First/last contact dates
- Deletion timestamp

## Security Best Practices

### For Users

1. **Choose a strong master password** (12+ characters recommended)
2. **Enable session timeout** appropriate for your environment
3. **Store backups securely** (encrypted drive or trusted cloud folder)
4. **Keep the application updated** for security fixes
5. **Lock your computer** when stepping away

### For Developers

1. All user input is parameterized in SQL queries
2. Jinja2 autoescaping prevents XSS in templates
3. File uploads use `secure_filename()` sanitization
4. Session cookies use `HttpOnly` and `SameSite=Lax`

## Reporting Security Issues

If you discover a security vulnerability, please report it privately:

1. **Do not** open a public GitHub issue
2. Email the maintainer directly
3. Allow reasonable time for a fix before disclosure

## Compliance Notes

EdgeCase is designed to support PHIPA (Personal Health Information Protection Act) compliance for Ontario healthcare providers:

- Encrypted storage of personal health information
- Audit trails for record modifications
- Configurable retention periods
- Access logging via session management

**Note:** Software alone does not guarantee compliance. Ensure your overall practice policies and procedures meet regulatory requirements.

---

*Last updated: December 2025*
