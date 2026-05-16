# EdgeCase Equalizer - Changelog

All notable changes after the initial v1.0 release (March 2026) are documented here.

Format: Each entry includes date, version (if applicable), and description.

---

## [Unreleased]

### 2026-05-16
- **AI Scribe**: Refined Cancel button presentation. Removed the inline "Generating..." status indicator (which was causing column-width reflow) and replaced it with a dedicated Cancel button styled to match the action buttons, placed below them in the same column. Uses `visibility: hidden` to reserve layout space so action buttons no longer jump when Cancel appears or disappears.
- **AI Scribe**: Converted the "Loading AI model..." banner from an inline element to a centered modal overlay with dimmed backdrop. Previously the banner pushed page content down when shown and let it snap back when hidden; the overlay is now `position: fixed` so it never affects layout. The overlay also better reflects the actual user state — the page is unusable until the model loads.

### 2026-05-15
- **AI Scribe**: Added Cancel button to abort in-flight generation. Uses `AbortController` to terminate the SSE stream cleanly, releasing the model so a new action can be started immediately. Previously, hitting the bottom "Cancel" link navigated away but left the generation running on the backend, causing subsequent requests to hang waiting for the model lock.
- **AI Scribe**: Fixed pre-existing bug where the "Generating..." status indicator never appeared. The JS was using `classList.remove('hidden')` to show the status div, but the div was hidden via inline `style="display: none;"` and no `.hidden` CSS class exists. Switched to direct inline style manipulation.
- **AI Scribe**: Renamed bottom "Cancel" link to "Back" with standard styling (left-arrow icon, plain `.btn` class) to match the Back button convention used throughout the rest of the app.

### 2026-04-10
- **Security**: Added `Cache-Control: no-store` headers to attachment viewing and download endpoints. Prevents browsers from caching decrypted attachment content to disk. Decrypted attachments now exist only in memory during viewing/download.

### 2026-04-01
- **Scheduler**: Fixed natural language date parsing to prioritize explicit dates over day-of-week names. Previously, "Thursday April 9" would be interpreted as "next Thursday" (ignoring the explicit date). Now explicit month+day patterns are checked first, with day-of-week as a fallback.

### 2026-03-28
- **Scheduler**: Fixed AppleScript calendar integration failing when Calendar.app is not already running. The AppleScript now explicitly launches Calendar before attempting to create events, preventing the "Application isn't running" (-600) error.

### 2026-03-23
- **AI Scribe**: Updated system prompt to preserve clinician's language choices including profanity, slang, and colloquialisms. Previously, the model would sometimes substitute euphemisms (e.g., changing "shit" to "defecate") when proofreading notes that reflected client language. The prompt now explicitly instructs the model to respect the therapist's clinical judgment about what language to include.

---

## [1.0.0] - 2026-03-11
Initial public release.
