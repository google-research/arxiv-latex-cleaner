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

"""Tests for YAML config and command-line argument precedence."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
import yaml
from arxiv_latex_cleaner import __main__ as cleaner_main


class ConfigPrecedenceTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    directory = tempfile.TemporaryDirectory()
    self.addCleanup(directory.cleanup)
    self.root = Path(directory.name)
    self.config = self.root / 'settings.yaml'
    self.project = self.root / 'paper'
    self.project.mkdir()
    self.output = Path(str(self.project) + '_arXiv')

  def _write_config(self, **options):
    self.config.write_text(
        yaml.safe_dump(options),
        encoding='utf-8',
    )
    return ['--config', str(self.config)]

  def _args(self, *flags):
    return cleaner_main.parse_arguments([str(self.project), *flags])

  def _create_paper(self, with_image=False):
    text = (
        '\\documentclass{article}\n'
        '\\begin{document}\n'
        'Text\n'
        + ('\\includegraphics{figure.png}\n' if with_image else '')
        + '\\end{document}\n'
    )
    (self.project / 'main.tex').write_text(text, encoding='utf-8')
    (self.project / 'refs.bib').write_text(
        '@book{test, title={Reference}}\n', encoding='utf-8'
    )
    if with_image:
      Image.new('RGB', (30, 10), (200, 120, 40)).save(
          self.project / 'figure.png'
      )

  def _run_command(self, *options):
    env = os.environ.copy()
    env['PYTHONPATH'] = os.getcwd()
    return subprocess.run(
        [
            sys.executable,
            '-m',
            'arxiv_latex_cleaner',
            str(self.project),
            '--config',
            str(self.config),
            *options,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

  def test_yaml_booleans_not_overwritten_by_false_cli_defaults(self):
    options = self._write_config(
        verbose=True,
        keep_bib=True,
        resize_images=True,
        compress_pdf=True,
        convert_png_to_jpg=True,
    )
    result = self._args(*options)
    for name in (
        'verbose',
        'keep_bib',
        'resize_images',
        'compress_pdf',
        'convert_png_to_jpg',
    ):
      self.assertTrue(result[name], name)

  def test_yaml_false_is_preserved_when_cli_defaults_are_false(self):
    options = self._write_config(
        keep_bib=False, resize_images=False, verbose=False
    )
    result = self._args(*options)
    self.assertFalse(result['keep_bib'])
    self.assertFalse(result['resize_images'])
    self.assertFalse(result['verbose'])

  def test_yaml_numeric_defaults_take_precedence(self):
    options = self._write_config(
        im_size=900,
        pdf_im_resolution=250,
        png_quality=88,
        png_size_threshold=1.25,
    )
    result = self._args(*options)
    self.assertEqual(result['im_size'], 900)
    self.assertEqual(result['pdf_im_resolution'], 250)
    self.assertEqual(result['png_quality'], 88)
    self.assertEqual(result['png_size_threshold'], 1.25)

  def test_yaml_list_defaults_take_precedence(self):
    options = self._write_config(
        commands_to_delete=['todo_cfg'],
        commands_only_to_delete=['added'],
        environments_to_delete=['obsolete'],
        if_exceptions=['iffalt'],
    )
    result = self._args(*options)
    self.assertEqual(result['commands_to_delete'], ['todo_cfg'])
    self.assertEqual(result['commands_only_to_delete'], ['added'])
    self.assertEqual(result['environments_to_delete'], ['obsolete'])
    self.assertEqual(result['if_exceptions'], ['iffalt'])

  def test_cli_boolean_true_overrides_yaml_false(self):
    options = self._write_config(keep_bib=False, verbose=False)
    result = self._args(*options, '--keep_bib', '--verbose')
    self.assertTrue(result['keep_bib'])
    self.assertTrue(result['verbose'])

  def test_cli_numeric_override_replaces_yaml_value(self):
    options = self._write_config(im_size=900)
    result = self._args(*options, '--im_size', '55')
    self.assertEqual(result['im_size'], 55)

  def test_cli_lists_prepend_to_yaml_entries(self):
    options = self._write_config(commands_to_delete=['from_yaml'])
    result = self._args(*options, '--commands_to_delete', 'from_cli')
    self.assertEqual(
        result['commands_to_delete'],
        ['from_cli', 'from_yaml'],
    )

  def test_cli_dict_merges_with_yaml_entries(self):
    options = self._write_config(images_allowlist={'y.png': 600})
    result = self._args(*options, '--images_allowlist', '{"x.png": 300}')
    self.assertEqual(
        result['images_allowlist'],
        {'y.png': 600, 'x.png': 300},
    )

  def test_no_config_uses_previous_cli_defaults(self):
    result = self._args()
    self.assertEqual(result['im_size'], 500)
    self.assertFalse(result['keep_bib'])
    self.assertFalse(result['verbose'])
    self.assertEqual(result['commands_to_delete'], [])
    self.assertNotIn('config', result)

  def test_empty_yaml_keeps_previous_defaults(self):
    self.config.write_text('', encoding='utf-8')
    result = self._args('--config', str(self.config))
    self.assertEqual(result['im_size'], 500)
    self.assertFalse(result['keep_bib'])

  def test_non_mapping_yaml_is_rejected(self):
    self.config.write_text('- not\n- mapping\n', encoding='utf-8')
    with self.assertRaises(SystemExit) as error:
      self._args('--config', str(self.config))
    self.assertEqual(error.exception.code, 2)

  def test_missing_config_is_rejected_cleanly(self):
    with self.assertRaises(SystemExit) as error:
      self._args('--config', str(self.root / 'missing.yaml'))
    self.assertEqual(error.exception.code, 2)

  def test_yaml_config_affects_real_cleaner_output_and_logging(self):
    self._create_paper(with_image=True)
    self._write_config(
        keep_bib=True,
        resize_images=True,
        im_size=9,
        verbose=True,
    )
    result = self._run_command()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertTrue((self.output / 'refs.bib').is_file())
    with Image.open(self.output / 'figure.png') as figure:
      self.assertEqual(figure.size, (9, 3))
    self.assertIn('Collecting file structure', result.stderr)

  def test_explicit_numeric_cli_override_affects_real_output(self):
    self._create_paper(with_image=True)
    self._write_config(keep_bib=True, resize_images=True, im_size=9)
    result = self._run_command('--im_size', '21')
    self.assertEqual(result.returncode, 0, result.stderr)
    with Image.open(self.output / 'figure.png') as figure:
      self.assertEqual(figure.size, (21, 7))

  def test_explicit_keep_bib_flag_affects_real_output(self):
    self._create_paper()
    self._write_config(keep_bib=False)
    result = self._run_command('--keep_bib')
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertTrue((self.output / 'refs.bib').is_file())


if __name__ == '__main__':
  unittest.main()
