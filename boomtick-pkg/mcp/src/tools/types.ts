export type JulesStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED";

export interface JulesSession {
  id: string;
  status: JulesStatus;
  createdAt: Date;
  pullRequestUrl?: string;
}
