import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import AnalyticsMockup from "./AnalyticsMockup";

const wrap = () =>
  render(
    <MemoryRouter>
      <AnalyticsMockup />
    </MemoryRouter>,
  );

describe("AnalyticsMockup", () => {
  it("renders the four stat cards, all metrics Pulse reports", () => {
    wrap();
    expect(screen.getByText("Views")).toBeInTheDocument();
    expect(screen.getByText("Read to the end")).toBeInTheDocument();
    expect(screen.getByText("Click-through")).toBeInTheDocument();
    expect(screen.getByText("Subscribers")).toBeInTheDocument();
  });

  it("never shows a metric Pulse does not measure", () => {
    const { container } = wrap();
    expect(container.textContent).not.toMatch(/open rate|opens|bounce/i);
  });

  it("says the numbers are a sample", () => {
    wrap();
    expect(screen.getByText("Sample data")).toBeInTheDocument();
  });

  it("renders chart section titles", () => {
    wrap();
    expect(screen.getByText("Views this week")).toBeInTheDocument();
    expect(screen.getByText("Subscriber growth")).toBeInTheDocument();
  });

  it("shows upgrade CTA", () => {
    wrap();
    expect(screen.getByText(/Start free/)).toBeInTheDocument();
  });

  it("renders day labels for the bar chart", () => {
    wrap();
    expect(screen.getByText("Mon")).toBeInTheDocument();
    expect(screen.getByText("Fri")).toBeInTheDocument();
    expect(screen.getByText("Sun")).toBeInTheDocument();
  });
});
