import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import GettingStarted, { DISMISS_KEY, gettingStartedSteps } from "./GettingStarted";
import { ROUTER_FUTURE } from "../lib/routerFuture";

const fresh = { projectCount: 0, connectedCount: 0, contentCount: 0, publishedCount: 0 };

function draw(props) {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <GettingStarted {...props} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("gettingStartedSteps", () => {
  it("reads each step from the account's own data", () => {
    const steps = gettingStartedSteps({ ...fresh, projectCount: 1, contentCount: 2 });
    expect(steps.map((s) => s.done)).toEqual([true, false, true, false]);
  });

  it("treats destinations that are still loading as not connected", () => {
    const [, destination] = gettingStartedSteps({ ...fresh, connectedCount: null });
    expect(destination.done).toBe(false);
  });
});

describe("GettingStarted", () => {
  it("leads a new account to the first step", () => {
    draw(fresh);
    expect(screen.getByText("0 of 4 done")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add project" })).toHaveAttribute("href", "/projects");
    expect(screen.getByRole("link", { name: "Add project" }).className).toContain("btn-primary");
  });

  it("marks finished steps and moves the primary action to the next one", () => {
    draw({ ...fresh, projectCount: 1 });
    expect(screen.getByTestId("step-project")).toHaveAttribute("data-done", "true");
    expect(screen.queryByRole("link", { name: "Add project" })).toBeNull();
    expect(screen.getByRole("link", { name: "Connect" }).className).toContain("btn-primary");
    expect(screen.getByText("1 of 4 done")).toBeInTheDocument();
  });

  it("disappears once everything is done", () => {
    const { container } = draw({
      projectCount: 1,
      connectedCount: 1,
      contentCount: 1,
      publishedCount: 1,
    });
    expect(container).toBeEmptyDOMElement();
  });

  it("stays hidden after the user hides it", async () => {
    const { unmount } = draw(fresh);
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByText("Get your first post out")).toBeNull();
    expect(window.localStorage.getItem(DISMISS_KEY)).toBe("1");

    unmount();
    draw(fresh);
    expect(screen.queryByText("Get your first post out")).toBeNull();
  });
});
