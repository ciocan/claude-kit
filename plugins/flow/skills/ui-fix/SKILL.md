---
name: ui-fix
description: Fix a layout, spacing, alignment or wording defect reported from a screenshot, in place on the current branch, and check it at phone and desktop widths in both themes. Use when the user posts a screenshot or image with a visual complaint, lists small visual changes to a page, or asks to adjust landing or product copy.
---

# UI fix from a screenshot

## Scope

- Fix it here, on the current branch and worktree. No issue, branch or PR unless the user asks.
- A list of points gets one commit per point when the user asks for commits.
- Fix the cause. When the defect sits in a shared component, look at its other uses before
  changing it.

## Building the fix

- Colours, spacing and type come from the repository's design tokens and its design document
  (`DESIGN.md` or the theme file). Never hardcode a colour.
- Use a component the repository already has before writing one. Then look in the component
  registry the project uses. Write a new one last.
- External links open in a new tab.
- Error messages shown to users never expose infrastructure: no host names, no stack traces, no
  provider names. Show your own identifiers, never the ids of an external system.

## Checking it

- Small and large screens, light and dark theme.
- The browser console stays free of errors and hydration warnings.
- Take an after screenshot. For a PR, take before and after.
- Run the check on your own port. Never restart the user's dev server.

## Copy

- Translated text reads the way a native speaker would write it. Rewrite word-for-word
  translations.
- Interface text is in the product's language. Code, comments, test titles and commit messages are
  in English.
- Sales and landing pages say how the product works now. No dates of changes, no "now supports",
  no account of what used to be different. A date that says when a figure was measured can stay.
- Never name internal tools or link to private trackers from a public page.
- A feature that is not built is marked as coming soon and gets an issue.
- After changing one passage, find the similar ones on the site and bring them in line.

## Before building something new

For a new page or a redesign, show two or three variants first, as an artifact or a mock, when the
user asks to see it beforehand. Colour changes stay within the brand's hue family unless the user
asks for a new direction.
