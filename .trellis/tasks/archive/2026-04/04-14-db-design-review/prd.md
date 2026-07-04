# Review Database Design against Sentiance Docs

## Goal
Review the database schema defined in `Entregable.md` to ensure it accurately and completely represents the Sentiance SDK entities, events, and insights based on the official documentation stored in `scraped_site/`.

## Requirements
- [ ] Read and understand the current DB design in `Entregable.md`.
- [ ] Scan `scraped_site/` for relevant Sentiance SDK documentation (Events, Insights, User data, etc.).
- [ ] Identify discrepancies or missing fields/entities in the current design.
- [ ] Provide a detailed report of findings and suggested improvements.

## Acceptance Criteria
- [ ] All primary Sentiance data points (as per docs) are accounted for in the schema.
- [ ] Data types and relationships in the schema align with the documentation's event/insight structures.
- [ ] Any missing "must-have" Sentiance attributes are identified.

## Technical Notes
- Follow Sentiance naming conventions where applicable.
- Ground all findings in local documentation files in `scraped_site/`.
