# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Regression tests for blank lines introduced when unwrapping commands."""

from pathlib import Path
import tempfile
import unittest

from arxiv_latex_cleaner import arxiv_latex_cleaner as cleaner


class KeepTextCommandSpacingTest(unittest.TestCase):

  def test_multiline_caption_keeps_only_one_newline_at_each_boundary(self):
    source = (
        '\\begin{figure}\n'
        '  \\caption{\n'
        '    Old text\n'
        '    \\added{\n'
        '      This is something new\n'
        '    }\n'
        '    Continued old text\n'
        '  }\n'
        '\\end{figure}\n'
    )
    expected = (
        '\\begin{figure}\n'
        '  \\caption{\n'
        '    Old text\n'
        '    This is something new\n'
        '    Continued old text\n'
        '  }\n'
        '\\end{figure}\n'
    )
    self.assertEqual(cleaner._remove_command(source, 'added', True), expected)

  def test_inline_command_still_preserves_surrounding_spaces(self):
    self.assertEqual(
        cleaner._remove_command(
            r'\caption{Before \added{in the middle} after}', 'added', True
        ),
        r'\caption{Before in the middle after}',
    )

  def test_multiline_command_placed_inline_preserves_its_line_break(self):
    source = 'Before \\added{\n  middle\n} after\n'
    self.assertEqual(
        cleaner._remove_command(source, 'added', True),
        'Before \n  middle\n after\n',
    )

  def test_opening_boundary_only_avoids_extra_blank_line(self):
    source = 'Before\n  \\added{\n    inside\n  } after\n'
    self.assertEqual(
        cleaner._remove_command(source, 'added', True),
        'Before\n  inside\n   after\n',
    )

  def test_closing_boundary_only_avoids_extra_blank_line(self):
    source = 'Before \\added{inside\n  }\nAfter\n'
    self.assertEqual(
        cleaner._remove_command(source, 'added', True),
        'Before inside\nAfter\n',
    )

  def test_explicit_paragraph_break_inside_wrapped_content_is_retained(self):
    source = 'Top\n\\added{\nFirst\n\nSecond\n}\nBottom\n'
    self.assertEqual(
        cleaner._remove_command(source, 'added', True),
        'Top\nFirst\n\nSecond\nBottom\n',
    )

  def test_repeated_wrappers_do_not_accumulate_blank_caption_lines(self):
    source = (
        '\\caption{\n'
        '  A\n'
        '  \\added{\n'
        '    B\n'
        '  }\n'
        '  \\added{\n'
        '    C\n'
        '  }\n'
        '  D\n'
        '}\n'
    )
    result = cleaner._remove_command(source, 'added', True)
    self.assertEqual(result, '\\caption{\n  A\n  B\n  C\n  D\n}\n')
    self.assertNotIn('\n\n', result)

  def test_remove_entire_command_remains_unchanged(self):
    source = 'A\n\\added{\nB\n}\nC\n'
    self.assertEqual(
        cleaner._remove_command(source, 'added', False),
        'A\n%\nC\n',
    )

  def test_tab_indentation_does_not_create_caption_paragraph(self):
    source = '\\caption{\n\tOld\n\t\\added{\n\tNew\n\t}\n\tAfter\n}\n'
    result = cleaner._remove_command(source, 'added', True)
    self.assertEqual(result, '\\caption{\n\tOld\n\tNew\n\tAfter\n}\n')

  def test_end_to_end_cleaner_keeps_caption_valid(self):
    with tempfile.TemporaryDirectory() as temp:
      project = Path(temp) / 'paper'
      project.mkdir()
      (project / 'main.tex').write_text(
          '\\documentclass{article}\n'
          '\\begin{document}\n'
          '\\begin{figure}\n'
          '\\caption{\n'
          'Old text\n'
          '\\added{\n'
          'New text\n'
          '}\n'
          'Continued\n'
          '}\n'
          '\\end{figure}\n'
          '\\end{document}\n',
          encoding='utf-8',
      )
      cleaner.run_arxiv_cleaner(
          {
              'input_folder': str(project),
              'images_allowlist': {},
              'resize_images': False,
              'im_size': 500,
              'compress_pdf': False,
              'pdf_im_resolution': 500,
              'commands_to_delete': [],
              'commands_only_to_delete': ['added'],
              'if_exceptions': [],
              'environments_to_delete': [],
              'keep_bib': False,
          }
      )
      output = (Path(str(project) + '_arXiv') / 'main.tex').read_text(
          encoding='utf-8'
      )
      self.assertIn('\\caption{\nOld text\nNew text\nContinued\n}', output)
      self.assertNotIn('\\added', output)
      self.assertNotIn('\n\n', output)


if __name__ == '__main__':
  unittest.main()
