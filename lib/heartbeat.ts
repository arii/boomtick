import * as fs from 'fs';
import * as path from 'path';
import { randomUUID } from 'node:crypto';

const LOG_DIR = path.join(process.cwd(), '.boomtick', 'logs', 'ai');

/**
 * Writes a heartbeat log entry to a unique file.
 * This prevents race conditions during concurrent writes from parallel steps.
 */
export async function logHeartbeat(status: string): Promise<void> {
  const sanitizedStatus = status.replace(/[\r\n]/g, ' ').trim();
  const timestamp = new Date().toISOString();
  const logEntry = `[${timestamp}] ${sanitizedStatus}\n`;

  try {
    if (!fs.existsSync(LOG_DIR)) {
      await fs.promises.mkdir(LOG_DIR, { recursive: true });
    }

    const logFile = path.join(LOG_DIR, `heartbeat-${randomUUID()}.log`);
    await fs.promises.writeFile(logFile, logEntry);

    console.log(`💓 Heartbeat: ${sanitizedStatus}`);
  } catch (error) {
    console.error('❌ Failed to write heartbeat log:', error);
    throw error;
  }
}
