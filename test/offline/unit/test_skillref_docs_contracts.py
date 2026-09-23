"""Contracts for the name-matching / scoring / file-reading helpers of
``pyapi.packages._skillref_docs``.

``skillref.*`` operations rank documentation hits with these helpers: the
*mode* decides which entries match at all, and the *score* decides their order.
A wrong branch here is invisible in a green end-to-end run (the search still
returns documents - just the wrong ones), which is exactly why the branches are
pinned individually.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pyapi.packages import _skillref_docs as docs


class TestNameMatches(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(docs.name_matches("dbOpenCellView", "dbOpenCellView", "exact"))
        self.assertFalse(docs.name_matches("dbOpenCellView", "dbOpen", "exact"))

    def test_prefix(self):
        self.assertTrue(docs.name_matches("dbOpenCellView", "dbOpen", "prefix"))
        self.assertFalse(docs.name_matches("dbOpenCellView", "OpenCell", "prefix"))

    def test_suffix(self):
        self.assertTrue(docs.name_matches("dbOpenCellView", "CellView", "suffix"))
        self.assertFalse(docs.name_matches("dbOpenCellView", "dbOpen", "suffix"))

    def test_regex_is_case_insensitive(self):
        self.assertTrue(docs.name_matches("dbOpenCellView", "^DBOPEN", "regex"))
        self.assertFalse(docs.name_matches("dbOpenCellView", "^CellView", "regex"))

    def test_invalid_regex_is_false_not_an_exception(self):
        self.assertFalse(docs.name_matches("dbOpenCellView", "([unclosed", "regex"))

    def test_unknown_mode_falls_back_to_substring(self):
        self.assertTrue(docs.name_matches("dbOpenCellView", "opence", "fuzzy"))
        self.assertFalse(docs.name_matches("dbOpenCellView", "zzz", "fuzzy"))


class TestNameScore(unittest.TestCase):
    def test_exact_mode(self):
        self.assertEqual(docs.name_score("abc", "abc", "exact"), 100)
        self.assertEqual(docs.name_score("abc", "ab", "exact"), 0)

    def test_prefix_mode(self):
        self.assertEqual(docs.name_score("abcdef", "abc", "prefix"), 80)
        self.assertEqual(docs.name_score("abcdef", "def", "prefix"), 0)

    def test_suffix_mode_uses_substring_weight(self):
        self.assertEqual(docs.name_score("abcdef", "def", "suffix"), 60)
        self.assertEqual(docs.name_score("abcdef", "abc", "suffix"), 0)

    def test_regex_mode(self):
        self.assertEqual(docs.name_score("abcdef", "cde", "regex"), 60)
        self.assertEqual(docs.name_score("abcdef", "zzz", "regex"), 0)
        self.assertEqual(docs.name_score("abcdef", "([bad", "regex"), 0)

    def test_default_mode_ranks_exact_over_prefix_over_substring(self):
        self.assertEqual(docs.name_score("abc", "ABC", "fuzzy"), 100)
        self.assertEqual(docs.name_score("abcdef", "abc", "fuzzy"), 80)
        self.assertEqual(docs.name_score("xxabcxx", "abc", "fuzzy"), 60)
        self.assertEqual(docs.name_score("xxabcxx", "zzz", "fuzzy"), 0)


class TestReadText(unittest.TestCase):
    def test_reads_utf8(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "u8.txt"
            path.write_text("hallo Ä", encoding="utf-8")
            self.assertEqual(docs.read_text(path), "hallo Ä")

    def test_falls_back_to_utf16(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "u16.txt"
            path.write_bytes("hallo Ä".encode("utf-16"))
            self.assertEqual(docs.read_text(path), "hallo Ä")

    def test_falls_back_to_latin1(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "l1.txt"
            path.write_bytes("hallo Ä".encode("latin-1"))
            self.assertEqual(docs.read_text(path), "hallo Ä")

    def test_missing_file_returns_empty_string(self):
        missing = Path(tempfile.gettempdir()) / "vb-no-such-doc.txt"
        self.assertEqual(docs.read_text(missing), "")


class TestHtmlToMarkdown(unittest.TestCase):
    def test_empty_input_is_empty(self):
        self.assertEqual(docs.html_to_markdown(""), "")
        self.assertEqual(docs.html_to_markdown("   \n "), "")

    def test_script_and_style_are_dropped(self):
        html = "<style>p{color:red}</style><script>var x=1</script><p>keep</p>"
        self.assertEqual(docs.html_to_markdown(html), "keep")

    def test_self_closing_code_tag_is_removed(self):
        self.assertEqual(docs.html_to_markdown("<code/>plain"), "plain")
        self.assertEqual(docs.html_to_markdown("<code></code>plain"), "plain")

    def test_headings_bold_italic_and_inline_code(self):
        html = "<h2>Title</h2><p><strong>b</strong> <em>i</em> <code>c</code></p>"
        markdown = docs.html_to_markdown(html)
        self.assertIn("## Title", markdown)
        self.assertIn("**b**", markdown)
        self.assertIn("_i_", markdown)
        self.assertIn("`c`", markdown)

    def test_break_becomes_a_newline_after_trailing_space_cleanup(self):
        self.assertEqual(docs.html_to_markdown("<p>a<br>b</p>"), "a\nb")

    def test_unordered_and_ordered_lists(self):
        self.assertEqual(docs.html_to_markdown("<ul><li>one</li><li>two</li></ul>"),
                         "- one\n\n- two")
        self.assertEqual(docs.html_to_markdown("<ol><li>a</li><li>b</li></ol>"),
                         "1. a\n\n2. b")

    def test_link_with_href_becomes_markdown_link(self):
        self.assertEqual(docs.html_to_markdown('<a href="http://x/y">t</a>'),
                         "[t](http://x/y)")

    def test_anchor_without_href_keeps_plain_text(self):
        self.assertEqual(docs.html_to_markdown("<a>t</a>"), "t")

    def test_pre_block_is_fenced_and_keeps_whitespace(self):
        self.assertEqual(docs.html_to_markdown("<pre>a\n  b</pre>"), "```\na\n  b\n```")

    def test_nested_pre_increments_depth(self):
        self.assertEqual(docs.html_to_markdown("<pre>a<pre>b</pre>c</pre>"), "```\nabc\n```")

    def test_horizontal_rule(self):
        self.assertEqual(docs.html_to_markdown("<p>a</p><hr><p>b</p>"), "a\n\n---\n\nb")

    def test_table_with_pipe_escaping(self):
        html = ("<table><tr><th>H1</th><th>H2</th></tr>"
                "<tr><td>a|b</td><td>c</td></tr></table>")
        self.assertEqual(docs.html_to_markdown(html),
                         "| H1 | H2 |\n|---|---|\n| a\\|b | c |")

    def test_empty_table_emits_nothing(self):
        self.assertEqual(docs.html_to_markdown("<table></table>"), "")

    def test_table_with_only_empty_rows_emits_no_header(self):
        self.assertEqual(docs.html_to_markdown("<table><tr></tr></table>"), "")

    def test_blank_lines_are_collapsed(self):
        self.assertEqual(docs.html_to_markdown("<p>a</p><p></p><p></p><p>b</p>"),
                         "a\n\nb")

    def test_three_or_more_newlines_are_collapsed_to_one_blank_line(self):
        # Consecutive headings emit "\n" from the end tag plus "\n\n" from the
        # next start tag, i.e. a run of three newlines that must collapse.
        self.assertEqual(docs.html_to_markdown("<h1>a</h1><h1>b</h1>"),
                         "# a\n\n# b")

    def test_handle_data_guards(self):
        converter = docs._MarkdownConverter()
        converter.handle_data("")
        self.assertEqual(converter.parts, [])
        converter.skip_depth = 1
        converter.handle_data("ignored")
        self.assertEqual(converter.parts, [])

    def test_leading_whitespace_is_stripped_once_after_a_heading(self):
        converter = docs._MarkdownConverter()
        converter.handle_starttag("h1", [])
        converter.handle_data("   ")          # whitespace only: flag kept
        converter.handle_data("  Heading")
        self.assertEqual("".join(converter.parts).strip(), "# Heading")


class TestHtmlToText(unittest.TestCase):
    def test_empty_input_is_empty(self):
        self.assertEqual(docs.html_to_text(""), "")

    def test_tags_entities_and_whitespace(self):
        self.assertEqual(docs.html_to_text("<p>a&nbsp;b</p><p>c&amp;d</p>"), "a b c&d")

    def test_script_style_and_head_are_dropped(self):
        html = "<head><title>t</title></head><style>x</style><body>b</body>"
        self.assertEqual(docs.html_to_text(html), "b")


if __name__ == "__main__":
    unittest.main()
