import { chromium } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";

type AuditConfig = {
  baseUrl: string;
  outputDir: string;
  viewports: Record<string, Array<{ name: string; width: number; height: number }>>;
};

const config = JSON.parse(
  await readFile("cli/dev_tools/resources/ux-audit.config.json", "utf8"),
) as AuditConfig;
const [route = "/"] = process.argv.slice(2).filter((value) => !value.startsWith("--"));
const viewportName = process.argv.slice(2).find((value) => value.startsWith("desktop-") || value.startsWith("mobile-"));
const viewport = Object.values(config.viewports)
  .flat()
  .find((candidate) => candidate.name === viewportName) ?? config.viewports.desktop[0];
const baseUrl = (process.env.UX_BASE_URL ?? config.baseUrl).replace(/\/$/, "");
const flags = new Set(process.argv.slice(2));
const routeName = route.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "") || "root";
const resultPath = `${config.outputDir}/results/${routeName}-${viewport.name}.json`;
const screenshotPath = `${config.outputDir}/results/${routeName}-${viewport.name}.png`;

const browser = await chromium.launch({ headless: true }).catch((error) => {
  throw new Error(`Could not start browser for UX audit: ${error}`);
});
let result: Record<string, unknown> = {};
try {
  const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
  const response = await page.goto(`${baseUrl}${route}`, {
    waitUntil: "domcontentloaded",
    timeout: 20_000,
  });
  if (!response || response.status() >= 400) {
    throw new Error(`UX audit server returned ${response?.status() ?? "no response"} at ${baseUrl}${route}`);
  }
  const checks = await page.evaluate(() => {
    const overflow = document.documentElement.scrollWidth > window.innerWidth
      ? [{ scrollWidth: document.documentElement.scrollWidth, viewportWidth: window.innerWidth }]
      : [];
    const tapTargets = Array.from(document.querySelectorAll<HTMLElement>("a, button, input, select, textarea, [role='button']"))
      .filter((element) => {
        const box = element.getBoundingClientRect();
        return box.width > 0 && (box.width < 44 || box.height < 44);
      })
      .map((element) => element.outerHTML.slice(0, 200));
    const images = Array.from(document.images).map((image) => ({
      naturalWidth: image.naturalWidth,
      renderedWidth: image.getBoundingClientRect().width,
    }));
    return { overflow, tapTargets, images };
  });
  await mkdir(`${config.outputDir}/results`, { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: false });
  result = { route, viewport: viewport.name, screenshot: screenshotPath, ...checks };
  await writeFile(resultPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
} finally {
  await browser.close();
}

const failures = [
  !flags.has("--images-only") && !flags.has("--overflow-only") && !flags.has("--contrast-only") && result.tapTargets && (result.tapTargets as unknown[]).length > 0,
  flags.has("--overflow-only") && (result.overflow as unknown[]).length > 0,
  !flags.has("--images-only") && !flags.has("--overflow-only") && !flags.has("--contrast-only") && (result.overflow as unknown[]).length > 0,
].some(Boolean);
if (failures) {
  process.exitCode = 1;
}
