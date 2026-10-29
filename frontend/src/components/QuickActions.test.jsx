import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import QuickActions from "./QuickActions";
import { api } from "../lib/api";
import { ROUTER_FUTURE } from "../lib/routerFuture";

vi.mock("../lib/api", () => ({
  api: {
    reviewQueuePage: vi.fn(),
    bulkApprove: vi.fn(),
  },
}));

const toast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock("./ui/Toast", () => ({ useToast: () => toast }));

function draw(props = {}) {
  return render(
    <MemoryRouter future={ROUTER_FUTURE}>
      <QuickActions reviewCount={0} onApproved={() => {}} {...props} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("QuickActions", () => {
  it("renders the toolbar with generate and published buttons", () => {
    draw();

    expect(screen.getByRole("toolbar", { name: "Quick actions" })).toBeInTheDocument();
    expect(screen.getByTitle("Generate new content")).toBeInTheDocument();
    expect(screen.getByTitle("View published content")).toBeInTheDocument();
    expect(screen.getByTitle("Settings")).toBeInTheDocument();
  });

  it("does not show approve button when reviewCount is 0", () => {
    draw({ reviewCount: 0 });

    expect(screen.queryByTitle(/Approve all/)).not.toBeInTheDocument();
  });

  it("shows approve button with count when items are in review", () => {
    draw({ reviewCount: 5 });

    expect(screen.getByTitle("Approve all 5 reviews")).toBeInTheDocument();
  });

  it("calls bulkApprove with all review queue IDs when clicked", async () => {
    api.reviewQueuePage.mockResolvedValue({
      items: [{ id: 1 }, { id: 2 }, { id: 3 }],
      total: 3,
    });
    api.bulkApprove.mockResolvedValue({ succeeded: [1, 2, 3], failed: [] });

    const onApproved = vi.fn();
    draw({ reviewCount: 3, onApproved });

    await userEvent.click(screen.getByTitle("Approve all 3 reviews"));

    expect(api.reviewQueuePage).toHaveBeenCalled();
    await vi.waitFor(() => {
      expect(api.bulkApprove).toHaveBeenCalledWith([1, 2, 3]);
    });
  });

  it("has 48px minimum touch targets on all interactive elements", () => {
    draw({ reviewCount: 2 });

    const buttons = screen.getAllByRole("button");
    const links = screen.getAllByRole("link");
    [...buttons, ...links].forEach((el) => {
      expect(el.className).toContain("quick-action-btn");
    });
  });
});

describe("a queue longer than a page", () => {
  it("approves every piece waiting, not the first page of them", async () => {
    // 150 waiting: the queue pages at 200 at most, and a bulk approve takes
    // at most 100 ids, so this is one read and two approvals.
    const waiting = Array.from({ length: 150 }, (_, i) => ({ id: i + 1 }));
    api.reviewQueuePage.mockImplementation(async ({ limit, offset }) => ({
      items: waiting.slice(offset, offset + limit),
      total: waiting.length,
    }));
    api.bulkApprove.mockImplementation(async (ids) => ({ succeeded: ids, failed: [] }));
    draw({ reviewCount: 150 });

    await userEvent.click(screen.getByTitle("Approve all 150 reviews"));

    await vi.waitFor(() => expect(api.bulkApprove).toHaveBeenCalledTimes(2));
    expect(api.bulkApprove.mock.calls.flatMap(([ids]) => ids)).toEqual(
      waiting.map((w) => w.id),
    );
    expect(api.bulkApprove.mock.calls.every(([ids]) => ids.length <= 100)).toBe(true);
    expect(toast.success).toHaveBeenCalledWith("Approved 150 items");
  });

  it("reads past the first page when the queue is longer than one read", async () => {
    const waiting = Array.from({ length: 250 }, (_, i) => ({ id: i + 1 }));
    api.reviewQueuePage.mockImplementation(async ({ limit, offset }) => ({
      items: waiting.slice(offset, offset + limit),
      total: waiting.length,
    }));
    api.bulkApprove.mockImplementation(async (ids) => ({ succeeded: ids, failed: [] }));
    draw({ reviewCount: 250 });

    await userEvent.click(screen.getByTitle("Approve all 250 reviews"));

    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith("Approved 250 items"));
    expect(api.reviewQueuePage).toHaveBeenCalledWith({ limit: 200, offset: 200 });
  });
});
