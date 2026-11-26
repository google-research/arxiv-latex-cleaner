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
"""Cleans the LaTeX code of your paper to submit to arXiv."""

import contextlib
import copy
import logging
import os
import shutil
import tempfile

from .file_ops import (
    MAX_FILENAME_LENGTH,
    AGENT_FILES_TO_DELETE,
    _create_dir_erase_if_exists,
    _create_dir_if_not_exists,
    _keep_pattern,
    _remove_pattern,
    _list_all_files,
    _copy_file,
    _strip_tex_contents,
    _read_file_content,
    _read_all_tex_contents,
    _write_file_content,
    _referenced_latex_support_files,
    _copy_only_referenced_non_tex_not_in_root,
    _search_reference,
    _keep_only_referenced,
    _keep_only_referenced_tex,
    _add_root_tex_files,
    _split_all_files,
    _create_out_folder,
)
from .tex_cleaning import (
    _remove_command,
    _remove_environment,
    _simplify_conditional_blocks,
    VERBATIM_ENVIRONMENTS,
    _find_unescaped_percent,
    _remove_comments_inline,
    _remove_comments_from_lines,
    _is_commented_out,
    _find_verbatim_environments,
    _remove_comments,
    _remove_comments_and_commands_to_delete,
    _replace_tikzpictures,
    _replace_includesvg,
    _merge_tex_files,
    strip_whitespace,
    _find_and_replace_patterns,
)
from .image_processing import (
    _convert_image_to_rgb,
    _resize_and_copy_figure,
    _update_image_references,
    _resize_pdf_figure,
    _find_parent_relative_figures,
    _resize_and_copy_figures_if_referenced,
)


def run_arxiv_cleaner(parameters):
  """Core of the code, runs the actual arXiv cleaner."""

  files_to_delete = [
      r'\.aux$',
      r'\.sh$',
      r'\.blg$',
      r'\.brf$',
      r'\.log$',
      r'\.out$',
      r'\.ps$',
      r'\.dvi$',
      r'\.synctex.gz$',
      '~$',
      r'\.backup$',
      r'\.gitignore$',
      r'\.DS_Store$',
      r'\.svg$',
      r'^\.idea',
      r'\.dpth$',
      r'\.md5$',
      r'\.dep$',
      r'\.auxlock$',
      r'\.fls$',
      r'\.fdb_latexmk$',
  ]

  if not parameters['keep_bib']:
    files_to_delete.append(r'\.bib$')

  if not parameters.get('keep_agent_files', False):
    files_to_delete += AGENT_FILES_TO_DELETE

  parameters.update({
      'to_delete': files_to_delete,
      'figures_to_copy_if_referenced': [
          r'\.png$',
          r'\.jpg$',
          r'\.jpeg$',
          r'\.pdf$',
      ],
  })

  logging.info('Collecting file structure.')
  parameters['output_folder'] = _create_out_folder(parameters['input_folder'])

  from_zip = parameters['input_folder'].endswith('.zip')
  tempdir_context = (
      tempfile.TemporaryDirectory() if from_zip else contextlib.suppress()
  )

  with tempdir_context as tempdir:

    if from_zip:
      logging.info('Unzipping input folder.')
      shutil.unpack_archive(parameters['input_folder'], tempdir)
      parameters['input_folder'] = tempdir

    splits = _split_all_files(parameters)

    logging.info('Reading all tex files')
    tex_contents = _read_all_tex_contents(
        splits['tex_in_root'] + splits['tex_not_in_root'], parameters
    )

    for tex_file in tex_contents:
      logging.info('Removing comments in file %s.', tex_file)
      tex_contents[tex_file] = _remove_comments_and_commands_to_delete(
          tex_contents[tex_file], parameters
      )

    for tex_file in tex_contents:
      logging.info('Replacing \\includesvg calls in file %s.', tex_file)
      tex_contents[tex_file] = _replace_includesvg(
          tex_contents[tex_file], splits['svg_inkscape']
      )

    for tex_file in tex_contents:
      logging.info('Replacing Tikz Pictures in file %s.', tex_file)
      content = _replace_tikzpictures(
          tex_contents[tex_file], splits['external_tikz_figures']
      )
      # If file ends with '\n' already, the split in last line would add an extra
      # '\n', so we remove it.
      tex_contents[tex_file] = content.split('\n')

    _keep_only_referenced_tex(tex_contents, splits)
    _add_root_tex_files(splits)

    if parameters.get('merge_tex_files', False):
      full_contents = {fn: '\n'.join(tex_contents[fn]) for fn in tex_contents}
      merged_files = set()
      for tex_file in splits['tex_in_root']:
        logging.info('Merging referenced TeX files into file %s.', tex_file)
        tex_contents[tex_file] = _merge_tex_files(
            tex_file, full_contents, merged_files
        ).split('\n')
      splits['tex_to_copy'] = [
          fn for fn in splits['tex_to_copy'] if fn not in merged_files
      ]

    for tex_file in splits['tex_to_copy']:
      logging.info('Replacing patterns in file %s.', tex_file)
      content = '\n'.join(tex_contents[tex_file])
      content = _find_and_replace_patterns(
          content, parameters.get('patterns_and_insertions', list())
      )
      tex_contents[tex_file] = content
      new_path = os.path.join(parameters['output_folder'], tex_file)
      logging.info('Writing modified contents to %s.', new_path)
      _write_file_content(
          content,
          new_path,
      )

    full_content = '\n'.join(
        ''.join(tex_contents[fn]) for fn in splits['tex_to_copy']
    )
    _copy_only_referenced_non_tex_not_in_root(parameters, full_content, splits)
    for non_tex_file in splits['non_tex_in_root']:
      logging.info('Copying non-tex file %s.', non_tex_file)
      _copy_file(non_tex_file, parameters)

    filename_changes = _resize_and_copy_figures_if_referenced(
        parameters, full_content, splits, tex_contents=tex_contents
    )
    logging.info('Outputs written to %s', parameters['output_folder'])

    # Update LaTeX references for changed filenames if tex_contents is provided.
    if tex_contents and filename_changes:
      for old_filename, new_filename in filename_changes.items():
        tex_contents = _update_image_references(
            tex_contents,
            old_filename,
            new_filename,
            verbose=parameters.get('verbose', False),
        )

      # Re-write modified tex files with new references after converting figures.
      for tex_file in splits['tex_to_copy']:
        if tex_file in tex_contents:
          if isinstance(tex_contents[tex_file], list):
            updated_content = ''.join(tex_contents[tex_file])
          else:
            updated_content = tex_contents[tex_file]

          output_path = os.path.join(parameters['output_folder'], tex_file)
          logging.info(
              'Re-writing modified tex file with updated references: %s',
              output_path,
          )
          _write_file_content(updated_content, output_path)

      logging.info(
          'Updated %d image references and re-wrote tex files.',
          len(filename_changes),
      )

def merge_args_into_config(args, config_params):
  final_args = copy.deepcopy(config_params)
  config_keys = config_params.keys()
  for key, value in args.items():
    if key in config_keys:
      if any([isinstance(value, t) for t in [str, bool, float, int]]):
        # Overwrites config value with args value.
        final_args[key] = value
      elif isinstance(value, list):
        # Appends args values to config values.
        final_args[key] = value + config_params[key]
      elif isinstance(value, dict):
        # Updates config params with args params.
        final_args[key].update(**value)
    else:
      final_args[key] = value
  return final_args
