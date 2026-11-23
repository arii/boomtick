import { chromium } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";

type AuditConfig = { baseUrl: string; outputDir: string };

const config = JSON.parse(
  await readFile("cli/dev_tools/resources/ux-audit.config.json", "utf8"),
) as AuditConfig;
const baseUrl = (process.env.UX_BASE_URL ?? config.baseUrl).replace(/\/$/, "");
const outputDir = `${config.outputDir}/`;

const browser = await chromium.launch({ headless: true }).catch((error) => {
  throw new Error(`Could not start browser for UX route discovery: ${error}`);
});
try {
  const page = await browser.newPage();
  const response = await page.goto(baseUrl, {
    waitUntil: "domcontentloaded",
    timeout: 20_000,
  });
  if (!response || response.status() >= 400) {
    throw new Error(`UX audit server returned ${response?.status() ?? "no response"} at ${baseUrl}`);
  }
  const routes = await page.evaluate(() => {
    const origin = window.location.origin;
    const values = Array.from(document.querySelectorAll<HTMLAnchorElement>("a[href]"))
      .map((anchor) => new URL(anchor.href, origin))
      .filter((url) => url.origin === origin && !url.search && !url.hash)
      .map((url) => url.pathname);
    return [...new Set(["/", ...values])].sort();
  });
  await mkdir(outputDir, { recursive: true });
  await writeFile(
    `${outputDir}routes.json`,
    `${JSON.stringify({ routes }, null, 2)}\n`,
    "utf8",
  );
} catch (error) {
  throw new Error(`UX route discovery failed for ${baseUrl}: ${error}`);
} finally {
  await browser.close();
}
