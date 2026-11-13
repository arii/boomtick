import { describe, it, expect } from "vitest";
import { installProcessGuards } from "./processGuards.js";

describe("installProcessGuards", () => {
  it("registers unhandledRejection and uncaughtException handlers", () => {
    const rejectionsBefore = process.listenerCount("unhandledRejection");
    const exceptionsBefore = process.listenerCount("uncaughtException");

    installProcessGuards();

    expect(process.listenerCount("unhandledRejection")).toBe(rejectionsBefore + 1);
    expect(process.listenerCount("uncaughtException")).toBe(exceptionsBefore + 1);
  });

  it("is idempotent — repeated calls never add duplicate listeners", () => {
    installProcessGuards(); // ensure guards are already installed
    const rejectionsBefore = process.listenerCount("unhandledRejection");
    const exceptionsBefore = process.listenerCount("uncaughtException");

    installProcessGuards();
    installProcessGuards();

    expect(process.listenerCount("unhandledRejection")).toBe(rejectionsBefore);
    expect(process.listenerCount("uncaughtException")).toBe(exceptionsBefore);
  });
});
