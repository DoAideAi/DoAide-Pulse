import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import LandingPage from "./LandingPage";

const auth = vi.hoisted(() => ({ login: vi.fn(), register: vi.fn() }));

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    login: auth.login,
    register: auth.register,
  }),
}));

const wrap = () =>
  render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  );

describe("LandingPage", () => {
  describe("comparison table", () => {
    it("renders the comparison section header", () => {
      wrap();
      expect(screen.getByText("Why creators choose Pulse")).toBeInTheDocument();
    });

    it("shows platform column headers", () => {
      wrap();
      const table = screen.getByRole("table");
      expect(table).toBeInTheDocument();
      expect(table.textContent).toContain("Mailchimp");
      expect(table.textContent).toContain("Substack");
    });

    it("shows feature rows in the comparison table", () => {
      wrap();
      const table = screen.getByRole("table");
      expect(table.textContent).toContain("Send time optimization");
      expect(table.textContent).toContain("Built for India");
      expect(table.textContent).toContain("Custom domain");
    });
  });

  describe("pricing section", () => {
    it("renders the pricing section header", () => {
      wrap();
      expect(screen.getByText("Simple, transparent pricing")).toBeInTheDocument();
    });

    it("shows all three tier names", () => {
      wrap();
      expect(screen.getByText("Pro")).toBeInTheDocument();
      expect(screen.getByText("Business")).toBeInTheDocument();
    });

    it("shows tier prices", () => {
      wrap();
      expect(screen.getByText("999")).toBeInTheDocument();
      expect(screen.getByText("2,999")).toBeInTheDocument();
    });

    it("shows the Pro tier with a highlight class", () => {
      wrap();
      const proCard = screen.getByText("Pro").closest(".landing-pricing-card");
      expect(proCard).toHaveClass("landing-pricing-highlight");
    });

    it("lists features for each tier", () => {
      wrap();
      expect(screen.getByText("Unlimited subscribers")).toBeInTheDocument();
      expect(screen.getByText("Advanced analytics dashboard")).toBeInTheDocument();
      expect(screen.getByText("Dedicated IP")).toBeInTheDocument();
    });
  });

  describe("analytics mockup", () => {
    it("renders the analytics preview", () => {
      wrap();
      expect(screen.getByText("See what your audience does")).toBeInTheDocument();
    });
  });

  describe("no fabricated social proof", () => {
    it("has no fabricated testimonials", () => {
      wrap();
      expect(screen.queryByText(/Trusted by newsletter creators/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Priya S\./)).not.toBeInTheDocument();
    });

    it("has no fabricated usage counters", () => {
      wrap();
      expect(screen.queryByText(/Newsletters sent/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Avg open rate/)).not.toBeInTheDocument();
    });
  });

  describe("sign in", () => {
    // The reset flow had a backend and an email and no way in from here.
    it("offers a way back in to someone who forgot their password", () => {
      wrap();
      expect(screen.getByRole("link", { name: "Forgot your password?" })).toHaveAttribute(
        "href",
        "/reset-password",
      );
    });

    it("does not offer it while creating an account", () => {
      wrap();
      fireEvent.click(screen.getByRole("tab", { name: "Create account" }));
      expect(screen.queryByRole("link", { name: "Forgot your password?" })).not.toBeInTheDocument();
    });
  });

  describe("an invite-only install", () => {
    afterEach(() => {
      auth.register.mockReset();
      window.history.replaceState(null, "", "/");
    });

    const fill = () => {
      fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
      fireEvent.change(screen.getByLabelText("Password"), { target: { value: "long-enough-pw" } });
    };

    it("takes the code from an invite link, opens on sign-up and sends it", async () => {
      window.history.replaceState(null, "", "/?invite=welcome-42");
      auth.register.mockResolvedValue(undefined);
      wrap();

      expect(window.location.search).toBe("");
      expect(screen.getByLabelText("Invite code")).toHaveValue("welcome-42");
      fill();
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));
      });

      await vi.waitFor(() =>
        expect(auth.register).toHaveBeenCalledWith(
          "new@example.com",
          "long-enough-pw",
          null,
          "welcome-42",
        ),
      );
    });

    it("asks for the code once the server says it wants one, instead of a dead end", async () => {
      auth.register.mockRejectedValueOnce(
        new Error("That invite code is not right. Check it against the one you were sent."),
      );
      wrap();
      fireEvent.click(screen.getByRole("tab", { name: "Create account" }));
      expect(screen.queryByLabelText("Invite code")).not.toBeInTheDocument();

      fill();
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));
      });
      const field = await screen.findByLabelText("Invite code");

      auth.register.mockResolvedValueOnce(undefined);
      fireEvent.change(field, { target: { value: "from-the-operator" } });
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));
      });
      await vi.waitFor(() =>
        expect(auth.register).toHaveBeenLastCalledWith(
          "new@example.com",
          "long-enough-pw",
          null,
          "from-the-operator",
        ),
      );
    });
  });

  describe("after a session ends mid-use", () => {
    afterEach(() => window.sessionStorage.clear());

    it("says why the user is back at sign-in, once", () => {
      window.sessionStorage.setItem("pulse:session-ended", "1");
      const { unmount } = wrap();

      expect(screen.getByRole("status")).toHaveTextContent("Your session has ended");
      expect(window.sessionStorage.getItem("pulse:session-ended")).toBeNull();
      unmount();

      wrap();
      expect(screen.queryByText(/Your session has ended/)).not.toBeInTheDocument();
    });
  });
});
