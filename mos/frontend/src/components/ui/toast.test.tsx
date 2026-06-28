import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { toast, ToastProvider } from "./toast";

describe("ToastProvider", () => {
  const toastIds: string[] = [];

  afterEach(() => {
    act(() => {
      toastIds.splice(0).forEach((id) => toast.raw.close(id));
    });
  });

  it("renders success toasts as filled status surfaces", async () => {
    render(
      <ToastProvider>
        <div />
      </ToastProvider>,
    );

    await act(async () => {
      toastIds.push(
        toast.success({
          title: "LinkedIn campaign published",
          description: "Now reaching 12,400 followers.",
        }),
      );
      await Promise.resolve();
    });

    expect(await screen.findByText("LinkedIn campaign published")).toBeInTheDocument();
    expect(screen.getByText("Now reaching 12,400 followers.")).toBeInTheDocument();
    expect(document.querySelector('[data-type="success"]')).toHaveClass("bg-success");
  });

  it("centers title-only toast content vertically", async () => {
    render(
      <ToastProvider>
        <div />
      </ToastProvider>,
    );

    await act(async () => {
      toastIds.push(toast.success("Workspace created"));
      await Promise.resolve();
    });

    expect(await screen.findByText("Workspace created")).toBeInTheDocument();
    expect(document.querySelector('[data-type="success"] [class*="items-center"]')).not.toBeNull();
  });

  it("supports persistent loading toasts", async () => {
    render(
      <ToastProvider>
        <div />
      </ToastProvider>,
    );

    await act(async () => {
      toastIds.push(
        toast.loading({
          title: "Generating drafts...",
          description: "Reading your last 12 launches to match tone.",
        }),
      );
      await Promise.resolve();
    });

    expect(await screen.findByText("Generating drafts...")).toBeInTheDocument();
    expect(document.querySelector('[data-type="loading"]')).toHaveClass("bg-content");
  });
});
