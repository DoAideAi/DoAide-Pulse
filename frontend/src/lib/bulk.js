// The most ids one bulk request takes (BulkContentIn ``max_length=100``).
// A selection or a queue can be longer than that, and one request naming more
// is a 422 that approves none of them.
export const BULK_LIMIT = 100;

/**
 * Run a bulk action over any number of ids, at most BULK_LIMIT per request,
 * and add the answers together. `key` is the list of ids that worked, which
 * approve and reject name differently.
 */
export async function inBatches(ids, action, key) {
  const merged = { [key]: [], failed: [] };
  for (let i = 0; i < ids.length; i += BULK_LIMIT) {
    const result = await action(ids.slice(i, i + BULK_LIMIT));
    merged[key].push(...(result?.[key] ?? []));
    merged.failed.push(...(result?.failed ?? []));
  }
  return merged;
}
