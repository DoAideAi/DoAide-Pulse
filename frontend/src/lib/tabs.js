/**
 * The keyboard half of `role="tablist"`, for lists whose tabs are buttons.
 *
 * Four tab lists said role="tab" and behaved like a row of buttons: every tab
 * a separate Tab stop, and the arrow keys a screen reader announces ("tab, 1
 * of 2") doing nothing. The pattern is one stop — the selected tab — with the
 * arrows, Home and End moving between them. Selection follows focus, which is
 * right here because every one of these switches instantly and locally.
 */
const MOVES = {
  ArrowRight: (i, n) => (i + 1) % n,
  ArrowDown: (i, n) => (i + 1) % n,
  ArrowLeft: (i, n) => (i - 1 + n) % n,
  ArrowUp: (i, n) => (i - 1 + n) % n,
  Home: () => 0,
  End: (_, n) => n - 1,
};

/** Put on each tab: only the selected one is reachable with Tab. */
export function tabProps(selected) {
  return { "aria-selected": selected, tabIndex: selected ? 0 : -1 };
}

/** Put on the `role="tablist"` element. Moves focus and clicks the new tab. */
export function onTabListKeyDown(event) {
  const move = MOVES[event.key];
  if (!move) return;
  const tabs = [...event.currentTarget.querySelectorAll('[role="tab"]:not([disabled])')];
  const current = tabs.indexOf(event.target.closest('[role="tab"]'));
  if (current === -1 || tabs.length === 0) return;
  event.preventDefault();
  const next = tabs[move(current, tabs.length)];
  next.focus();
  next.click();
}
