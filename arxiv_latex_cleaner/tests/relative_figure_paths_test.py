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
"""Regression tests for images referenced from a nested TeX source."""

import pathlib
import tempfile
import unittest

from PIL import Image
from arxiv_latex_cleaner import arxiv_latex_cleaner


class ParentRelativeFigureTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    workdir = tempfile.TemporaryDirectory()
    self.addCleanup(workdir.cleanup)
    self.input_dir = pathlib.Path(workdir.name) / 'paper'
    self.input_dir.mkdir()
    self.output_dir = pathlib.Path(str(self.input_dir) + '_arXiv')
    self.images = self.input_dir / 'images'
    self.images.mkdir()
    self.figures = self.input_dir / 'figures'
    self.figures.mkdir()

    for path in (
        self.images / 'image_0.png',
        self.images / 'image_1.png',
        self.figures / 'image_0.png',
    ):
      Image.new('RGB', (4, 3), (50, 100, 200)).save(path)

  def _run(self, tex_source, reference, *, convert_png_to_jpg=False):
    tex_file = self.input_dir / tex_source
    tex_file.parent.mkdir(parents=True, exist_ok=True)
    tex_file.write_text(
        '\\includegraphics{' + reference + '}\n',
        encoding='utf-8',
    )
    (self.input_dir / 'main.tex').write_text(
        '\\documentclass{article}\n'
        '\\begin{document}\n'
        + '\\input{'
        + tex_source.removesuffix('.tex')
        + '}\n'
        '\\end{document}\n',
        encoding='utf-8',
    )
    arxiv_latex_cleaner.run_arxiv_cleaner(
        {
            'input_folder': str(self.input_dir),
            'images_allowlist': {},
            'resize_images': False,
            'im_size': 500,
            'compress_pdf': False,
            'pdf_im_resolution': 500,
            'commands_to_delete': [],
            'commands_only_to_delete': [],
            'if_exceptions': [],
            'environments_to_delete': [],
            'keep_bib': False,
            'convert_png_to_jpg': convert_png_to_jpg,
        }
    )
    return self.output_dir / tex_source

  def test_parent_reference_keeps_only_correct_image(self):
    section = self._run('sections/section_0.tex', '../images/image_0.png')
    self.assertTrue((self.output_dir / 'images/image_0.png').is_file())
    self.assertFalse((self.output_dir / 'figures/image_0.png').exists())
    self.assertFalse((self.output_dir / 'images/image_1.png').exists())
    self.assertIn('../images/image_0.png', section.read_text())

  def test_nested_parent_reference_is_resolved(self):
    self._run('sections/nested/section_0.tex', '../../images/image_0.png')
    self.assertTrue((self.output_dir / 'images/image_0.png').is_file())

  def test_omitted_extension_is_supported(self):
    self._run('sections/section_0.tex', '../images/image_0')
    self.assertTrue((self.output_dir / 'images/image_0.png').is_file())

  def test_root_file_cannot_reference_outside_project(self):
    (self.input_dir / 'main.tex').write_text(
        '\\includegraphics{../images/image_0.png}\n',
        encoding='utf-8',
    )
    # No nested TeX files; the root-level ../images path is outside the tree.
    arxiv_latex_cleaner.run_arxiv_cleaner(
        {
            'input_folder': str(self.input_dir),
            'images_allowlist': {},
            'resize_images': False,
            'im_size': 500,
            'compress_pdf': False,
            'pdf_im_resolution': 500,
            'commands_to_delete': [],
            'commands_only_to_delete': [],
            'if_exceptions': [],
            'environments_to_delete': [],
            'keep_bib': False,
        }
    )
    self.assertFalse((self.output_dir / 'images/image_0.png').exists())

  def test_converting_parent_referenced_png_updates_tex(self):
    section = self._run(
        'sections/section_0.tex',
        '../images/image_0.png',
        convert_png_to_jpg=True,
    )
    self.assertTrue((self.output_dir / 'images/image_0.jpg').is_file())
    self.assertFalse((self.output_dir / 'images/image_0.png').exists())
    self.assertIn('../images/image_0.jpg', section.read_text())

  def test_unreferenced_nested_tex_does_not_pull_in_images(self):
    ignored = self.input_dir / 'sections/unused.tex'
    ignored.parent.mkdir(parents=True, exist_ok=True)
    ignored.write_text('\\includegraphics{../images/image_1.png}\n')
    self._run('sections/section_0.tex', '../images/image_0.png')
    self.assertTrue((self.output_dir / 'images/image_0.png').is_file())
    self.assertFalse((self.output_dir / 'images/image_1.png').exists())

  def test_direct_figure_resolution_rejects_path_escape(self):
    figures = ('images/image_0.png', 'figures/image_0.png')
    refs = {
        'sections/part.tex': [
            '\\includegraphics{../images/image_0.png}',
        ],
        'main.tex': '\\includegraphics{../images/image_0.png}',
    }
    self.assertEqual(
        arxiv_latex_cleaner._find_parent_relative_figures(
            figures, refs, ['sections/part.tex', 'main.tex']
        ),
        {'images/image_0.png'},
    )


if __name__ == '__main__':
  unittest.main()
