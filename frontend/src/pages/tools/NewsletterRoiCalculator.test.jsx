import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import NewsletterRoiCalculator from "./NewsletterRoiCalculator";

const wrap = () =>
  render(
    <MemoryRouter>
      <NewsletterRoiCalculator />
    </MemoryRouter>,
  );

describe("NewsletterRoiCalculator", () => {
  it("renders all input fields", () => {
    wrap();
    expect(screen.getByLabelText(/subscribers/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/open rate/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/click rate/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/conversion rate/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/revenue per conversion/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/monthly cost/i)).toBeInTheDocument();
  });

  it("calculates ROI with default values", () => {
    wrap();
    const roi = screen.getByTestId("roi");
    expect(roi.textContent).toMatch(/%/);
  });

  it("shows no ROI rather than 0% when the newsletter costs nothing", async () => {
    wrap();
    const cost = screen.getByLabelText(/monthly cost/i);
    await userEvent.clear(cost);
    await userEvent.type(cost, "0");
    const roi = screen.getByTestId("roi");
    expect(roi.textContent).toBe("—");
    expect(roi.className).not.toMatch(/text-good|text-bad/);
  });

  it("shows annual projection", () => {
    wrap();
    const annual = screen.getByTestId("annual");
    expect(annual.textContent).toMatch(/^₹/);
  });

  it("shows correct opens for default values", () => {
    wrap();
    const opens = screen.getByTestId("opens");
    expect(opens.textContent).toBe("1,750");
  });

  it("clamps negative inputs to zero instead of producing negative revenue", async () => {
    const { container } = wrap();
    const subsInput = screen.getByLabelText(/subscribers/i);
    // fireEvent.change is more reliable than userEvent.type for number inputs in jsdom
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(subsInput, { target: { value: "-100" } });
    const revenue = screen.getByTestId("revenue");
    expect(revenue.textContent).toBe("₹0");
  });

  it("answers in rupees, grouped the Indian way, like the pricing it sits beside", () => {
    wrap();
    expect(screen.getByLabelText(/revenue per conversion \(₹\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/monthly cost \(₹\)/i)).toBeInTheDocument();
    const subs = screen.getByLabelText(/subscribers/i);
    // 1,00,000 readers × 100% × 100% × 100% × ₹500 = ₹5,00,00,000 a month.
    fireEvent.change(subs, { target: { value: "100000" } });
    for (const label of [/open rate/i, /click rate/i, /conversion rate/i]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: "100" } });
    }
    expect(screen.getByTestId("opens").textContent).toBe("1,00,000");
    expect(screen.getByTestId("revenue").textContent).toBe("₹5,00,00,000");
    expect(document.body.textContent).not.toMatch(/\$/);
  });

  it("clamps rates above 100 to 100", async () => {
    wrap();
    const openInput = screen.getByLabelText(/open rate/i);
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(openInput, { target: { value: "150" } });
    const opens = screen.getByTestId("opens");
    const opensValue = Number(opens.textContent.replace(/,/g, ""));
    expect(opensValue).toBeLessThanOrEqual(5000);
  });
});
