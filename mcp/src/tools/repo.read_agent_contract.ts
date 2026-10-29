import { z } from "zod";
import * as fs from "fs/promises";
import { existsSync } from "fs";
import * as path from "path";
import { ReadAgentContractInputSchema } from "./contract.js";
import { resolveTargetRepoPath } from "./repo.read_agent_context.js";

export { ReadAgentContractInputSchema };

export async function readAgentContractHandler(args: Partial<z.infer<typeof ReadAgentContractInputSchema>>) {
  const targetPath = await resolveTargetRepoPath(args);
  const contractPath = path.join(targetPath, ".agents", "AGENT_CONTRACT.md");

  if (!existsSync(contractPath)) {
    throw new Error(`Agent contract not found at ${contractPath}`);
  }

  const content = await fs.readFile(contractPath, "utf-8");
  return {
    status: "success",
    content,
    path: contractPath,
  };
}
