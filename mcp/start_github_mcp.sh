# Set the token and run the Docker container
export GITHUB_TOKEN=$(gh auth token)
docker run -i --rm \
  -e GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_TOKEN" \
  -e GITHUB_TOOLSETS="actions,code_security,dependabot,issues,pull_requests,repos,search,security_advisories" \
  ghcr.io/github/github-mcp-server:latest
