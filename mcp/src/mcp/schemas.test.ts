import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

describe("MCP tool schemas export", () => {
  it("should generate valid schema files with non-null parameters object", () => {
    const schemasDir = path.resolve(process.cwd(), ".mcp/schemas");
    expect(fs.existsSync(schemasDir)).toBe(true);

    const files = fs.readdirSync(schemasDir).filter((f) => f.endsWith(".json"));
    expect(files.length).toBeGreaterThan(0);

    for (const file of files) {
      const filePath = path.join(schemasDir, file);
      const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));

      expect(content).toHaveProperty("name");
      expect(typeof content.name).toBe("string");

      expect(content).toHaveProperty("description");
      expect(typeof content.description).toBe("string");

      expect(content).toHaveProperty("parameters");
      expect(content.parameters).not.toBeNull();
      expect(typeof content.parameters).toBe("object");
      expect(content.parameters.type).toBe("object");
      expect(content.parameters.properties).toBeDefined();
    }
  });
});
