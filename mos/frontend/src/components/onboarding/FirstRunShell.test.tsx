import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ContextPreviewPanel,
  FirstRunShell,
  OnboardingProgressRail,
  ReviewChangesPanel,
  SetupChecklist,
} from "./index";

describe("first-run onboarding primitives", () => {
  it("renders a split shell with rail, task, and context slots", () => {
    render(
      <FirstRunShell
        progressRail={<OnboardingProgressRail current={2} total={5} label="Setup progress" />}
        title="Brand source"
        description="Focused setup step"
        context={
          <ContextPreviewPanel
            title="Setup context"
            workspaceSummary={[{ label: "Workspace", value: "Real workspace" }]}
            checklist={[{ id: "configured", label: "Configured", status: "done" }]}
            blockers={["Missing source"]}
          />
        }
      >
        <button type="button">Continue</button>
      </FirstRunShell>,
    );

    expect(screen.getAllByRole("progressbar", { name: "Setup progress" })[0]).toHaveAttribute("aria-valuenow", "40");
    expect(screen.getByRole("heading", { name: "Brand source" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Setup context" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
  });

  it("renders setup and review state primitives without synthetic source data", () => {
    render(
      <div>
        <SetupChecklist
          title="Setup status"
          items={[
            { id: "done", label: "Configured", status: "done" },
            { id: "blocked", label: "Source blocked", status: "blocked", details: "Connect a real source." },
          ]}
        />
        <ReviewChangesPanel
          title="Review changes"
          items={[
            { id: "added", label: "Workspace profile", status: "added" },
            { id: "missing", label: "Proof asset", status: "missing" },
          ]}
        />
      </div>,
    );

    expect(screen.getByText("Configured")).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Workspace profile")).toBeInTheDocument();
    expect(screen.getByText("Proof asset")).toBeInTheDocument();
  });
});
