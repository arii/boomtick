from typing import Dict, Any, Optional

class CommandHandler:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    def handle(self, pr_number: int, command_text: str, comment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Parses and dispatches slash commands.
        """
        command = command_text.strip().lower()

        if command.startswith("/ai-review"):
            return self._handle_ai_review(pr_number)
        elif command.startswith("/ai-fix"):
            return self._handle_ai_fix(pr_number)

        return {"status": "ignored", "message": f"Unknown command: {command}"}

    def _handle_ai_review(self, pr_number: int) -> Dict[str, Any]:
        review_data = self.orchestrator.review_pr(pr_number)
        recommendation = review_data.get("recommendation", "COMMENT")

        # Map recommendation to GH event
        event = "COMMENT"
        if recommendation == "Approved":
            event = "APPROVE"
        elif recommendation == "Not Approved":
            event = "REQUEST_CHANGES"

        comment_body = f"## 🤖 AI Code Review\n\n{review_data.get('reviewComment', 'No comment provided.')}\n\n**Recommendation:** {recommendation}"

        self.orchestrator.github.create_review(pr_number, comment_body, [], event)

        return {"status": "success", "message": f"Submitted {event} review for PR #{pr_number}", "review": review_data}

    def _handle_ai_fix(self, pr_number: int) -> Dict[str, Any]:
        # First, ensure we have the conflict files
        conflict_files = self.orchestrator.find_conflict_files()
        if not conflict_files:
            return {"status": "error", "message": "No merge conflicts detected locally. Ensure you have merged the base branch and markers are present."}

        results = [(f, self.orchestrator.resolve_conflict(f)) for f in conflict_files]
        resolved = [f for f, success in results if success]
        failed = [f for f, success in results if not success]

        if failed:
            msg = f"Failed to resolve conflicts in: {', '.join(failed)}"
            return {"status": "partial_success" if resolved else "error", "message": msg, "resolved": resolved, "failed": failed}

        return {"status": "success", "message": f"Successfully resolved conflicts in {len(resolved)} files.", "resolved": resolved}
