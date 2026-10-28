import { useState } from "react";
import { Link } from "react-router-dom";
import ShareButtons from "../../components/ShareButtons";
import PublicNav from "../../components/PublicNav";
import DoAideFooter from "../../components/DoAideFooter";
import trackEvent from "../../lib/trackEvent";
import { usePageMeta } from "../../lib/pageMeta";
import { PUBLIC_ROUTE_META } from "../../data/publicRouteMeta";

const INDUSTRIES = {
  Tech: [
    { day: "Tuesday", hour: 10 },
    { day: "Thursday", hour: 14 },
  ],
  "E-commerce": [
    { day: "Tuesday", hour: 10 },
    { day: "Saturday", hour: 10 },
  ],
  Finance: [
    { day: "Wednesday", hour: 9 },
    { day: "Thursday", hour: 9 },
  ],
  Health: [
    { day: "Monday", hour: 8 },
    { day: "Wednesday", hour: 10 },
  ],
  Education: [
    { day: "Tuesday", hour: 9 },
    { day: "Thursday", hour: 11 },
  ],
  Media: [
    { day: "Monday", hour: 6 },
    { day: "Thursday", hour: 16 },
  ],
  SaaS: [
    { day: "Tuesday", hour: 11 },
    { day: "Wednesday", hour: 14 },
  ],
  Other: [
    { day: "Tuesday", hour: 10 },
    { day: "Thursday", hour: 10 },
  ],
};

const TZ_OFFSETS = {
  IST: 5.5,
  EST: -5,
  PST: -8,
  GMT: 0,
  CET: 1,
  AEST: 10,
};

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

// The industry figures are the audience's own clock — "Tuesday 10 AM" means
// 10 AM where the readers are, whichever zone that is. They used to be shifted
// as if they were IST, so a PST audience was told to send at 8:30 PM, and a
// shift past midnight kept the original day. The recommendation now stays in
// the audience's time; the IST line underneath is when to press send from
// India, with the day moved when the conversion crosses midnight.
function inIst(day, hour, tz) {
  const shifted = hour + (TZ_OFFSETS.IST - TZ_OFFSETS[tz]);
  const dayShift = Math.floor(shifted / 24);
  const index = (DAYS.indexOf(day) + dayShift + DAYS.length) % DAYS.length;
  return { day: DAYS[index], hour: shifted - dayShift * 24 };
}

function formatHour(h) {
  const whole = Math.floor(h);
  const min = h % 1 === 0.5 ? "30" : "00";
  const ampm = whole >= 12 ? "PM" : "AM";
  const display = whole === 0 ? 12 : whole > 12 ? whole - 12 : whole;
  return `${display}:${min} ${ampm}`;
}

function buildHeatmap(slots) {
  const map = {};
  for (const d of DAYS) map[d] = 0;
  for (const s of slots) map[s.day] = Math.max(map[s.day], 1);
  return DAYS.map((d) => ({ day: d, intensity: map[d] }));
}

export default function SendTimeOptimizer() {
  const [industry, setIndustry] = useState("Tech");
  const [tz, setTz] = useState("IST");

  usePageMeta(PUBLIC_ROUTE_META["/tools/send-time-optimizer"]);

  const slots = INDUSTRIES[industry];
  const heatmap = buildHeatmap(slots);

  return (
    <div className="min-h-screen bg-canvas text-ink-700">
      <PublicNav />

      <main id="main" tabIndex={-1} className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="page-title mb-2">Send Time Optimizer</h1>
        <p className="mb-6 text-ink-500">
          Find the best days and times to send your newsletter by industry and timezone.
        </p>

        <div className="panel p-5 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="industry" className="label">
                Industry
              </label>
              <select
                id="industry"
                className="input"
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
              >
                {Object.keys(INDUSTRIES).map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="tz" className="label">
                Audience timezone
              </label>
              <select
                id="tz"
                className="input"
                value={tz}
                onChange={(e) => setTz(e.target.value)}
              >
                {Object.keys(TZ_OFFSETS).map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="mt-6 space-y-4">
          <h2 className="text-sm font-semibold text-ink-900">Recommended send times</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {slots.map((s, i) => {
              const ist = inIst(s.day, s.hour, tz);
              return (
                <div key={i} className="panel p-4" data-testid="time-slot">
                  <div className="text-lg font-semibold text-ink-900">{s.day}</div>
                  <div className="text-brand-500 font-medium" data-testid="time-display">
                    {formatHour(s.hour)}
                  </div>
                  <div className="text-xs text-ink-400">{tz} — your audience's time</div>
                  {tz !== "IST" && (
                    <div className="mt-1 text-xs text-ink-500" data-testid="ist-display">
                      {ist.day} {formatHour(ist.hour)} IST
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-6">
          <h2 className="mb-3 text-sm font-semibold text-ink-900">Weekly heatmap</h2>
          <div className="flex gap-1.5" data-testid="heatmap">
            {heatmap.map((d) => (
              <div key={d.day} className="flex-1 text-center">
                <div
                  className={`mx-auto mb-1 h-8 rounded ${
                    d.intensity > 0
                      ? "bg-brand-500"
                      : "bg-ink-400/10"
                  }`}
                  title={d.day}
                />
                <div className="text-[10px] text-ink-400">{d.day.slice(0, 3)}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel mt-10 p-5 text-center">
          <p className="mb-3 text-ink-900">
            Let Pulse learn when your own posts do best, and schedule for it.
          </p>
          <Link to="/" className="btn-primary" onClick={() => trackEvent("cta-click", { source: "tool-sendtime" })}>
            Try DoAide Pulse
          </Link>
        </div>

        <div className="mt-6">
          <ShareButtons text="Find the best time to send your newsletter — free tool by DoAide Pulse" />
        </div>
      </main>

      <DoAideFooter />
    </div>
  );
}
