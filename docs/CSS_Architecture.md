# EdgeCase CSS Architecture

**Last Updated:** December 1, 2025

## Overview

EdgeCase uses a layered CSS architecture:

1. **shared.css** (1,180 lines) - Common patterns used across multiple pages
2. **Page-specific CSS** - Styles unique to individual pages

All pages load shared.css via base.html, then their own CSS via `{% block extra_css %}`.

**Total CSS:** 4,641 lines across 24 files

---

## shared.css Sections (1,180 lines)

| Line | Section | What's in it |
|------|---------|--------------|
| 4 | CSS Custom Properties | Color variables (:root) |
| 47 | Buttons | .btn, .btn-primary, .btn-secondary, .btn-danger, .btn-add |
| 170 | Form Elements | Inputs, selects, textareas, labels |
| 275 | Date Input Group | .date-input-group, .date-select |
| 306 | Form Layouts | .form-group, .form-row |
| 387 | Checkboxes | Custom styled checkboxes |
| 425 | Modals | .modal, .modal-content, .modal-actions |
| 469 | Cards | .card, .card-header |
| 495 | Section Dividers | .section-divider |
| 580 | File Uploads | .attachment-*, file upload styling |
| 616 | Badges | .badge, .badge-* variants |
| 626 | Utility Classes | .text-muted, .sr-only, etc. |
| 682 | Session-Specific | Legacy compatibility |
| 730 | Year/Month Timeline | .year-group, .month-group |
| 775 | Table Base | table, thead, tbody, th, td |
| 818 | Empty State | .empty-state |
| 916 | Dropdown Buttons | .dropdown-container, .dropdown-btn, .dropdown-menu |
| 989 | Error/Success Messages | .error-message, .success-message |
| 1012 | Controls Bar | .controls-bar, .search-box, .filter-select |
| 1074 | Icon Buttons | .btn-icon, .btn-icon-grey |
| 1087 | Status Badges | .status-badge with variants |
| 1122 | Page Header Row | .header-row |
| 1140 | Form Sections | .form-section |
| 1150 | Form Actions | .form-actions |
| 1156 | Stats Cards | .stats-container, .stat-card |

---

## Page-Specific CSS Files

### Large Files (100+ lines)
| File | Lines | Page | Notes |
|------|-------|------|-------|
| main_view.css | 645 | Client list | Filters, client cards, retention modal |
| backups.css | 563 | Backup settings | Backup cards, progress bars |
| outstanding_statements.css | 429 | Billing | Statement cards, payment UI |
| add_edit_link_group.css | 330 | Link groups | Member selection, fee allocation |
| manage_links.css | 189 | Link management | Link group list |
| ledger_report.css | 171 | Financial report | Report form, preview |
| ledger.css | 166 | Income/Expense | Ledger table, filters |
| export.css | 153 | Export entries | Export options |
| add_edit_type.css | 128 | Client types | Color picker, type form |
| client_file.css | 99 | Client timeline | Entry list, profile card |

### Small Files (<100 lines)
| File | Lines | Notes |
|------|-------|-------|
| settings.css | 86 | Settings page |
| profile.css | 78 | Profile entry form |
| expense.css | 72 | Expense entry |
| deleted_clients.css | 67 | Deleted clients view |
| manage_types.css | 65 | Types table |
| schedule_form.css | 61 | Calendar scheduling |
| upload.css | 57 | Upload entry |
| add_client.css | 25 | New client form |
| session.css | 22 | Session entry |
| absence.css | 21 | Absence entry |
| communication.css | 17 | Communication entry |
| income.css | 9 | Income entry |
| item.css | 8 | Item entry |

---

## Where to Put New Styles

**Use shared.css for:**
- Buttons, form inputs, modals
- Any pattern used on 3+ pages
- Base table styling
- Common badges/status indicators

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
/* In shared.css - use these classes */
.btn                 /* Base button */
.btn-primary         /* Teal action button */
.btn-secondary       /* Grey button */
.btn-danger          /* Red destructive action */
.btn-add             /* Teal "Add" button */
.btn-icon            /* Icon-only button (teal) */
.btn-icon-grey       /* Icon-only button (grey) */
```

### Controls Bar (search + filters)
```css
.controls-bar        /* Flex container */
.controls-left       /* Left side with search + filter */
.search-box          /* Search input container */
.filter-select       /* Dropdown filter */
```

### Dropdown Menu
```css
.dropdown-container  /* Wrapper with position:relative */
.dropdown-btn        /* Trigger button */
.dropdown-menu       /* Hidden menu */
.dropdown-item       /* Menu item (link or button) */
```

### Form Section
```css
.form-section        /* Bordered container */
.form-section h3     /* Section title */
.form-actions        /* Bottom button row */
```

---

## Inline CSS (Templates)

Some templates still have inline `<style>` blocks:
- **base.html** - Font declarations (must stay - uses Jinja url_for)
- **login.html** - Font declarations (same reason)
- **change_password.html** - Font declarations (same reason)
- **settings.html** - Minor styles
- **edit_history.html** - Component styles

The font declarations cannot be moved to external CSS because they use Jinja's `url_for()` function.
