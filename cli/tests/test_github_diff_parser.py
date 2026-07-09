import unittest
from unittest.mock import patch, MagicMock
from dev_tools.services.github import GitHubClient

class TestGitHubDiffParser(unittest.TestCase):
    def setUp(self):
        self.client = GitHubClient(token="dummy", repo="owner/repo")

    @patch('dev_tools.services.github.GitHubClient.fetch_pr_diff')
    def test_single_hunk(self, mock_fetch_diff):
        mock_fetch_diff.return_value = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1,1 +1,2 @@
 context
+added
"""
        mapping = self.client._get_diff_mapping(1)
        self.assertEqual(mapping['a.txt'][1], 1) # context
        self.assertEqual(mapping['a.txt'][2], 2) # added

    @patch('dev_tools.services.github.GitHubClient.fetch_pr_diff')
    def test_multiple_hunks(self, mock_fetch_diff):
        mock_fetch_diff.return_value = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1,1 +1,1 @@
 context1
@@ -10,1 +10,2 @@
 context2
+added2
"""
        mapping = self.client._get_diff_mapping(1)
        # First hunk header is 0
        # Line 1 (context1) is 1
        self.assertEqual(mapping['a.txt'][1], 1)

        # Second hunk header is 2
        # Line 10 (context2) is 3
        # Line 11 (added2) is 4
        self.assertEqual(mapping['a.txt'][10], 3)
        self.assertEqual(mapping['a.txt'][11], 4)

    @patch('dev_tools.services.github.GitHubClient.fetch_pr_diff')
    def test_multiple_files(self, mock_fetch_diff):
        mock_fetch_diff.return_value = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1,1 +1,1 @@
 a
diff --git b/b.txt b/b.txt
--- a/b.txt
+++ b/b.txt
@@ -5,1 +5,1 @@
 b
"""
        mapping = self.client._get_diff_mapping(1)
        self.assertEqual(mapping['a.txt'][1], 1)
        self.assertEqual(mapping['b.txt'][5], 1)

    @patch('dev_tools.services.github.GitHubClient.fetch_pr_diff')
    def test_deletions_and_no_newline(self, mock_fetch_diff):
        mock_fetch_diff.return_value = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1,3 +1,2 @@
 context
-removed
-removed2
+added
\\ No newline at end of file
"""
        mapping = self.client._get_diff_mapping(1)
        # hunk header: 0
        # context: 1
        # -removed: 2
        # -removed2: 3
        # +added: 4
        # \ No newline: 5
        self.assertEqual(mapping['a.txt'][1], 1)
        self.assertEqual(mapping['a.txt'][2], 4)
        self.assertNotIn(3, mapping['a.txt'])

    @patch('dev_tools.services.github.GitHubClient.fetch_pr_diff')
    def test_complex_diff(self, mock_fetch_diff):
        # A more realistic diff with multiple hunks and mixed changes
        mock_fetch_diff.return_value = """diff --git a/src/app.ts b/src/app.ts
index 1234567..89abcdef 100644
--- a/src/app.ts
+++ b/src/app.ts
@@ -10,6 +10,7 @@
 import { A } from './A';
-import { B } from './B';
+import { C } from './C';
 import { D } from './D';

 export const App = () => {
@@ -25,3 +26,3 @@
-  const x = 1;
+  const x = 2;
   return x;
"""
        mapping = self.client._get_diff_mapping(1)

        # Hunk 1 (lines 10-16 in new file)
        # @@ -10,6 +10,7 @@ : pos 0
        # import { A } from './A'; : line 10, pos 1
        # -import { B } from './B'; : pos 2
        # +import { C } from './C'; : line 11, pos 3
        #  import { D } from './D'; : line 12, pos 4
        #                           : line 13, pos 5
        #  export const App = () => { : line 14, pos 6

        self.assertEqual(mapping['src/app.ts'][10], 1)
        self.assertEqual(mapping['src/app.ts'][11], 3)
        self.assertEqual(mapping['src/app.ts'][12], 4)
        self.assertEqual(mapping['src/app.ts'][14], 6)

        # Hunk 2 (lines 26-28 in new file)
        # @@ -25,3 +26,3 @@ : pos 7
        # -  const x = 1; : pos 8
        # +  const x = 2; : line 26, pos 9
        #    return x; : line 27, pos 10

        self.assertEqual(mapping['src/app.ts'][26], 9)
        self.assertEqual(mapping['src/app.ts'][27], 10)

    @patch('dev_tools.services.github.GitHubClient.fetch_pr_diff')
    def test_first_hunk_only_deletions(self, mock_fetch_diff):
        # Test case: First hunk contains only deletions.
        # Second hunk should NOT reset position to 0.
        mock_fetch_diff.return_value = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1,2 +1,0 @@
-removed1
-removed2
@@ -10,1 +8,2 @@
 context
+added
"""
        mapping = self.client._get_diff_mapping(1)
        # Hunk 1 (pos 0 to 2)
        # @@ -1,2 +1,0 @@ : pos 0
        # -removed1 : pos 1
        # -removed2 : pos 2

        # Hunk 2 (pos 3 to 5)
        # @@ -10,1 +8,2 @@ : pos 3
        # context : line 8, pos 4
        # +added : line 9, pos 5

        self.assertEqual(mapping['a.txt'][8], 4)
        self.assertEqual(mapping['a.txt'][9], 5)

if __name__ == '__main__':
    unittest.main()
