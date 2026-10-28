// Every public page has a <main id="main"> for the skip link in PublicNav to
// land on. The signed-in shell supplied one; the pages outside it had none, so
// there was no landmark to jump to and nothing for the skip link to target.
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ api: { generateContentIdeas: vi.fn() } }));

import Blog from "./Blog";
import Embed from "./Embed";
import NewsletterGallery from "./NewsletterGallery";
import TemplatesGallery from "./TemplatesGallery";
import ContentIdeaGenerator from "./tools/ContentIdeaGenerator";
import NewsletterRoiCalculator from "./tools/NewsletterRoiCalculator";
import SendTimeOptimizer from "./tools/SendTimeOptimizer";
import SubjectLineTester from "./tools/SubjectLineTester";

const PAGES = {
  Blog,
  Embed,
  NewsletterGallery,
  TemplatesGallery,
  ContentIdeaGenerator,
  NewsletterRoiCalculator,
  SendTimeOptimizer,
  SubjectLineTester,
};

describe.each(Object.entries(PAGES))("%s", (_name, Page) => {
  it("has one main landmark that the skip link points at", () => {
    render(
      <MemoryRouter>
        <Page />
      </MemoryRouter>,
    );
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "main");
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute(
      "href",
      "#main",
    );
  });
});
