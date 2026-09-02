# Weekly Feedback App Backlog

## 1. Set up an empty Django project with a passing test
Goal: Create a minimal Django project that installs, starts, and has one passing automated test.
Description: Initialize the Django project and feedback app, add the app to `INSTALLED_APPS`, and document the local setup commands. Add a basic smoke test that verifies the test environment works, then confirm `python manage.py test` passes.

## 2. Create the project and weekly feedback data models
Goal: Store projects, weekly feedback cycles, and anonymous responses in the database.
Description: Define models for a project, its assigned leads, a time-bounded feedback cycle, and a response containing a 1–5 score and optional comment. Add migrations plus model tests covering validation, relationships, and cycle open/closed behavior.

## 3. Build the public feedback form
Goal: Let a participant submit anonymous feedback through a cycle-specific public link.
Description: Create a route, form, view, and responsive template that display the project name, a 1–5 health score, an optional comment, and a concise privacy note. Validate submissions and test successful input as well as missing or invalid scores.

## 4. Enforce feedback-cycle availability
Goal: Accept responses only while the linked weekly feedback cycle is open.
Description: Check the cycle's opening and closing timestamps before displaying or processing its form. Provide clear empty, unavailable, and closed states, with tests for active, future, expired, missing, and inactive-project cycles.

## 5. Prevent duplicate anonymous responses
Goal: Limit a participant to one response per weekly cycle without recording raw identifying data.
Description: Hash the request network address and an anonymous device identifier using a server-side salt, then store only those hashes. Add database constraints, duplicate-response screens, a secure device cookie, and tests for repeat network and device submissions.

## 6. Add sign-in and project-level authorization
Goal: Restrict internal results so administrators see all projects and leads see only assigned projects.
Description: Configure username-and-password authentication and protect every internal dashboard route. Implement a reusable project visibility rule and test anonymous redirects, lead access, cross-project denial, and administrator access.

## 7. Build the signed-in project list dashboard
Goal: Give each authorized user a summary of the active projects they may view.
Description: Display each visible project's name, total response count, and average health score, with links to detailed results. Include an informative empty state and tests ensuring the displayed projects and aggregate values follow role permissions.

## 8. Build the project results dashboard
Goal: Show authorized users the latest weekly results for one project.
Description: Present the cycle dates, response count, average score, 1–5 score distribution, and anonymous comments in a readable responsive page. Handle projects without cycles or responses and test calculations, ordering, empty states, and access restrictions.

## 9. Add Django admin management for projects and cycles
Goal: Allow administrators to manage projects, lead assignments, and feedback cycles without custom management screens.
Description: Register the relevant models in Django admin with useful columns, filters, search fields, and date controls. Verify that staff users can perform the intended operations while ordinary project leads cannot access administrative management.

## 10. Create reproducible demonstration data
Goal: Let a new developer populate a working demo environment with one command.
Description: Add an idempotent management command that creates an administrator, a project lead, sample projects, open and closed cycles, and representative responses. Document the demo credentials and public link, and test that running the command repeatedly does not duplicate its core records.

## 11. Improve accessibility and responsive presentation
Goal: Make public and internal pages usable with keyboards, screen readers, and small screens.
Description: Review templates for semantic headings, explicit labels, focus visibility, error announcements, color contrast, and logical keyboard order. Verify key pages at common mobile and desktop widths and record a short manual accessibility checklist.

## 12. Document setup, operation, privacy, and current limitations
Goal: Give developers and reviewers one reliable guide to running and understanding the MVP.
Description: Update the README with prerequisites, installation, migrations, demo seeding, server and test commands, roles, and primary routes. Explain what anonymous metadata is hashed, the MVP's security assumptions, and deferred features such as automatic scheduling, QR codes, and CSV/PDF exports.
