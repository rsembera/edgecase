# EdgeCase Equalizer

Practice management software for independent therapists.

**Status:** Production ready. In use as of January 2026.

## Features

- Client records with encrypted database (SQLCipher)
- Session notes, communications, billing items
- PDF invoice generation with payment tracking
- Guardian billing for minor clients
- Couples/family/group therapy support
- Calendar integration (.ics export, Apple Calendar)
- Full backup/restore system
- Local AI assistant for session notes (optional)

## Requirements

- Python 3.11 or higher
- macOS, Linux, or Windows

### macOS

```bash
brew install sqlcipher
```

### Linux (Debian/Ubuntu)

```bash
sudo apt install sqlcipher libsqlcipher-dev
```

### Windows

SQLCipher installation on Windows requires additional steps. See [sqlcipher3-wheels documentation](https://github.com/niccokunzmann/sqlcipher3-wheels).

## Installation

```bash
git clone https://github.com/rsembera/edgecase.git
cd edgecase
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

### With AI features (optional)

```bash
pip install -e ".[ai]"
```

## Running

```bash
python main.py
```

Then open http://localhost:8080 in your browser.

### Development mode (auto-reload)

```bash
python main.py --dev
```

## License

GNU Affero General Public License v3.0 (AGPL-3.0)

This ensures EdgeCase remains free software for therapists while preventing proprietary SaaS derivatives.

## Author

Richard Sembera
