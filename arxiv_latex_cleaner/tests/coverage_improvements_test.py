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
"""Unit and CLI tests covering edge cases in arxiv_latex_cleaner."""

import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from absl.testing import parameterized
from PIL import Image

from arxiv_latex_cleaner import arxiv_latex_cleaner as cleaner


class ConditionalEdgeCasesTest(parameterized.TestCase):

  @parameterized.named_parameters(
      {
          'testcase_name': 'unmatched_else',
          'text': 'Hello \\else world\n',
          'expected_warning': 'unmatched \\else',
      },
      {
          'testcase_name': 'duplicate_else',
          'text': '\\iffalse a \\else b \\else c \\fi\n',
          'expected_warning': 'duplicate \\else',
      },
      {
          'testcase_name': 'unmatched_fi',
          'text': 'Hello \\fi world\n',
          'expected_warning': 'unmatched \\fi',
      },
      {
          'testcase_name': 'unclosed_iffalse',
          'text': '\\iffalse never closed\n',
          'expected_warning': 'unmatched \\iffalse',
      },
      {
          'testcase_name': 'unclosed_nested_in_else',
          'text': '\\iffalse a \\else \\iftrue b \\fi\n',
          'expected_warning': 'unmatched \\iffalse',
      },
  )
  def test_malformed_conditionals_warn_and_preserve_input(
      self, text, expected_warning
  ):
    stderr_buf = io.StringIO()
    with mock.patch.object(os.sys, 'stderr', stderr_buf):
      output = cleaner._simplify_conditional_blocks(text)
    self.assertEqual(output, text)
    self.assertIn(expected_warning, stderr_buf.getvalue())

  @parameterized.named_parameters(
      {
          'testcase_name': 'nested_iftrue_inside_iffalse_else',
          'text': '\\iffalse a\\else\\iftrue b\\else c\\fi\\fi\n',
          'expected': 'b\n',
      },
      {
          'testcase_name': 'nested_iffalse_inside_unknown_else',
          'text': '\\ifcustom a\\else\\iffalse b\\fi c\\fi\n',
          'expected': '\\ifcustom a\\else c\\fi\n',
      },
      {
          'testcase_name': 'non_constant_if_macro_comparison',
          'text': '\\if\\foo\\bar keep\\else alt\\fi\n',
          'expected': '\\if\\foo\\bar keep\\else alt\\fi\n',
      },
  )
  def test_nested_and_unknown_conditionals(self, text, expected):
    self.assertEqual(cleaner._simplify_conditional_blocks(text), expected)


class CommentsAndStrippingEdgeCasesTest(unittest.TestCase):

  def test_comment_immediately_after_url_is_removed(self):
    line = r'See \url{https://example.com/a%20b}% trailing comment' + '\n'
    self.assertEqual(
        cleaner._remove_comments_inline(line),
        r'See \url{https://example.com/a%20b}' + '\n',
    )

  def test_commented_out_verbatim_on_last_line_without_newline(self):
    text = 'Hello\n% \\begin{verbatim}\n% \\end{verbatim}'
    self.assertEqual(cleaner._remove_comments(text), 'Hello\n')

  def test_strip_tex_contents_with_comment_after_end_document(self):
    lines = [
        '\\begin{document}\n',
        'Body\n',
        '\\end{document} % trailing comment\n',
        'After document\n',
    ]
    self.assertEqual(
        cleaner._strip_tex_contents(lines, '\\end{document}'),
        lines[:3],
    )


class ImageAndPdfProcessingTest(unittest.TestCase):

  def test_resize_corrupt_image_falls_back_to_copy(self):
    with tempfile.TemporaryDirectory() as tmp:
      src = Path(tmp) / 'src'
      dst = Path(tmp) / 'dst'
      src.mkdir()
      dst.mkdir()
      (src / 'corrupt.png').write_bytes(b'not a valid png image')

      stdout_buf = io.StringIO()
      with mock.patch.object(sys, 'stdout', stdout_buf):
        out = cleaner._resize_and_copy_figure(
            filename='corrupt.png',
            origin_folder=str(src),
            destination_folder=str(dst),
            resize_image=True,
            image_size=100,
            compress_pdf=False,
            pdf_resolution=150,
            convert_png_to_jpg=False,
        )
      self.assertEqual(out, 'corrupt.png')
      self.assertEqual(
          (dst / 'corrupt.png').read_bytes(), b'not a valid png image'
      )

  def test_png_to_jpg_verbose_small_and_large_threshold(self):
    with tempfile.TemporaryDirectory() as tmp:
      src = Path(tmp) / 'src'
      dst = Path(tmp) / 'dst'
      src.mkdir()
      dst.mkdir()
      img = Image.new('RGB', (64, 64), color=(10, 20, 30))
      img.save(src / 'sample.png', 'PNG')

      # Small PNG (below threshold -> quality 100)
      stdout_small = io.StringIO()
      with mock.patch.object(sys, 'stdout', stdout_small):
        out_small = cleaner._resize_and_copy_figure(
            filename='sample.png',
            origin_folder=str(src),
            destination_folder=str(dst),
            resize_image=False,
            image_size=100,
            compress_pdf=False,
            pdf_resolution=150,
            convert_png_to_jpg=True,
            png_quality=80,
            png_size_threshold=10.0,
            verbose=True,
        )
      self.assertEqual(out_small, 'sample.jpg')
      self.assertIn('Keeping original quality', stdout_small.getvalue())
      self.assertTrue((dst / 'sample.jpg').exists())

      # Large PNG (above threshold -> configured quality)
      stdout_large = io.StringIO()
      with mock.patch.object(sys, 'stdout', stdout_large):
        out_large = cleaner._resize_and_copy_figure(
            filename='sample.png',
            origin_folder=str(src),
            destination_folder=str(dst),
            resize_image=False,
            image_size=100,
            compress_pdf=False,
            pdf_resolution=150,
            convert_png_to_jpg=True,
            png_quality=75,
            png_size_threshold=0.0,
            verbose=True,
        )
      self.assertEqual(out_large, 'sample.jpg')
      self.assertIn('quality 75', stdout_large.getvalue())

  def test_update_image_references_noop_and_extensionless_and_list(self):
    # No-op when filename unchanged
    contents = {'main.tex': '\\includegraphics{fig.png}\n'}
    self.assertIsNone(
        cleaner._update_image_references(contents, 'fig.png', 'fig.png')
    )
    self.assertEqual(contents['main.tex'], '\\includegraphics{fig.png}\n')

    # Extensionless reference (Pattern 2) with list-format content + verbose
    list_contents = {
        'main.tex': ['\\begin{figure}\n', '\\includegraphics{images/fig}\n']
    }
    stdout_buf = io.StringIO()
    with mock.patch.object(sys, 'stdout', stdout_buf):
      updated = cleaner._update_image_references(
          list_contents, 'images/fig.png', 'images/fig.jpg', verbose=True
      )
    self.assertIsInstance(updated['main.tex'], list)
    self.assertIn('images/fig.jpg', '\n'.join(updated['main.tex']))
    self.assertIn('Applied pattern 2', stdout_buf.getvalue())

  def test_resize_pdf_figure_handles_timeout(self):
    fake_proc = mock.MagicMock()
    fake_proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd=['gs'], timeout=1),
        (b'partial out', b'partial err'),
    ]
    stdout_buf = io.StringIO()
    with mock.patch.object(subprocess, 'Popen', return_value=fake_proc):
      with mock.patch.object(sys, 'stdout', stdout_buf):
        cleaner._resize_pdf_figure('fig.pdf', '/src', '/dst', 150, timeout=1)
    fake_proc.kill.assert_called_once()
    self.assertEqual(fake_proc.communicate.call_count, 2)
    self.assertIn('partial out', stdout_buf.getvalue())


class FileHandlingAndMergeEdgeCasesTest(unittest.TestCase):

  def test_referenced_support_files_skips_empty_and_macro_entries(self):
    tex = r'\usepackage{local/my_pkg, , \dynamicpkg}'
    self.assertEqual(
        cleaner._referenced_latex_support_files(tex),
        {'local/my_pkg.sty'},
    )

  def test_add_root_tex_files_preserves_unreferenced_root_tex(self):
    splits = {
        'tex_in_root': ['main.tex', 'supplement.tex'],
        'tex_to_copy': ['main.tex'],
    }
    cleaner._add_root_tex_files(splits)
    self.assertEqual(splits['tex_to_copy'], ['main.tex', 'supplement.tex'])

  def test_merge_tex_files_default_merged_files_argument(self):
    tex_contents = {
        'main.tex': 'A\n\\input{sub}\nB\n',
        'sub.tex': 'SUB\n',
    }
    merged = cleaner._merge_tex_files('main.tex', tex_contents)
    self.assertEqual(merged, 'A\nSUB\n\nB\n')

  def _base_params(self, input_folder):
    return {
        'input_folder': str(input_folder),
        'images_allowlist': {},
        'resize_images': False,
        'im_size': 500,
        'compress_pdf': False,
        'pdf_im_resolution': 500,
        'commands_to_delete': [],
        'commands_only_to_delete': [],
        'environments_to_delete': [],
        'verbatim_environments': [],
        'if_exceptions': [],
        'keep_bib': False,
        'keep_agent_files': False,
        'merge_tex_files': False,
        'use_external_tikz': None,
        'svg_inkscape': None,
        'patterns_and_insertions': [],
        'paths_to_keep': [],
        'convert_png_to_jpg': False,
        'png_quality': 50,
        'png_size_threshold': 0.5,
        'verbose': False,
    }

  def test_split_all_files_with_svg_inkscape_option(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / 'main.tex').write_text('\\begin{document}\\end{document}\n')
      svg_dir = root / 'svg-inkscape'
      svg_dir.mkdir()
      (svg_dir / 'diagram_svg-tex.pdf').write_bytes(b'%PDF-1.4')

      params = self._base_params(root)
      params['to_delete'] = []
      params['figures_to_copy_if_referenced'] = [r'\.pdf$']
      params['svg_inkscape'] = 'svg-inkscape'

      splits = cleaner._split_all_files(params)
      self.assertEqual(
          splits['svg_inkscape'], ['svg-inkscape/diagram_svg-tex.pdf']
      )

  def test_end_to_end_png_to_jpg_verbose_rewrites_tex(self):
    with tempfile.TemporaryDirectory() as tmp:
      src = Path(tmp) / 'paper'
      src.mkdir()
      (src / 'main.tex').write_text(
          '\\documentclass{article}\n'
          '\\begin{document}\n'
          '\\includegraphics{pic.png}\n'
          '\\end{document}\n',
          encoding='utf-8',
      )
      Image.new('RGB', (32, 32), color=(255, 0, 0)).save(src / 'pic.png', 'PNG')

      params = self._base_params(src)
      params['convert_png_to_jpg'] = True
      params['verbose'] = True

      stdout_buf = io.StringIO()
      with mock.patch.object(sys, 'stdout', stdout_buf):
        cleaner.run_arxiv_cleaner(params)

      out_dir = Path(str(src) + '_arXiv')
      self.assertTrue((out_dir / 'pic.jpg').exists())
      self.assertIn('pic.jpg', (out_dir / 'main.tex').read_text('utf-8'))
      self.assertIn('Updated 1 image references', stdout_buf.getvalue())


class CliEndToEndTest(unittest.TestCase):

  def test_cli_help_exits_zero(self):
    result = subprocess.run(
        [sys.executable, '-m', 'arxiv_latex_cleaner', '--help'],
        capture_output=True,
        text=True,
        check=False,
    )
    self.assertEqual(result.returncode, 0)
    self.assertIn('arxiv_latex_cleaner@', result.stdout)
    self.assertIn('--merge_tex_files', result.stdout)
    self.assertIn('--keep_agent_files', result.stdout)

  def test_cli_cleans_project_directory(self):
    with tempfile.TemporaryDirectory() as tmp:
      src = Path(tmp) / 'paper'
      src.mkdir()
      (src / 'main.tex').write_text(
          '\\documentclass{article}\n'
          '% secret comment\n'
          '\\begin{document}\n'
          'Hello \\todo{remove me} world.\n'
          '\\end{document}\n',
          encoding='utf-8',
      )
      (src / 'CLAUDE.md').write_text('private agent notes\n', encoding='utf-8')

      result = subprocess.run(
          [
              sys.executable,
              '-m',
              'arxiv_latex_cleaner',
              str(src),
              '--commands_to_delete',
              'todo',
          ],
          capture_output=True,
          text=True,
          check=False,
      )
      self.assertEqual(result.returncode, 0, msg=result.stderr)

      out_dir = Path(str(src) + '_arXiv')
      cleaned = (out_dir / 'main.tex').read_text(encoding='utf-8')
      self.assertNotIn('secret comment', cleaned)
      self.assertNotIn('\\todo', cleaned)
      self.assertIn('Hello', cleaned)
      self.assertFalse((out_dir / 'CLAUDE.md').exists())


if __name__ == '__main__':
  unittest.main()
