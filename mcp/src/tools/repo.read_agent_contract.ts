import { z } from "zod";
import * as fs from "fs/promises";
import { existsSync, readFileSync } from "fs";
import * as path from "path";
import * as yaml from "yaml";
import { AgentContractConfigSchema, ReadAgentContractInputSchema } from "./contract.js";
import { resolveTargetRepoPath } from "./repo.read_agent_context.js";

export { ReadAgentContractInputSchema };

export function parseAgentContractContent(
  rawContent: string,
  targetPath: string
): { content: string; config: z.infer<typeof AgentContractConfigSchema> } {
  let parsedConfigRaw: Record<string, unknown> | null = null;
  let markdownBody = rawContent;

  const frontMatterMatch = rawContent.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (frontMatterMatch) {
    const yamlStr = frontMatterMatch[1];
    markdownBody = rawContent.slice(frontMatterMatch[0].length);
    try {
      const parsedYaml = yaml.parse(yamlStr);
      if (parsedYaml && typeof parsedYaml === "object") {
        parsedConfigRaw = parsedYaml as Record<string, unknown>;
      }
    } catch (e) {
      console.warn("Failed to parse YAML front-matter from AGENT_CONTRACT.md:", e);
    }
  }

  // If no front-matter was found, check for fallback .agents/agent-config.json
  if (!parsedConfigRaw) {
    const jsonConfigPath = path.join(targetPath, ".agents", "agent-config.json");
    if (existsSync(jsonConfigPath)) {
      try {
        const jsonContent = readFileSync(jsonConfigPath, "utf-8");
        const parsedJson = JSON.parse(jsonContent);
        if (parsedJson && typeof parsedJson === "object") {
          parsedConfigRaw = parsedJson as Record<string, unknown>;
        }
      } catch (e) {
        console.warn("Failed to parse .agents/agent-config.json fallback:", e);
      }
    }
  }

  // Sanitize empty strings or nulls to fall back to Zod schema defaults where appropriate
  const config = AgentContractConfigSchema.parse(parsedConfigRaw || {});

  return {
    content: markdownBody,
    config,
  };
}

export async function readAgentContractHandler(args: Partial<z.infer<typeof ReadAgentContractInputSchema>>) {
  const targetPath = await resolveTargetRepoPath(args);
  const contractPath = path.join(targetPath, ".agents", "AGENT_CONTRACT.md");

  if (!existsSync(contractPath)) {
    throw new Error(`Agent contract not found at ${contractPath}`);
  }

  const rawContent = await fs.readFile(contractPath, "utf-8");
  const { content, config } = parseAgentContractContent(rawContent, targetPath);

  return {
    status: "success",
    content,
    path: contractPath,
    config,
  };
}
