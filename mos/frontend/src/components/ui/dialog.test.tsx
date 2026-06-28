import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "./alert-dialog";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "./dialog";

describe("modal primitives", () => {
  it("gives standard dialog descriptions readable default rhythm", () => {
    render(
      <DialogRoot open>
        <DialogContent>
          <DialogTitle>Dialog title</DialogTitle>
          <DialogDescription>Dialog description copy.</DialogDescription>
        </DialogContent>
      </DialogRoot>,
    );

    expect(screen.getByText("Dialog description copy.")).toHaveClass("mt-2", "leading-normal");
  });

  it("gives alert dialog descriptions readable default rhythm", () => {
    render(
      <AlertDialog open>
        <AlertDialogContent>
          <AlertDialogTitle>Delete workspace</AlertDialogTitle>
          <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
        </AlertDialogContent>
      </AlertDialog>,
    );

    expect(screen.getByText("This cannot be undone.")).toHaveClass("mt-2", "leading-normal");
  });
});
