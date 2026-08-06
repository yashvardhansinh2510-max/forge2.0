/**
 * Shared quotation persistence primitive.
 *
 * Both quotation presentations may schedule a save while an earlier request
 * is still in flight. Keeping the queue here makes the ordering guarantee a
 * property of the quotation system rather than of one particular builder.
 */
export type PersistQueue<T> = { current: Promise<T> };

export function enqueueQuotationPersist<T>(
  queue: PersistQueue<T>,
  run: () => Promise<T>,
): Promise<T> {
  const queued = queue.current.then(run, run);
  queue.current = queued.then(() => null as T, () => null as T);
  return queued;
}
