# coding=utf-8
# Copyright 2018 The Google Research Authors.
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

import filecmp
from os import path
import shutil
import unittest
from absl.testing import parameterized

from arxiv_latex_cleaner import arxiv_latex_cleaner
from PIL import Image


class UnitTests(parameterized.TestCase):

  @parameterized.named_parameters(
      {
          'testcase_name': 'no_comment',
          'line_in': 'Foo\n',
          'true_output': 'Foo\n'
      }, {
          'testcase_name': 'auto_ignore',
          'line_in': '%auto-ignore\n',
          'true_output': '%auto-ignore\n'
      }, {
          'testcase_name': 'percent',
          'line_in': r'100\% accurate\n',
          'true_output': r'100\% accurate\n'
      }, {
          'testcase_name': 'comment',
          'line_in': '  % Comment\n',
          'true_output': ''
      }, {
          'testcase_name': 'comment_inline',
          'line_in': 'Foo %Comment\n',
          'true_output': 'Foo %\n'
      })
  def test_remove_comments_inline(self, line_in, true_output):
    self.assertEqual(
        arxiv_latex_cleaner._remove_comments_inline(line_in), true_output)

  @parameterized.named_parameters(
      {
          'testcase_name': 'no_command',
          'text_in': 'Foo\nFoo2\n',
          'true_output': 'Foo\nFoo2\n'
      }, {
          'testcase_name': 'command_not_removed',
          'text_in': '\\textit{Foo\nFoo2}\n',
          'true_output': '\\textit{Foo\nFoo2}\n'
      }, {
          'testcase_name': 'command_removed',
          'text_in': 'A\\todo{B\nC}\nD\n\\end{document}',
          'true_output': 'A\nD\n\\end{document}'
      })
  def test_remove_command(self, text_in, true_output):
    self.assertEqual(
        arxiv_latex_cleaner._remove_command(text_in, 'todo'), true_output)

  @parameterized.named_parameters(
      {
          'testcase_name': 'no_environment',
          'text_in': 'Foo\n',
          'true_output': 'Foo\n'
      }, {
          'testcase_name': 'environment_not_removed',
          'text_in': 'Foo\n\\begin{equation}\n3x+2\n\\end{equation}\nFoo',
          'true_output': 'Foo\n\\begin{equation}\n3x+2\n\\end{equation}\nFoo'
      }, {
          'testcase_name': 'environment_removed',
          'text_in': 'Foo\\begin{comment}\n3x+2\n\\end{comment}\nFoo',
          'true_output': 'Foo\nFoo'
      })
  def test_remove_environment(self, text_in, true_output):
    self.assertEqual(
        arxiv_latex_cleaner._remove_environment(text_in, 'comment'),
        true_output)

  @parameterized.named_parameters(
      {
          'testcase_name': 'no_iffalse',
          'text_in': 'Foo\n',
          'true_output': 'Foo\n'
      }, {
          'testcase_name': 'if_not_removed',
          'text_in': '\\ifvar\n\\ifvar\nFoo\n\\fi\n\\fi\n',
          'true_output': '\\ifvar\n\\ifvar\nFoo\n\\fi\n\\fi\n'
      }, {
          'testcase_name': 'if_removed_with_nested_ifvar',
          'text_in': '\\ifvar\n\\iffalse\n\\ifvar\nFoo\n\\fi\n\\fi\n\\fi\n',
          'true_output': '\\ifvar\n\\fi\n'
      }, {
          'testcase_name': 'if_removed_with_nested_iffalse',
          'text_in': '\\ifvar\n\\iffalse\n\\iffalse\nFoo\n\\fi\n\\fi\n\\fi\n',
          'true_output': '\\ifvar\n\\fi\n'
      }, {
          'testcase_name': 'if_removed_eof',
          'text_in': '\\iffalse\nFoo\n\\fi',
          'true_output': ''
      }, {
          'testcase_name': 'if_removed_space',
          'text_in': '\\iffalse\nFoo\n\\fi ',
          'true_output': ''
      }, {
          'testcase_name': 'if_removed_backslash',
          'text_in': '\\iffalse\nFoo\n\\fi\\end{document}',
          'true_output': '\\end{document}'
      })
  def test_remove_iffalse_block(self, text_in, true_output):
    self.assertEqual(
        arxiv_latex_cleaner._remove_iffalse_block(text_in), true_output)

  @parameterized.named_parameters(
      {
          'testcase_name': 'all_pass',
          'inputs': ['abc', 'bca'],
          'patterns': ['a'],
          'true_outputs': ['abc', 'bca'],
      }, {
          'testcase_name': 'not_all_pass',
          'inputs': ['abc', 'bca'],
          'patterns': ['a$'],
          'true_outputs': ['bca'],
      })
  def test_keep_pattern(self, inputs, patterns, true_outputs):
    self.assertEqual(
        list(arxiv_latex_cleaner._keep_pattern(inputs, patterns)), true_outputs)

  @parameterized.named_parameters(
      {
          'testcase_name': 'all_pass',
          'inputs': ['abc', 'bca'],
          'patterns': ['a'],
          'true_outputs': [],
      }, {
          'testcase_name': 'not_all_pass',
          'inputs': ['abc', 'bca'],
          'patterns': ['a$'],
          'true_outputs': ['abc'],
      })
  def test_remove_pattern(self, inputs, patterns, true_outputs):
    self.assertEqual(
        list(arxiv_latex_cleaner._remove_pattern(inputs, patterns)),
        true_outputs)

  @parameterized.named_parameters(
      {
          'testcase_name': 'no_tikz',
          'text_in': 'Foo\n',
          'figures_in': ['ext_tikz/test1.pdf', 'ext_tikz/test2.pdf'],
          'true_output': 'Foo\n'
      }, {
          'testcase_name':
              'tikz_no_match',
          'text_in':
              'Foo\\tikzsetnextfilename{test_no_match}\n\\begin{tikzpicture}\n\\node (test) at (0,0) {Test1};\n\\end{tikzpicture}\nFoo',
          'figures_in': ['ext_tikz/test1.pdf', 'ext_tikz/test2.pdf'],
          'true_output':
              'Foo\\tikzsetnextfilename{test_no_match}\n\\begin{tikzpicture}\n\\node (test) at (0,0) {Test1};\n\\end{tikzpicture}\nFoo'
      }, {
          'testcase_name':
              'tikz_match',
          'text_in':
              'Foo\\tikzsetnextfilename{test2}\n\\begin{tikzpicture}\n\\node (test) at (0,0) {Test1};\n\\end{tikzpicture}\nFoo',
          'figures_in': ['ext_tikz/test1.pdf', 'ext_tikz/test2.pdf'],
          'true_output':
              'Foo\\includegraphics{ext_tikz/test2.pdf}\nFoo'
      })
  def test_replace_tikzpictures(self, text_in, figures_in, true_output):
    self.assertEqual(
        arxiv_latex_cleaner._replace_tikzpictures(text_in, figures_in),
        true_output)


class IntegrationTests(unittest.TestCase):

  def _compare_files(self, filename, filename_true):
    if path.splitext(filename)[1].lower() in ['.jpg', '.jpeg', '.png']:
      with Image.open(filename) as im, Image.open(filename_true) as im_true:
        # We check only the sizes of the images, checking pixels would be too
        # complicated in case the resize implementations change.
        self.assertEqual(
            im.size, im_true.size,
            'Images {:s} was not resized properly.'.format(filename))
    else:
      self.assertTrue(
          filecmp.cmp(filename, filename_true),
          '{:s} and {:s} are not equal.'.format(filename, filename_true))

  def test_complete(self):
    out_path_true = 'tex_arXiv_true'
    self.out_path = 'tex_arXiv'

    # Make sure the folder does not exist, since we erase it in the test.
    if path.isdir(self.out_path):
      raise RuntimeError('The folder {:s} should not exist.'.format(
          self.out_path))

    arxiv_latex_cleaner.run_arxiv_cleaner({
        'input_folder': 'tex',
        'images_whitelist': {
            'images/im2_included.jpg': 200
        },
        'resize_images': True,
        'im_size': 100,
        'compress_pdf': False,
        'pdf_im_resolution': 500,
        'commands_to_delete': ['mytodo'],
        'use_external_tikz': 'ext_tikz'
    })

    # Checks the set of files is the same as in the true folder.
    out_files = set(arxiv_latex_cleaner._list_all_files(self.out_path))
    out_files_true = set(arxiv_latex_cleaner._list_all_files(out_path_true))
    self.assertEqual(out_files, out_files_true)

    # Compares the contents of each file against the true value.
    for f1 in out_files:
      self._compare_files(
          path.join(self.out_path, f1), path.join(out_path_true, f1))

  def tearDown(self):
    shutil.rmtree(self.out_path)
    super(IntegrationTests, self).tearDown()


if __name__ == '__main__':
  unittest.main()
