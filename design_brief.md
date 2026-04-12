# UI Design Brief: LinkedIn Saved Posts App

## 1. Product Overview

### Working concept

A LinkedIn-focused saved content app that helps users search, organise, review, and export their saved posts more effectively than LinkedIn’s native saved posts experience.

### Core value proposition

The product should feel like a personal knowledge library for professional content, rather than a social feed. It should help users:

- find saved posts quickly
- organise posts into meaningful structures
- review valuable content later
- export their saved content into their own systems or databases

### Product positioning

This should feel like:

- a modern bookmark manager
- a calm productivity tool
- a professional knowledge archive

The closest design reference is **Raindrop.io**, but adapted for text-heavy LinkedIn content and stronger retrieval workflows.

---

## 2. Visual Direction

### Design north star

Design the app like a calm, premium saved-knowledge workspace, taking cues from Raindrop’s clarity and structure, but optimised for text-heavy LinkedIn content, fast search, and professional organisation.

### Desired feel

- clean
- modern
- professional
- calm
- premium but simple
- search-first
- utility-led
- highly legible

### What the UI should not feel like

- a noisy social media feed
- a generic admin dashboard
- an overly corporate enterprise product
- a bright or overly playful consumer app
- a direct clone of LinkedIn’s native interface

### Reference influence

Primary inspiration:

- **Raindrop.io** for structure, clarity, sidebar behaviour, and saved-content browsing

Secondary feel:

- LinkedIn-native trust through use of blue, white, and familiar professional visual language
- modern SaaS/productivity app polish
- lightweight knowledge management / note-taking product cues

### Key interface qualities to borrow from Raindrop

- clear left-hand sidebar navigation
- clean list and card-based browsing
- strong spacing and low visual noise
- elegant filter and tag behaviour
- minimal but polished hierarchy
- soft use of colour rather than loud decoration

### Where the product should differ

The app should be more:

- text-centric
- metadata-rich
- search-driven
- archive-oriented
- built for professional retrieval and export

---

## 3. Colour Palette

### Core brand colours

- **LinkedIn Blue**: `#0A66C2`
- **Deep Action Blue**: `#004182`
- **White**: `#FFFFFF`

### UI neutrals

- **App Background**: `#F6F8FB`
- **Primary Surface**: `#FFFFFF`
- **Secondary Surface**: `#F1F5F9`
- **Border**: `#DCE6F0`
- **Divider**: `#E7EEF5`

### Typography colours

- **Primary Text**: `#162230`
- **Secondary Text**: `#5F6E7D`
- **Muted Text**: `#8895A3`

### Soft blue system tones

- **Blue Tint Background**: `#EAF4FF`
- **Blue Tint Hover**: `#DCEEFF`
- **Selected Item State**: `#D7E9FF`

### Functional colours

- **Success**: `#1E8E5A`
- **Warning**: `#C98512`
- **Error**: `#C23B3B`

### Recommended colour balance

Use roughly:

- 70% white and very light neutrals
- 20% soft tinted surfaces
- 10% accent and action colours

This keeps the interface airy, calm, and readable.

---

## 4. Typography and Style

### Typography direction

Use a modern sans-serif with strong readability and clean hierarchy.

### Tone of typography

- crisp
- editorial
- uncluttered
- professional

### Hierarchy guidance

- page titles should feel confident and spacious
- section headings should be clear and functional
- body text should be highly readable
- metadata should be visible but understated
- supporting information should be quieter, never dominant

### Styling principles

- generous whitespace
- rounded surfaces and cards
- subtle borders
- minimal shadows
- restrained icon usage
- strong alignment and spacing rhythm
- focus on scanability

---

## 5. Product UX Principles

### Primary UX principles

1. **Search first**

   - search should feel central to the product experience
   - users should always know where to search

2. **Organise without friction**

   - tagging, collections, and filtering should feel lightweight and fast

3. **Make text-heavy content easy to scan**

   - cards and lists should support quick recognition, not full reading

4. **Support later retrieval**

   - the product should feel built for “find that useful post from months ago”

5. **Make export feel natural**

   - exporting should feel like a core product value, not an afterthought

6. **Keep cognitive load low**
   - avoid clutter, over-decoration, or too many competing actions

---

## 6. Information Architecture

### Core navigation structure

Left sidebar:

- All Saved Posts
- Recent
- Collections
- Tags
- Authors
- Export
- Settings

Optional future additions:

- Highlights
- Notes
- Smart Collections
- Favourites / Pinned
- Synced / Exported status views

### Primary top-bar elements

- global search bar
- filter button or filter row
- view toggle
- sort dropdown
- profile/settings access

---

## 7. Main Pages

## 7.1 Home / Landing Page

### Purpose

Explain the value simply and get the user to connect/import their saved posts.

### Content

- concise headline
- one-line value proposition
- brief supporting explanation
- simple product preview
- primary CTA to connect or import
- optional trust/privacy reassurance

### Suggested messaging direction

Search, organise, and revisit your saved LinkedIn posts properly.

### Layout

- clean hero
- product screenshot/mockup
- short features section
- minimal footer

### Notes

This page should be light. The core product value is in the app itself, not marketing-heavy content.

---

## 7.2 Main Library Page

### Purpose

This is the core product experience.

### Main functions

- browse saved posts
- search saved posts
- filter by attributes
- move between collections
- open item detail
- take quick actions

### Layout structure

- left sidebar
- top search and controls
- main results area
- optional right-side preview panel on desktop

### Core UI blocks

- global search input
- filter chips / filter row
- sort control
- list/grid toggle
- saved post result cards
- pagination or infinite scroll
- optional quick-preview pane

### Recommended default view

A comfortable card-list hybrid rather than a pure image grid.

Why:

- LinkedIn posts are text-heavy
- users need preview content, author info, and metadata
- readability matters more than thumbnail density

---

## 7.3 Post Detail Page

### Purpose

Allow users to fully inspect, annotate, and act on a saved post.

### Content blocks

- author section
- source/original post link
- full saved content or extended preview
- metadata
- tags
- collection assignment
- personal notes
- export actions
- related posts or similar posts

### Metadata examples

- Author
- Company
- Date saved
- Original post date
- Content type
- Tags
- Export status

### Key behaviours

- easy tagging
- easy movement into collections
- note-taking
- one-click open original source
- export from detail view

---

## 7.4 Collections Page

### Purpose

Let users browse saved posts grouped into thematic buckets.

### Examples

- Marketing
- Career
- AI
- Product Ideas
- Leadership
- Writing
- Research

### Content

- collection list
- collection cards
- item counts
- create new collection action
- collection-specific filters and search

### Design note

Collections should feel useful and clean, not overcomplicated.

---

## 7.5 Authors Page

### Purpose

Help users retrieve saved posts by creator rather than keyword alone.

### Content

- author list
- avatar or placeholder
- author name
- organisation/company if available
- number of saved posts
- filter/search within authors

### Benefit

This adds strong retrieval value for professional content.

---

## 7.6 Tags Page

### Purpose

Support fast thematic browsing and filtering.

### Content

- tag list
- tag counts
- frequently used tags
- filter by tag
- tag management

### Design note

Tags should feel light and clean, likely using subtle pill styling.

---

## 7.7 Export / Integrations Page

### Purpose

Make export and ownership a visible differentiator.

### Content

- export options
- CSV export
- JSON export
- personal database/export integrations
- export history
- status indicators
- data control explanations

### Design note

This page can feel slightly more “power user” without becoming technical or intimidating.

---

## 7.8 Settings Page

### Purpose

Allow users to manage account, import behaviour, and data controls.

### Content

- account preferences
- sync/import settings
- privacy controls
- data retention/deletion
- export preferences
- notification settings if relevant later

---

## 8. Core Components

## 8.1 Sidebar

### Style

- pale neutral or white background
- subtle right border
- minimal icon set
- blue active state
- compact, tidy spacing

### Behaviour

- sticky on desktop
- collapsible for narrower screen widths

---

## 8.2 Search Bar

### Style

- prominent
- rounded rectangle
- white surface
- subtle border
- clear placeholder text
- LinkedIn blue focus state

### Suggested placeholder

Search posts, authors, keywords, and tags

### Behaviour

- always visible on primary app views
- should feel like the centre of the experience

---

## 8.3 Saved Post Cards

### Style

- white background
- 14px to 16px radius
- light border
- very subtle shadow or none
- generous internal spacing

### Content structure

- author line
- metadata line
- text preview
- tags
- action row

### Actions

- open
- tag
- add to collection
- export
- more menu

---

## 8.4 Tags

### Style

- pill format
- pale blue or light neutral fill
- subtle text contrast
- small and clean
- avoid bright multicolour usage

---

## 8.5 Buttons

### Primary

- filled LinkedIn blue
- white text
- dark blue hover

### Secondary

- white or pale surface
- subtle border
- dark text

### Tertiary

- text-only or low-emphasis surface hover

---

## 8.6 Filter Chips

### Style

- rounded pills
- neutral background by default
- blue tinted selected state

### Purpose

Help users quickly narrow results without overloading the interface

---

## 9. Wireframe Structure

## 9.1 Landing Page Wireframe

```text
------------------------------------------------------------
Top Nav
[Logo]                                      [Sign In]
------------------------------------------------------------

Hero Section
[Headline]
[Short supporting sentence]
[Primary CTA]   [Secondary CTA]

[Product mockup / screenshot]

------------------------------------------------------------
Feature Row
[Search saved posts]
[Organise with tags and collections]
[Export to your own database]

------------------------------------------------------------
Trust / Privacy Note
[Short reassurance about user data and exports]

------------------------------------------------------------
Footer
------------------------------------------------------------
```

## 9.2 Main Library Page Wireframe

```text
------------------------------------------------------------
| Sidebar        | Top Bar                                 |
|                | [Search..............................]  |
| All Saved      | [Filters] [Sort] [View Toggle]         |
| Recent         |----------------------------------------|
| Collections    |                                        |
| Tags           | Filter Chips Row                       |
| Authors        | [Author] [Date] [Tag] [Type] [...]     |
| Export         |                                        |
| Settings       |----------------------------------------|
|                |                                        |
|                | Result List / Card Area                |
|                | [Post Card]                            |
|                | [Post Card]                            |
|                | [Post Card]                            |
|                |                                        |
------------------------------------------------------------
```

## 9.3 Main Library with Preview Pane

```text
----------------------------------------------------------------------
| Sidebar        | Results Area                     | Preview Pane     |
|                |                                  |                  |
| All Saved      | [Search........................] | Selected Post    |
| Recent         | [Filters] [Sort]                | Author           |
| Collections    |----------------------------------| Metadata         |
| Tags           | [Post Card]                      | Preview text     |
| Authors        | [Post Card]                      | Tags             |
| Export         | [Post Card]                      | Actions          |
| Settings       |                                  |                  |
----------------------------------------------------------------------
```

## 9.4 Post Detail Page Wireframe

```text
------------------------------------------------------------
Top Bar
[Back]     [Search]                        [Actions Menu]
------------------------------------------------------------

Main Content Area

[Author / Source Block]
[Metadata Row]

[Full Post Content / Extended Preview]

[Tags]
[Collections]

[Notes Section]

[Export Actions]

[Related Posts]
------------------------------------------------------------
```

## 9.5 Collections Page Wireframe

```text
------------------------------------------------------------
Top Bar
[Collections]                     [Create Collection]
------------------------------------------------------------

[Search Collections]

------------------------------------------------------------
[Collection Card]   [Collection Card]   [Collection Card]
[Count]             [Count]             [Count]

[Collection Card]   [Collection Card]   [Collection Card]
------------------------------------------------------------
```

## 9.6 Export Page Wireframe

```text
------------------------------------------------------------
Top Bar
[Export & Integrations]
------------------------------------------------------------

Export Options
[CSV Export]
[JSON Export]
[Database / Integration Export]

------------------------------------------------------------
Export History
[Last export] [Status] [Format] [Destination]
[Last export] [Status] [Format] [Destination]
------------------------------------------------------------

Data Controls
[Retention]
[Delete Data]
[Permissions / Access]
------------------------------------------------------------
```

---

## 10. Interaction Notes

### Recommended default interaction patterns

- single-click open for items
- multi-filter browsing
- quick tag assignment
- quick move to collection
- search available globally
- export accessible both globally and per item

### Important usability goals

- users should understand the product within seconds
- users should be able to retrieve an old post quickly
- organisation should never feel like admin work
- the interface should support both casual browsing and intentional search

---

## 11. Future-Friendly Design Considerations

The design should leave room for future features such as:

- AI summaries of saved posts
- smart tagging
- semantic search
- duplicate detection
- note extraction
- highlights
- smart collections
- integrations with Notion, Airtable, or databases
- saved search views

The current interface should still feel simple even with those possibilities in mind.

---

## 12. Final Design Summary

The app should feel like a calm, premium, modern saved-content workspace inspired by Raindrop, but tailored specifically for LinkedIn posts and professional knowledge retrieval.

The UI should prioritise:

- search
- clarity
- organisation
- metadata
- readability
- exportability

It should be visually restrained, highly legible, and immediately useful.
