/** A copy of `list` with the item at `from` moved to `to`.
 *
 *  Out-of-range or no-op moves return the same array, so a caller can pass the
 *  result straight to state without causing a re-render for a drop that went
 *  nowhere. */
export function moveItem(list, from, to) {
  if (
    !Array.isArray(list) ||
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= list.length ||
    to >= list.length
  ) {
    return list;
  }
  const next = list.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}
