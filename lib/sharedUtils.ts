export async function runWithConcurrencyLimit(
  taskQueue: Array<() => Promise<void>>,
  limit: number
): Promise<void> {
  const workers = Array.from({ length: Math.min(limit, taskQueue.length) }, async () => {
    while (taskQueue.length > 0) {
      const task = taskQueue.shift();
      if (task) await task();
    }
  });

  await Promise.all(workers);
}
