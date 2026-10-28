# 0005: References from log-like rows are `ON DELETE SET NULL` foreign keys

## Context
Some rows are records of something that happened: a trigger firing, an idea
that was written up, a revision's author. They point at a piece or a user that
the user may later delete, and the record must outlive it. The first
implementation of each used a plain integer column with no constraint, on that
reasoning.

## Decision
Use a real foreign key with `ON DELETE SET NULL`, and index it. The record
survives the delete; its reference becomes NULL instead of an id that points
nowhere. A migration that adds one first clears ids that already dangle, or
PostgreSQL refuses the constraint.

## Consequences
- No dangling ids. These had real symptoms: ideas that vanished from every
  list because their dead draft id made them look used, and trigger events whose
  "View piece" link went to a 404.
- Code reading these columns must treat NULL as "the thing was deleted".
- The index matters: without it, every delete of the parent scans the child
  table to null its references.

## Rejected
- **A plain integer column:** the original choice. It leaves dangling ids, and
  SQLite ids can even be reused.
- **`ON DELETE CASCADE`:** loses the record, which is the thing being kept.

## In the code
`content_ideas.used_content_id` (`j0l2g4i6k8m0`),
`trigger_events.content_id` (`p5r7t9v1x3z5`),
`content_revisions.author_user_id`, `subscribers.project_id`.
`tests/test_the_schema_has_the_indexes_its_queries_need.py` requires every
foreign key to be indexed.
