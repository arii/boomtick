import { createAppAuth } from '@octokit/auth-app';

export async function initializeGitHubAuth(): Promise<void> {
  const appId = process.env.GITHUB_APP_ID || process.env.APP_ID;
  const privateKey = process.env.GITHUB_APP_PRIVATE_KEY || process.env.APP_PRIVATE_KEY;

  if (appId && privateKey) {
    try {
      const formattedPrivateKey = privateKey.replace(/\\n/g, '\n');
      const auth = createAppAuth({
        appId: appId,
        privateKey: formattedPrivateKey,
      });

      // We need to fetch the installation ID for the current repository
      // Since we need an installation access token, and we are likely running in a GitHub Action
      // we know the GITHUB_REPOSITORY (owner/repo).
      const repo = process.env.GITHUB_REPOSITORY;
      if (!repo) {
        console.warn('⚠️ GITHUB_REPOSITORY not set. Cannot mint installation token for repository.');
        return;
      }

      const [owner, repoName] = repo.split('/');

      // First, get the installation ID for this repo using JWT auth
      // For this we need to use a regular fetch or octokit with JWT auth
      const jwtAuth = await auth({ type: 'app' });

      const res = await fetch(`https://api.github.com/repos/${owner}/${repoName}/installation`, {
        headers: {
          'Authorization': `Bearer ${jwtAuth.token}`,
          'Accept': 'application/vnd.github.v3+json',
        }
      });

      if (!res.ok) {
        throw new Error(`Failed to get installation ID: ${res.status} ${res.statusText}`);
      }

      const installationData = await res.json();
      const installationId = installationData.id;

      const installationAuth = await auth({
        type: 'installation',
        installationId: installationId,
      });

      console.log('✅ Generated GitHub App installation token successfully.');
      process.env.GITHUB_TOKEN = installationAuth.token;
    } catch (err) {
      console.warn('⚠️ Failed to generate GitHub App token, falling back to GITHUB_TOKEN:', err instanceof Error ? err.message : err);
    }
  } else {
    if (!process.env.GITHUB_TOKEN) {
      console.warn('⚠️ Neither GitHub App credentials nor GITHUB_TOKEN were provided.');
    }
  }
}
