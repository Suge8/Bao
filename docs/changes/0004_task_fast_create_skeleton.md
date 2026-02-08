# 0004 Task Fast Create Skeleton

[FEAT] 2026-02-08 Task Fast Create Interaction Skeleton

## Summary

Established the "Fast Create" interaction skeleton for the Tasks page, allowing users to describe tasks via natural language or simple schedule options, while keeping advanced configurations in a collapsible section.

## Details

1.  **UI Changes**:
    -   Introduced a "Fast Path" section at the top of the create form.
    -   Added a natural language input textarea with AI source label placeholder.
    -   Added simplified "Once" / "Interval" schedule toggle.
    -   Moved existing full form fields into a "Advanced Settings" collapsible section (using `framer-motion` for smooth transition).
    -   Added visual cues for "Field Source Labels" (placeholder).

2.  **i18n**:
    -   Added `tasks.fast_create.*` keys for new UI elements.

3.  **Tests**:
    -   Added E2E test case verifying the presence of fast create inputs and the toggle behavior of the advanced section.

## Impact

-   **User Experience**: Reduces cognitive load by hiding complex configurations by default, encouraging natural language input.
-   **Architecture**: Prepares the frontend for future AI-driven task drafting (NL -> structured spec).

## Next Steps

-   Implement the actual NL parsing logic to populate the form fields.
-   Connect the "Fast Path" inputs to the backend or use them to draft the task spec.
