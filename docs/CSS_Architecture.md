# EdgeCase CSS Architecture

**Last Updated:** December 16, 2025

## Overview

EdgeCase uses a layered CSS architecture:

1. **shared.css** (~2,270 lines) - Common patterns used across multiple pages
2. **Page-specific CSS** - Styles unique to individual pages

All pages load shared.css via base.html, then their own CSS via `{% block extra_css %}`.

**Total CSS:** ~7,560 lines across 27 files

---

## shared.css Sections (~2,270 lines)

Organized into logical sections:

| Line | Section | What's in it |
|------|---------|--------------|
| 1 | CSS Custom Properties | Colors, shadows, spacing variables |
| 55 | Buttons | .btn, .btn-primary, .btn-secondary, .btn-danger, .btn-small |
| 155 | Icon Buttons | .btn-icon, .btn-icon-grey |
| 180 | Form Elements | Inputs, selects, textareas, labels |
| 280 | Date Input Group | .date-input-group |
| 305 | Form Layouts | .form-row, .form-row-thirds, .fee-grid, grids |
| 390 | Checkboxes | .checkbox-label, .checkbox-label-inline |
| 415 | Modals | .modal, .modal-overlay, .modal-content, .modal-box |
| 530 | Warning/Error Boxes | .warning-text, .warning-box, .error-box, .billed-warning |
| 605 | Cards | .card, .card-narrow, .card-wide, .empty-state-card |
| 630 | Section Dividers | .section-divider, .section-heading, .section-border-top |
| 655 | File Uploads | .upload-section, .attachment-*, .upload-form-* |
| 770 | Badges | .type-badge, .status-badge, .session-badge-*, .minor-badge |
| 820 | Text Utilities | .text-muted, .text-success, .text-danger, .text-income |
| 845 | Spacing Utilities | .mb-*, .mt-*, .pt-*, .ml-* |
| 870 | Max Width Utilities | .max-w-200, .max-w-300 |
| 880 | Flex Utilities | .flex, .flex-wrap, .flex-center-gap |
| 895 | Icon Utilities | .icon-xs/sm/md, colors, positioning |
| 950 | Page Header | .page-header, .header-row, .page-subtitle |
| 990 | Controls Bar | .controls-bar, .search-box, .filter-select |
| 1080 | Dropdown Menus | .dropdown-*, unified item styles |
| 1180 | Year/Month Timeline | .year-header, .month-header, expand/collapse |
| 1260 | Tables | table, thead, tbody, th, td |
| 1305 | Empty States | .empty-state, .placeholder-message |
| 1340 | Stats Cards | .stats-container, .stat-card, .category-* |
| 1400 | Form Sections | .form-section, .form-actions, .options-panel |
| 1470 | Client File Components | .client-header, .profile-*, .linked-*, .contact-* |
| 1580 | Legend Dots | .legend-dot variants |
| 1590 | Progress Bar | .progress-bar-container, .progress-bar-fill |
| 1615 | Footer & Misc | .footer-section, .about-link, status text |
| 1650 | Choices.js Overrides | Custom styling for Choices.js dropdowns |

---

## Icon Sizing (Standardized)

```css
.icon-xs { width: 14px; height: 14px; }
.icon-sm { width: 16px; height: 16px; }
.icon-md { width: 20px; height: 20px; }
```

---

## Spacing Utilities (CSS Variables)

```css
/* Uses CSS custom properties for consistency */
.mb-1 { margin-bottom: var(--space-lg); }   /* 1rem */
.mb-2 { margin-bottom: var(--space-xl); }   /* 1.5rem */
.mt-1 { margin-top: var(--space-lg); }      /* 1rem */
.mt-2 { margin-top: var(--space-2xl); }     /* 2rem */
```

---

## Page-Specific CSS Files

### Large Files (100+ lines)
| File | Lines | Page | Notes |
|------|-------|------|-------|
| main_view.css | ~758 | Client list | Filters, client cards, retention modal |
| backups.css | ~611 | Backup settings | Backup cards, progress bars |
| outstanding_statements.css | ~402 | Billing | Statement cards, payment UI |
| add_edit_link_group.css | ~413 | Link groups | Member selection, fee allocation |
| pickers.css | ~321 | Date/time pickers | Custom picker components |
| ai_scribe.css | ~293 | AI Scribe | Modal and streaming UI |
| profile.css | ~291 | Profile entry | Contact fields, guardian billing |
| manage_links.css | ~237 | Link management | Link group list |
| add_edit_type.css | ~172 | Client types | Color picker, type form |
| ledger_report.css | ~170 | Financial report | Report form, preview |
| session.css | ~168 | Session entry | Session form, AI button |
| ledger.css | ~158 | Income/Expense | Ledger table, filters |
| upload.css | ~135 | Upload entry | File upload UI |
| schedule_form.css | ~123 | Calendar scheduling | Schedule form |
| manage_types.css | ~116 | Types table | Types list |
| expense.css | ~116 | Expense entry | Expense form |
| settings.css | ~115 | Settings page | Settings sections |
| export.css | ~114 | Export entries | Export options |
| communication.css | ~103 | Communication | Communication form |

### Small Files (<100 lines)
| File | Lines | Notes |
|------|-------|-------|
| client_file.css | ~99 | Client timeline |
| absence.css | ~98 | Absence entry |
| income.css | ~97 | Income entry |
| item.css | ~87 | Item entry |
| deleted_clients.css | ~67 | Deleted clients view |
| add_client.css | ~25 | New client form |
| choices.min.css | - | Choices.js library (minified) |

---

## Where to Put New Styles

**Use shared.css for:**
- Buttons, form inputs, modals
- Any pattern used on 3+ pages
- Base table styling
- Common badges/status indicators
- Utility classes

**Use page-specific CSS for:**
- Layouts unique to that page
- Page-specific cards or sections
- Overrides of shared patterns

**Naming conventions:**
- `.btn-*` for buttons
- `.form-*` for form elements
- `.*-badge` for badges
- `.*-card` for card components
- Page prefix for unique items (e.g., `.retention-item` in main_view.css)

---

## Common Patterns

### Standard Button
```css
.btn                 /* Base button (teal) */
.btn-primary         /* Teal action button */
.btn-secondary       /* Grey button */
.btn-danger          /* Red destructive action */
.btn-small, .btn-sm  /* Smaller button (38px height) */
.btn-icon            /* Icon-only button (teal) */
.btn-icon-grey       /* Icon-only button (grey) */
```

### Controls Bar (search + filters)
```css
.controls-bar        /* Flex container */
.controls-left       /* Left side with search + filter */
.controls-actions    /* Right side actions */
.search-box          /* Search input container */
.filter-select       /* Dropdown filter */
```

### Dropdown Menu
```css
.dropdown-container  /* Wrapper with position:relative */
.dropdown-btn        /* Trigger button */
.dropdown-menu       /* Hidden menu */
.dropdown-item       /* Menu item (unified style) */
```

### Form Section
```css
.form-section        /* Bordered container */
.form-section label  /* Section labels */
.form-actions        /* Bottom button row */
```

### Modal
```css
.modal-overlay       /* Full-screen backdrop */
.modal-content       /* White box */
.modal-box           /* Alternative naming */
.modal-title         /* Heading */
.modal-actions       /* Button row */
```

---

## Entry Type Badges

```css
.session-badge-communication  /* Purple */
.session-badge-absence        /* Rose */
.session-badge-item           /* Amber */
.session-badge-upload         /* Blue */
```

---

## Inline CSS (Templates)

Some templates have inline `<style>` blocks that must stay:
- **base.html** - Font declarations (uses Jinja url_for)
- **login.html** - Font declarations (uses Jinja url_for)
- **change_password.html** - Font declarations (uses Jinja url_for)

The font declarations cannot be moved to external CSS because they use Jinja's `url_for()` function.

---

## Consolidation History

**December 6, 2025:**
- Reduced shared.css from 2,583 → 2,006 lines (-22%)
- Removed 31 unused selectors
- Fixed icon size conflicts
- Fixed margin utility conflicts
- Merged duplicate dropdown styles
- Merged duplicate badge definitions
- Consolidated modal styles
- Organized into logical sections

**December 16, 2025:**
- Documentation refresh with accurate line counts
- Total CSS now ~7,560 lines (growth from feature additions)
