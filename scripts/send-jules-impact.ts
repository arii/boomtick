import { sendJulesImpactReport } from '../lib/julesReviewClient';

async function main(): Promise<void> {
  const taskId = process.env.TASK_ID;
  if (!taskId) {
    console.log("No TASK_ID provided. Exiting.");
    return;
  }
  await sendJulesImpactReport(taskId);
}

main().catch(err => {
  console.error("Error sending Jules impact report:", err);
  process.exit(1);
});
