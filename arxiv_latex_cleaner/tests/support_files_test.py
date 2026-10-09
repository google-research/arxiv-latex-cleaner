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
"""Tests for locally referenced TeX support files in subdirectories."""

import pathlib
import tempfile
import unittest

from arxiv_latex_cleaner import arxiv_latex_cleaner


class ReferencedAuxiliaryFilesTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    temp = tempfile.TemporaryDirectory()
    self.addCleanup(temp.cleanup)
    self.root = pathlib.Path(temp.name) / 'paper'
    self.root.mkdir()
    self.output = pathlib.Path(str(self.root) + '_arXiv')

  def _create_file(self, relative_path, text='supporting content'):
    path = self.root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')

  def _run_cleaner(self, main_content, keep_bib=False):
    self._create_file('main.tex', main_content)
    arxiv_latex_cleaner.run_arxiv_cleaner(
        {
            'input_folder': str(self.root),
            'images_allowlist': {},
            'resize_images': False,
            'im_size': 500,
            'compress_pdf': False,
            'pdf_im_resolution': 500,
            'commands_to_delete': [],
            'commands_only_to_delete': [],
            'if_exceptions': [],
            'environments_to_delete': [],
            'keep_bib': keep_bib,
        }
    )

  def test_usepackage_keeps_nested_style_without_filename_extension(self):
    self._create_file('misc/emnlp2024.sty')
    self._create_file('misc/unrelated.sty')
    self._run_cleaner(r'\usepackage{misc/emnlp2024}')
    self.assertTrue((self.output / 'misc/emnlp2024.sty').is_file())
    self.assertFalse((self.output / 'misc/unrelated.sty').exists())
    self.assertIn(
        r'\usepackage{misc/emnlp2024}',
        (self.output / 'main.tex').read_text(),
    )

  def test_optional_options_and_multiple_package_names(self):
    self._create_file('misc/first.sty')
    self._create_file('misc/second.sty')
    self._create_file('misc/third.sty')
    self._run_cleaner(r'\usepackage[final]{misc/first, misc/second.sty}')
    self.assertTrue((self.output / 'misc/first.sty').is_file())
    self.assertTrue((self.output / 'misc/second.sty').is_file())
    self.assertFalse((self.output / 'misc/third.sty').exists())

  def test_bibliography_style_is_kept_without_extension(self):
    self._create_file('styles/custom_bib.bst')
    self._create_file('styles/unused.bst')
    self._run_cleaner(r'\bibliographystyle{styles/custom_bib}')
    self.assertTrue((self.output / 'styles/custom_bib.bst').is_file())
    self.assertFalse((self.output / 'styles/unused.bst').exists())

  def test_custom_documentclass_and_requirepackage_are_preserved(self):
    self._create_file('format/myclass.cls')
    self._create_file('format/localpkg.sty')
    self._run_cleaner(
        '\\documentclass[10pt]{format/myclass}\n'
        '\\RequirePackage{format/localpkg}\n'
    )
    self.assertTrue((self.output / 'format/myclass.cls').is_file())
    self.assertTrue((self.output / 'format/localpkg.sty').is_file())

  def test_bib_files_respect_keep_bib(self):
    self._create_file('refs/references.bib')
    source = r'\bibliography{refs/references}'
    self._run_cleaner(source, keep_bib=False)
    self.assertFalse((self.output / 'refs/references.bib').exists())
    self._run_cleaner(source, keep_bib=True)
    self.assertTrue((self.output / 'refs/references.bib').is_file())

  def test_addbibresource_keeps_bib_file_if_enabled(self):
    self._create_file('refs/references.bib')
    self._run_cleaner(
        r'\addbibresource[location=local]{refs/references.bib}',
        keep_bib=True,
    )
    self.assertTrue((self.output / 'refs/references.bib').is_file())

  def test_unrelated_directory_with_same_basename_is_not_copied(self):
    self._create_file('styles1/shared.sty')
    self._create_file('styles2/shared.sty')
    self._run_cleaner(r'\usepackage{styles1/shared}')
    self.assertTrue((self.output / 'styles1/shared.sty').is_file())
    self.assertFalse((self.output / 'styles2/shared.sty').exists())

  def test_references_outside_root_are_rejected(self):
    self._create_file('styles/inside.sty')
    self._run_cleaner(r'\usepackage{../styles/inside}')
    self.assertFalse((self.output / 'styles/inside.sty').exists())

  def test_parent_directory_normalization_preserves_in_root_paths(self):
    self._create_file('styles/needed.sty')
    self._run_cleaner(r'\usepackage{styles/subfolder/../needed}')
    self.assertTrue((self.output / 'styles/needed.sty').is_file())

  def test_commented_package_not_included(self):
    self._create_file('styles/ignored.sty')
    self._run_cleaner(
        '% \\usepackage{styles/ignored}\n'
        '\\begin{document}\nText\n\\end{document}\n'
    )
    self.assertFalse((self.output / 'styles/ignored.sty').exists())

  def test_direct_figure_style_path_is_still_matched_strictly(self):
    self._create_file('files/config.json')
    self._run_cleaner(r'\input{files/config.json}')
    self.assertTrue((self.output / 'files/config.json').is_file())

  def test_false_partial_path_does_not_copy_support_file(self):
    self._create_file('extra/other.sty')
    self._run_cleaner(r'\usepackage{other}')
    self.assertFalse((self.output / 'extra/other.sty').exists())


if __name__ == '__main__':
  unittest.main()
