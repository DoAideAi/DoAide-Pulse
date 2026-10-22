import { describe, expect, it } from "vitest";
import { STARTER_TEMPLATES } from "./starterTemplates";
import { nameProblem, undeclaredIn, unusedVariables } from "./templates";
import { CONTENT_TYPES } from "./triggers";

// Mirrors BUILTINS in app/services/templates.py.
const BUILTINS = [
  "project.name",
  "project.slug",
  "project.description",
  "project.url",
  "project.repo",
  "project.tech_stack",
  "date.today",
  "date.long",
  "date.year",
  "date.month",
  "signal.headline",
  "signal.summary",
  "signal.url",
  "signal.source",
  "signal.items",
].map((name) => ({ name, description: "" }));

describe.each(STARTER_TEMPLATES)("the $cadence starter", (starter) => {
  const declared = starter.variables.map((v) => v.name);

  it("references nothing the server would reject", () => {
    expect(
      undeclaredIn(declared, BUILTINS, starter.title_template, starter.body_template),
    ).toEqual([]);
  });

  it("declares nothing it doesn't use", () => {
    expect(unusedVariables(declared, starter.title_template, starter.body_template)).toEqual([]);
  });

  it("has valid variable names and a known content type", () => {
    declared.forEach((name, i) => {
      expect(nameProblem(name, BUILTINS, declared.filter((_, j) => j !== i))).toBeFalsy();
    });
    expect(CONTENT_TYPES).toContain(starter.content_type);
  });

  it("has no id, so saving creates a new template", () => {
    expect(starter.id).toBeUndefined();
  });
});
