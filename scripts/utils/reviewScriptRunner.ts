import { writeMissingApiKeyVerdict } from './verdict';

export interface ReviewScriptOptions {
  geminiClient: {
    reportFileName: string;
    reportTitle: string;
  };
  orchestrateGemini: () => Promise<void>;
  scriptName: string;
}

export async function runReviewScript(options: ReviewScriptOptions): Promise<void> {
  const provider = process.argv[2] || 'gemini';

  if (provider === 'gemini') {
    // security-safe: Environment variables are trusted in this workflow context.
    if (!process.env.GEMINI_API_KEY) {
      console.warn(`⚠️  Skipping agent ${options.scriptName} — GEMINI_API_KEY not set.`);
      try {
        await writeMissingApiKeyVerdict(
          options.geminiClient.reportFileName,
          options.geminiClient.reportTitle,
          'GEMINI_API_KEY'
        );
      } catch (err) {
        console.error('Failed to write missing API key verdict', err);
      }
      return;
    }
    await options.orchestrateGemini();
  } else {
    console.error('❌ Unknown or unsupported provider specified. Standardized directly on Gemini.');
    process.exit(1);
  }
}

export function handleScriptError(error: unknown, scriptName: string): void {
  console.error(`❌ Agent ${scriptName} failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
