# EdgeCase Equalizer - Changelog

All notable changes after the initial v1.0 release (March 2026) are documented here.

Format: Each entry includes date, version (if applicable), and description.

---

## [Unreleased]

### 2026-03-28
- **Scheduler**: Fixed AppleScript calendar integration failing when Calendar.app is not already running. The AppleScript now explicitly launches Calendar before attempting to create events, preventing the "Application isn't running" (-600) error.

### 2026-03-23
- **AI Scribe**: Updated system prompt to preserve clinician's language choices including profanity, slang, and colloquialisms. Previously, the model would sometimes substitute euphemisms (e.g., changing "shit" to "defecate") when proofreading notes that reflected client language. The prompt now explicitly instructs the model to respect the therapist's clinical judgment about what language to include.

---

## [1.0.0] - 2026-03-11
Initial public release.
