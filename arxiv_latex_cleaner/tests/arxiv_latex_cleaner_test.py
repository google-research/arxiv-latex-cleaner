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

from os import path
import shutil
import unittest
from absl.testing import parameterized

from arxiv_latex_cleaner import arxiv_latex_cleaner
from PIL import Image


def make_args(
    input_folder='foo/bar',
    resize_images=False,
    im_size=500,
    compress_pdf=False,
    pdf_im_resolution=500,
    images_whitelist=None,
    commands_to_delete=None,
    use_external_tikz='foo/bar/tikz',
):
  if images_whitelist is None:
    images_whitelist = {}
  if commands_to_delete is None:
    commands_to_delete = []
  args = {
      'input_folder': input_folder,
      'resize_images': resize_images,
      'im_size': im_size,
      'compress_pdf': compress_pdf,
      'pdf_im_resolution': pdf_im_resolution,
      'images_whitelist': images_whitelist,
      'commands_to_delete': commands_to_delete,
      'use_external_tikz': use_external_tikz,
  }
  return args


def make_contents():
  return (r'& \figcompfigures{'
          '\n\timage1.jpg'
          '\n}{'
          '\n\t'
          r'\ww'
          '\n}{'
          '\n\t1.0'
          '\n\t}'
          '\n& '
          r'\figcompfigures{image2.jpg}{\ww}{1.0}')


def make_patterns():
  pattern = r'(?:\\figcompfigures{\s*)(?P<first>.*?)\s*}\s*{\s*(?P<second>.*?)\s*}\s*{\s*(?P<third>.*?)\s*}'
  insertion = r"""\parbox[c]{{
            {second}\linewidth
        }}{{
            \includegraphics[
                width={third}\linewidth
            ]{{
                figures/{first}
            }}
        }} """
  description = 'Replace figcompfigures'
  output = {
      'pattern': pattern,
      'insertion': insertion,
      'description': description
  }
  return [output]


def make_search_reference_tests():
  return ({
      'testcase_name': 'prefix1',
      'filenames': ['include_image_yes.png', 'include_image.png'],
      'contents': '\\include{include_image_yes.png}',
      'strict': False,
      'true_outputs': ['include_image_yes.png']
  }, {
      'testcase_name': 'prefix2',
      'filenames': ['include_image_yes.png', 'include_image.png'],
      'contents': '\\include{include_image.png}',
      'strict': False,
      'true_outputs': ['include_image.png']
  }, {
      'testcase_name': 'nested_more_specific',
      'filenames': [
          'images/im_included.png', 'images/include/images/im_included.png'
      ],
      'contents': '\\include{images/include/images/im_included.png}',
      'strict': False,
      'true_outputs': ['images/include/images/im_included.png']
  }, {
      'testcase_name':
          'nested_less_specific',
      'filenames': [
          'images/im_included.png', 'images/include/images/im_included.png'
      ],
      'contents':
          '\\include{images/im_included.png}',
      'strict':
          False,
      'true_outputs': [
          'images/im_included.png', 'images/include/images/im_included.png'
      ]
  }, {
      'testcase_name': 'nested_substring',
      'filenames': ['images/im_included.png', 'im_included.png'],
      'contents': '\\include{images/im_included.png}',
      'strict': False,
      'true_outputs': ['images/im_included.png']
  }, {
      'testcase_name': 'nested_diffpath',
      'filenames': ['images/im_included.png', 'figures/im_included.png'],
      'contents': '\\include{images/im_included.png}',
      'strict': False,
      'true_outputs': ['images/im_included.png']
  }, {
      'testcase_name': 'diffext',
      'filenames': ['tables/demo.tex', 'tables/demo.tikz', 'demo.tex'],
      'contents': '\\include{tables/demo.tex}',
      'strict': False,
      'true_outputs': ['tables/demo.tex']
  }, {
      'testcase_name': 'diffext2',
      'filenames': ['tables/demo.tex', 'tables/demo.tikz', 'demo.tex'],
      'contents': '\\include{tables/demo}',
      'strict': False,
      'true_outputs': ['tables/demo.tex', 'tables/demo.tikz']
  }, {
      'testcase_name': 'strict_prefix1',
      'filenames': ['demo_yes.tex', 'demo.tex'],
      'contents': '\\include{demo_yes.tex}',
      'strict': True,
      'true_outputs': ['demo_yes.tex']
  }, {
      'testcase_name': 'strict_prefix2',
      'filenames': ['demo_yes.tex', 'demo.tex'],
      'contents': '\\include{demo.tex}',
      'strict': True,
      'true_outputs': ['demo.tex']
  }, {
      'testcase_name': 'strict_nested_more_specific',
      'filenames': [
          'tables/table_included.csv',
          'tables/include/tables/table_included.csv'
      ],
      'contents': '\\include{tables/include/tables/table_included.csv}',
      'strict': True,
      'true_outputs': ['tables/include/tables/table_included.csv']
  }, {
      'testcase_name': 'strict_nested_less_specific',
      'filenames': [
          'tables/table_included.csv',
          'tables/include/tables/table_included.csv'
      ],
      'contents': '\\include{tables/table_included.csv}',
      'strict': True,
      'true_outputs': ['tables/table_included.csv']
  }, {
      'testcase_name': 'strict_nested_substring1',
      'filenames': ['tables/table_included.csv', 'table_included.csv'],
      'contents': '\\include{tables/table_included.csv}',
      'strict': True,
      'true_outputs': ['tables/table_included.csv']
  }, {
      'testcase_name': 'strict_nested_substring2',
      'filenames': ['tables/table_included.csv', 'table_included.csv'],
      'contents': '\\include{table_included.csv}',
      'strict': True,
      'true_outputs': ['table_included.csv']
  }, {
      'testcase_name': 'strict_nested_diffpath',
      'filenames': ['tables/table_included.csv', 'data/table_included.csv'],
      'contents': '\\include{tables/table_included.csv}',
      'strict': True,
      'true_outputs': ['tables/table_included.csv']
  }, {
      'testcase_name': 'strict_diffext',
      'filenames': ['tables/demo.csv', 'tables/demo.txt', 'demo.csv'],
      'contents': '\\include{tables/demo.csv}',
      'strict': True,
      'true_outputs': ['tables/demo.csv']
  }, {
      'testcase_name': 'path_starting_with_dot',
      'filenames': ['./images/im_included.png', './figures/im_included.png'],
      'contents': '\\include{./images/im_included.png}',
      'strict': False,
      'true_outputs': ['./images/im_included.png']
  })


class UnitTests(parameterized.TestCase):

  @parameterized.named_parameters(
      {
          'testcase_name': 'empty config',
          'args': make_args(),
          'config_params': {},
          'final_args': make_args(),
      },
      {
          'testcase_name': 'empty args',
          'args': {},
          'config_params': make_args(),
          'final_args': make_args(),
      },
      {
          'testcase_name':
              'args and config provided',
          'args':
              make_args(
                  images_whitelist={'path1/': 1000},
                  commands_to_delete=[r'\todo1']),
          'config_params':
              make_args(
                  'foo_/bar_',
                  True,
                  1000,
                  True,
                  1000,
                  images_whitelist={'path2/': 1000},
                  commands_to_delete=[r'\todo2'],
                  use_external_tikz='foo_/bar_/tikz_',
              ),
          'final_args':
              make_args(
                  images_whitelist={
                      'path1/': 1000,
                      'path2/': 1000
                  },
                  commands_to_delete=[r'\todo1', r'\todo2'],
              ),
      },
  )
  def test_merge_args_into_config(self, args, config_params, final_args):
    self.assertEqual(
        arxiv_latex_cleaner.merge_args_into_config(args, config_params),
        final_args)

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
          'keep_text': False,
          'true_output': 'Foo\nFoo2\n'
      }, {
          'testcase_name': 'command_not_removed',
          'text_in': '\\textit{Foo\nFoo2}\n',
          'keep_text': False,
          'true_output': '\\textit{Foo\nFoo2}\n'
      }, {
          'testcase_name': 'command_no_end_line_removed',
          'text_in': 'A\\todo{B\nC}D\nE\n\\end{document}',
          'keep_text': False,
          'true_output': 'AD\nE\n\\end{document}'
      }, {
          'testcase_name': 'command_with_end_line_removed',
          'text_in': 'A\n\\todo{B\nC}\nD\n\\end{document}',
          'keep_text': False,
          'true_output': 'A\n%\nD\n\\end{document}'
      }, {
          'testcase_name': 'no_command_keep_text',
          'text_in': 'Foo\nFoo2\n',
          'keep_text': True,
          'true_output': 'Foo\nFoo2\n'
      }, {
          'testcase_name': 'command_not_removed_keep_text',
          'text_in': '\\textit{Foo\nFoo2}\n',
          'keep_text': True,
          'true_output': '\\textit{Foo\nFoo2}\n'
      }, {
          'testcase_name': 'command_no_end_line_removed_keep_text',
          'text_in': 'A\\todo{B\nC}D\nE\n\\end{document}',
          'keep_text': True,
          'true_output': 'AB\nCD\nE\n\\end{document}'
      }, {
          'testcase_name': 'command_with_end_line_removed_keep_text',
          'text_in': 'A\n\\todo{B\nC}\nD\n\\end{document}',
          'keep_text': True,
          'true_output': 'A\nB\nC\nD\n\\end{document}'
      }, {
          'testcase_name': 'nested_command_keep_text',
          'text_in': 'A\n\\todo{B\n\\todo{C}}\nD\n\\end{document}',
          'keep_text': True,
          'true_output': 'A\nB\nC\nD\n\\end{document}'
      }, {
          'testcase_name':
              'deeply_nested_command_keep_text',
          'text_in':
              'A\n\\todo{B\n\\emph{C\\footnote{\\textbf{D}}}}\nE\n\\end{document}',
          'keep_text':
              True,
          'true_output':
              'A\nB\n\\emph{C\\footnote{\\textbf{D}}}\nE\n\\end{document}'
      })
  def test_remove_command(self, text_in, keep_text, true_output):
    self.assertEqual(
        arxiv_latex_cleaner._remove_command(text_in, 'todo', keep_text),
        true_output)

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
      }, {
          'testcase_name': 'commands_not_removed',
          'text_in': '\\newcommand\\figref[1]{Figure~\\ref{fig:\#1}}',
          'true_output': '\\newcommand\\figref[1]{Figure~\\ref{fig:\#1}}'
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
          'testcase_name':
              'replace_contents',
          'content':
              make_contents(),
          'patterns_and_insertions':
              make_patterns(),
          'true_outputs': (
              r'& \parbox[c]{\ww\linewidth}{\includegraphics[width=1.0\linewidth]{figures/image1.jpg}}'
              '\n'
              r'& \parbox[c]{\ww\linewidth}{\includegraphics[width=1.0\linewidth]{figures/image2.jpg}}'
          ),
      },)
  def test_find_and_replace_patterns(self, content, patterns_and_insertions,
                                     true_outputs):
    output = arxiv_latex_cleaner._find_and_replace_patterns(
        content, patterns_and_insertions)
    output = arxiv_latex_cleaner.strip_whitespace(output)
    true_outputs = arxiv_latex_cleaner.strip_whitespace(true_outputs)
    self.assertEqual(output, true_outputs)

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

  @parameterized.named_parameters(*make_search_reference_tests())
  def test_search_reference_weak(self, filenames, contents, strict,
                                 true_outputs):
    cleaner_outputs = []
    for filename in filenames:
      reference = arxiv_latex_cleaner._search_reference(filename, contents,
                                                        strict)
      if reference is not None:
        cleaner_outputs.append(filename)

    # weak check (passes as long as cleaner includes a superset of the true_output)
    for true_output in true_outputs:
      self.assertIn(true_output, cleaner_outputs)

  @parameterized.named_parameters(*make_search_reference_tests())
  def test_search_reference_strong(self, filenames, contents, strict,
                                   true_outputs):
    cleaner_outputs = []
    for filename in filenames:
      reference = arxiv_latex_cleaner._search_reference(filename, contents,
                                                        strict)
      if reference is not None:
        cleaner_outputs.append(filename)

    # strong check (set of files must match exactly)
    weak_check_result = set(true_outputs).issubset(cleaner_outputs)
    if weak_check_result:
      msg = 'not fatal, cleaner included more files than necessary'
    else:
      msg = 'fatal, see test_search_reference_weak'
    self.assertEqual(cleaner_outputs, true_outputs, msg)

  @parameterized.named_parameters(
      {
          'testcase_name': 'three_parent',
          'filename': 'long/path/to/img.ext',
          'content_strs': [
              # match
              '{img.ext}',
              '{to/img.ext}',
              '{path/to/img.ext}',
              '{long/path/to/img.ext}',
              '{%\nimg.ext  }',
              '{to/img.ext % \n}',
              '{  \npath/to/img.ext\n}',
              '{ \n \nlong/path/to/img.ext\n}',
              '{img}',
              '{to/img}',
              '{path/to/img}',
              '{long/path/to/img}',
              # dont match
              '{from/img.ext}',
              '{from/img}',
              '{imgoext}',
              '{from/imgo}',
              '{ \n long/\npath/to/img.ext\n}',
              '{path/img.ext}',
              '{long/img.ext}',
              '{long/path/img.ext}',
              '{long/to/img.ext}',
              '{path/img}',
              '{long/img}',
              '{long/path/img}',
              '{long/to/img}'
          ],
          'strict': False,
          'true_outputs': [True] * 12 + [False] * 13
      },
      {
          'testcase_name': 'two_parent',
          'filename': 'path/to/img.ext',
          'content_strs': [
              # match
              '{img.ext}',
              '{to/img.ext}',
              '{path/to/img.ext}',
              '{%\nimg.ext  }',
              '{to/img.ext % \n}',
              '{  \npath/to/img.ext\n}',
              '{img}',
              '{to/img}',
              '{path/to/img}',
              # dont match
              '{long/path/to/img.ext}',
              '{ \n \nlong/path/to/img.ext\n}',
              '{long/path/to/img}',
              '{from/img.ext}',
              '{from/img}',
              '{imgoext}',
              '{from/imgo}',
              '{ \n long/\npath/to/img.ext\n}',
              '{path/img.ext}',
              '{long/img.ext}',
              '{long/path/img.ext}',
              '{long/to/img.ext}',
              '{path/img}',
              '{long/img}',
              '{long/path/img}',
              '{long/to/img}'
          ],
          'strict': False,
          'true_outputs': [True] * 9 + [False] * 16
      },
      {
          'testcase_name': 'one_parent',
          'filename': 'to/img.ext',
          'content_strs': [
              # match
              '{img.ext}',
              '{to/img.ext}',
              '{%\nimg.ext  }',
              '{to/img.ext % \n}',
              '{img}',
              '{to/img}',
              # dont match
              '{long/path/to/img}',
              '{path/to/img}',
              '{ \n \nlong/path/to/img.ext\n}',
              '{  \npath/to/img.ext\n}',
              '{long/path/to/img.ext}',
              '{path/to/img.ext}',
              '{from/img.ext}',
              '{from/img}',
              '{imgoext}',
              '{from/imgo}',
              '{ \n long/\npath/to/img.ext\n}',
              '{path/img.ext}',
              '{long/img.ext}',
              '{long/path/img.ext}',
              '{long/to/img.ext}',
              '{path/img}',
              '{long/img}',
              '{long/path/img}',
              '{long/to/img}'
          ],
          'strict': False,
          'true_outputs': [True] * 6 + [False] * 19
      },
      {
          'testcase_name': 'two_parent_strict',
          'filename': 'path/to/img.ext',
          'content_strs': [
              # match
              '{path/to/img.ext}',
              '{  \npath/to/img.ext\n}',
              # dont match
              '{img.ext}',
              '{to/img.ext}',
              '{%\nimg.ext  }',
              '{to/img.ext % \n}',
              '{img}',
              '{to/img}',
              '{path/to/img}',
              '{long/path/to/img.ext}',
              '{ \n \nlong/path/to/img.ext\n}',
              '{long/path/to/img}',
              '{from/img.ext}',
              '{from/img}',
              '{imgoext}',
              '{from/imgo}',
              '{ \n long/\npath/to/img.ext\n}',
              '{path/img.ext}',
              '{long/img.ext}',
              '{long/path/img.ext}',
              '{long/to/img.ext}',
              '{path/img}',
              '{long/img}',
              '{long/path/img}',
              '{long/to/img}'
          ],
          'strict': True,
          'true_outputs': [True] * 2 + [False] * 23
      },
  )
  def test_search_reference_filewise(self, filename, content_strs, strict,
                                     true_outputs):
    if len(content_strs) != len(true_outputs):
      raise ValueError(
          "number of true_outputs doesn't match number of content strs")
    for content, true_output in zip(content_strs, true_outputs):
      reference = arxiv_latex_cleaner._search_reference(filename, content,
                                                        strict)
      matched = reference is not None
      msg_not = ' ' if true_output else ' not '
      msg_fmt = 'file {} should' + msg_not + 'have matched latex reference {}'
      msg = msg_fmt.format(filename, content)
      self.assertEqual(matched, true_output, msg)


class IntegrationTests(unittest.TestCase):

  def setUp(self):
    super(IntegrationTests, self).setUp()
    self.out_path = 'tex_arXiv'

  def _compare_files(self, filename, filename_true):
    if path.splitext(filename)[1].lower() in ['.jpg', '.jpeg', '.png']:
      with Image.open(filename) as im, Image.open(filename_true) as im_true:
        # We check only the sizes of the images, checking pixels would be too
        # complicated in case the resize implementations change.
        self.assertEqual(
            im.size, im_true.size,
            'Images {:s} was not resized properly.'.format(filename))
    else:
      # Checks if text files are equal without taking in account end of line
      # characters.
      with open(filename, 'rb') as f:
        processed_content = f.read().splitlines()
      with open(filename_true, 'rb') as f:
        groundtruth_content = f.read().splitlines()

      self.assertEqual(
          processed_content, groundtruth_content,
          '{:s} and {:s} are not equal.'.format(filename, filename_true))

  def test_complete(self):
    out_path_true = 'tex_arXiv_true'

    # Make sure the folder does not exist, since we erase it in the test.
    if path.isdir(self.out_path):
      raise RuntimeError('The folder {:s} should not exist.'.format(
          self.out_path))

    arxiv_latex_cleaner.run_arxiv_cleaner({
        'input_folder': 'tex',
        'images_whitelist': {
            'images/im2_included.jpg': 200,
            'images/im3_included.png': 400,
        },
        'resize_images': True,
        'im_size': 100,
        'compress_pdf': False,
        'pdf_im_resolution': 500,
        'commands_to_delete': ['mytodo'],
        'commands_only_to_delete': ['red'],
        'use_external_tikz': 'ext_tikz',
        'keep_bib': False
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
