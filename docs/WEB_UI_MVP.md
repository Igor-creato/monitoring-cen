# Web UI MVP

## Fastest stack for FastAPI

- Server-rendered Jinja2 templates mounted directly in FastAPI.
- Plain CSS in `backend/app/web/static/app.css`.
- Tiny progressive JS for loading state on submitted forms.
- HTML forms over POST/redirect/GET; no SPA, no bundler, no client routing.

This keeps deployment simple: one FastAPI process can serve API, pages, and static assets.

## Screen Structure

- `/register` and `/login`: authentication forms with server-side validation and HTTP-only JWT cookie.
- `/monitors`: responsive list, status filter, summary counters, empty state.
- `/monitors/new`: create form with URL, target price, interval, notification channel.
- `/monitors/{id}`: monitor card, current values, editable settings, recent price checks, delete action.
- `/monitors/{id}/history`: full price history table with success/error states.
- `/profile`: account details and default notification settings for new monitors.

## UI States

- Loading: forms with `data-loading` disable submit buttons and show a spinner.
- Empty: monitor list and history have explicit empty states with next action.
- Error: form validation and persistence failures render visible alert blocks.

## Validation

Validation is intentionally duplicated at the right layers:

- Browser hints: `type=email`, `type=url`, `required`, `minlength`, `maxlength`.
- Server validation: existing Pydantic request schemas are reused by web form handlers.
- Domain validation: marketplace URL normalization and ownership checks stay in services/repositories.

## Production Notes

- Auth token is stored in an HTTP-only `SameSite=Lax` cookie.
- State-changing forms include a signed CSRF token.
- Templates do not bypass service ownership checks.
- User notification defaults are persisted in the `users` table.
