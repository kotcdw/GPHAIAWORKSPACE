"""Workflow engine, work items (the "Projects" inbox) and the SLA clock.

* Every status change of a tracked record is recorded as a transition (``workflow_transitions``), checked against
  the record type's workflow definition. Definitions ship matching today's behaviour; admins customise them later.
* Every hand-off is a work item with an assignee and a working-day due date (``work_items``), derived from the
  records themselves, so the inbox can never drift from the work.
* The SLA clock warns the assignee before the due date and escalates when it passes.
"""
