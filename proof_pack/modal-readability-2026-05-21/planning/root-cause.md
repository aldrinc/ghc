# Root Cause Diagnosis

Root cause: modal header rhythm is not owned by the design-system primitive.

Why chain:

1. The screenshot is hard to read because the title and body copy touch too closely.
2. They touch because `AlertDialogDescription` has no default top spacing.
3. That exists because modal primitives separate type styling from layout rhythm.
4. Call sites compensate manually, but not consistently.
5. The system lacks a default modal anatomy fixture that makes this regression obvious.

System flaw: layout responsibility is in the wrong layer.

