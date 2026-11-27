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
"""File discovery, copying, and LaTeX reference resolution helpers."""

import os
import pathlib
import shutil

import regex


MAX_FILENAME_LENGTH = 120

# Files and directories written by AI coding agents/assistants (Claude Code,
# OpenAI Codex, GitHub Copilot, Cursor, Gemini CLI, and others). They hold
# instructions, memory, rules, and local tool config that should never end up
# in an arXiv source bundle. Patterns are matched against POSIX-style relative
# paths, so they cover both the project root and any subdirectory. Only tool-
# specific names are included; generic names a human might legitimately use
# (e.g. CONVENTIONS.md, memory-bank/) are deliberately left out to avoid
# deleting real paper sources.
AGENT_FILES_TO_DELETE = [
    # Cross-tool standard instruction files (AGENTS.md / AGENT.md).
    r'(?:^|/)AGENTS?\.md$',
    r'(?:^|/)AGENTS\.override\.md$',
    # Anthropic Claude / Claude Code.
    r'(?:^|/)CLAUDE\.md$',
    r'(?:^|/)CLAUDE\.local\.md$',
    r'(?:^|/)\.claude/',
    r'(?:^|/)\.mcp\.json$',
    # OpenAI Codex.
    r'(?:^|/)\.codex/',
    # GitHub Copilot.
    r'(?:^|/)\.github/copilot-instructions\.md$',
    r'(?:^|/)\.github/instructions/',
    r'(?:^|/)\.github/prompts/',
    r'(?:^|/)\.github/chatmodes/',
    # Cursor.
    r'(?:^|/)\.cursorrules$',
    r'(?:^|/)\.cursor/',
    r'(?:^|/)\.cursorignore$',
    r'(?:^|/)\.cursorindexingignore$',
    # Windsurf / Codeium / Devin.
    r'(?:^|/)\.windsurfrules$',
    r'(?:^|/)\.windsurf/',
    r'(?:^|/)\.devin/',
    r'(?:^|/)\.codeiumignore$',
    # Google Gemini CLI / Code Assist.
    r'(?:^|/)GEMINI\.md$',
    r'(?:^|/)\.gemini/',
    r'(?:^|/)\.aiexclude$',
    # Continue.dev.
    r'(?:^|/)\.continue/',
    r'(?:^|/)\.continuerules$',
    # Cline.
    r'(?:^|/)\.clinerules(?:$|/)',
    r'(?:^|/)\.clineignore$',
    # Roo Code.
    r'(?:^|/)\.roo/',
    r'(?:^|/)\.roorules',
    r'(?:^|/)\.rooignore$',
    # Aider (config, history, and cache files all start with '.aider').
    r'(?:^|/)\.aider',
    # Zed.
    r'(?:^|/)\.rules$',
    # JetBrains AI Assistant / Junie.
    r'(?:^|/)\.aiassistant/',
    r'(?:^|/)\.junie/',
    r'(?:^|/)\.aiignore$',
    r'(?:^|/)\.noai$',
    # Amazon Q Developer / Kiro.
    r'(?:^|/)\.amazonq/',
    r'(?:^|/)\.kiro/',
    # Augment Code.
    r'(?:^|/)\.augment/',
    r'(?:^|/)\.augment-guidelines$',
    # OpenHands.
    r'(?:^|/)\.openhands/',
    r'(?:^|/)\.openhands_instructions$',
    # Sourcegraph Cody.
    r'(?:^|/)\.sourcegraph/',
    r'(?:^|/)\.cody/',
    # Trae, Qodo, Goose, Warp, Tabnine.
    r'(?:^|/)\.trae/',
    r'(?:^|/)\.qodo/',
    r'(?:^|/)\.goose/',
    r'(?:^|/)\.goosehints$',
    r'(?:^|/)WARP\.md$',
    r'(?:^|/)\.tabnine/',
]

# Fix for Windows: Even if '\' (os.sep) is the standard way of making paths on
# Windows, it interferes with regular expressions. We just change os.sep to '/'
# and os.path.join to a version using '/' as Windows will handle it the right
# way.
if os.name == 'nt':
  global old_os_path_join

  def new_os_join(path, *args):
    res = old_os_path_join(path, *args)
    res = res.replace('\\', '/')
    return res

  old_os_path_join = os.path.join

  os.sep = '/'
  os.path.join = new_os_join

def _create_dir_erase_if_exists(path):
  if os.path.exists(path):
    shutil.rmtree(path)
  os.makedirs(path)

def _create_dir_if_not_exists(path):
  if not os.path.exists(path):
    os.makedirs(path)

def _keep_pattern(haystack, patterns_to_keep):
  """Keeps the strings that match 'patterns_to_keep'."""
  out = []
  for item in haystack:
    if any((regex.findall(rem, item) for rem in patterns_to_keep)):
      out.append(item)
  return out

def _remove_pattern(haystack, patterns_to_remove):
  """Removes the strings that match 'patterns_to_remove'."""
  return [
      item
      for item in haystack
      if item not in _keep_pattern([item], patterns_to_remove)
  ]

def _list_all_files(in_folder, ignore_dirs=None):
  if ignore_dirs is None:
    ignore_dirs = []
  to_consider = [
      os.path.join(os.path.relpath(path, in_folder), name)
      if path != in_folder
      else name
      for path, _, files in os.walk(in_folder)
      for name in files
  ]
  return _remove_pattern(to_consider, ignore_dirs)

def _copy_file(filename, params):
  _create_dir_if_not_exists(
      os.path.join(params['output_folder'], os.path.dirname(filename))
  )
  shutil.copy(
      os.path.join(params['input_folder'], filename),
      os.path.join(params['output_folder'], filename),
  )

def _strip_tex_contents(lines, end_str):
  """Removes everything after end_str."""
  for i in range(len(lines)):
    if end_str in lines[i]:
      if '%' not in lines[i]:
        return lines[: i + 1]
      elif lines[i].index('%') > lines[i].index(end_str):
        return lines[: i + 1]
  return lines


def _read_file_content(filename):
  with open(filename, 'r', encoding='utf-8') as fp:
    lines = fp.readlines()
    lines = _strip_tex_contents(lines, '\\end{document}')
    return lines

def _read_all_tex_contents(tex_files, parameters):
  contents = {}
  for fn in tex_files:
    contents[fn] = _read_file_content(
        os.path.join(parameters['input_folder'], fn)
    )
  return contents

def _write_file_content(content, filename):
  _create_dir_if_not_exists(os.path.dirname(filename))
  with open(filename, 'w', encoding='utf-8') as fp:
    return fp.write(content)

def _referenced_latex_support_files(contents):
  r"""Find explicitly referenced local .sty, .cls, .bst and .bib resources.

  Unlike \includegraphics, \usepackage and \bibliographystyle usually omit
  their file extensions. Matching an exact project-relative path avoids
  copying unrelated files that happen to share a basename.
  """
  commands = {
      'usepackage': '.sty',
      'RequirePackage': '.sty',
      'documentclass': '.cls',
      'LoadClass': '.cls',
      'bibliographystyle': '.bst',
      'bibliography': '.bib',
      'addbibresource': '.bib',
  }
  pattern = (
      r'\\(' + '|'.join(commands) + r')'
      r'(?:\s*\[[^\]]*\])?\s*\{([^{}]+)\}'
  )
  referenced = set()
  for match in regex.finditer(pattern, contents):
    suffix = commands[match.group(1)]
    for name in match.group(2).split(','):
      name = name.strip()
      if not name or '\\' in name:
        continue
      # The TeX compilation root is the input project folder. Do not
      # resolve an absolute path or a path leading outside that folder.
      name = os.path.normpath(name).replace('\\', '/')
      if os.path.isabs(name) or name == '..' or name.startswith('../'):
        continue
      if not name.endswith(suffix):
        name += suffix
      referenced.add(name)
  return referenced

def _copy_only_referenced_non_tex_not_in_root(parameters, contents, splits):
  referenced_support_files = _referenced_latex_support_files(contents)
  for fn in splits['non_tex_not_in_root']:
    if (
        fn in referenced_support_files
        or _search_reference(fn, contents, strict=True) is not None
    ):
      _copy_file(fn, parameters)

def _search_reference(filename, contents, strict=False):
  """Returns a match object if filename is referenced in contents, and None otherwise.

  If not strict mode, path prefix and extension are optional.
  """
  if strict:
    # regex pattern for strict=True for path/to/img.ext:
    # \{[\s%]*path/to/img\.ext[\s%]*\}
    filename_regex = filename.replace('.', r'\.')
  else:
    filename_path = pathlib.Path(filename)

    # make extension optional
    root, extension = filename_path.stem, filename_path.suffix
    basename_regex = '{}({})?'.format(
        regex.escape(root), regex.escape(extension)
    )

    # iterate through parent fragments to make path prefix optional
    path_prefix_regex = ''
    for fragment in reversed(filename_path.parents):
      if fragment.name == '.':
        continue
      fragment = regex.escape(fragment.name)
      path_prefix_regex = '({}{}{})?'.format(
          path_prefix_regex, fragment, os.sep
      )

    # Regex pattern for strict=True for path/to/img.ext:
    # \{[\s%]*(<path_prefix>)?<basename>(<ext>)?[\s%]*\}
    filename_regex = path_prefix_regex + basename_regex

  # Some files 'path/to/file' are referenced in tex as './path/to/file' thus
  # adds prefix for relative paths starting with './' or '.\' to regex search.
  filename_regex = r'(.' + os.sep + r')?' + filename_regex

  # Pads with braces and optional whitespace/comment characters.
  patn = r'\{{[\s%]*{}[\s%]*\}}'.format(filename_regex)
  # Picture references in LaTeX are allowed to be in different cases.
  return regex.search(patn, contents, regex.IGNORECASE)

def _keep_only_referenced(filenames, contents, strict=False):
  """Returns the filenames referenced from contents.

  If not strict mode, path prefix and extension are optional.
  """
  return [
      fn
      for fn in filenames
      if _search_reference(fn, contents, strict) is not None
  ]

def _keep_only_referenced_tex(contents, splits):
  """Returns the filenames referenced from the tex files themselves.

  It needs various iterations in case one file is referenced from an
  unreferenced file.
  """
  old_referenced = set(splits['tex_in_root'] + splits['tex_not_in_root'])
  while True:
    referenced = set(splits['tex_in_root'])
    for fn in old_referenced:
      for fn2 in old_referenced:
        if regex.search(
            r'(' + os.path.splitext(fn)[0] + r'[.}])', '\n'.join(contents[fn2])
        ):
          referenced.add(fn)

    if referenced == old_referenced:
      splits['tex_to_copy'] = list(referenced)
      return

    old_referenced = referenced.copy()

def _add_root_tex_files(splits):
  # TODO: Check auto-ignore marker in root to detect the main file. Then check
  #  there is only one non-referenced TeX in root.

  # Forces the TeX in root to be copied, even if they are not referenced.
  for fn in splits['tex_in_root']:
    if fn not in splits['tex_to_copy']:
      splits['tex_to_copy'].append(fn)

def _split_all_files(parameters):
  """Splits the files into types or location to know what to do with them."""
  file_splits = {
      'all': _list_all_files(
          parameters['input_folder'], ignore_dirs=['.git' + os.sep]
      ),
      'in_root': [
          f
          for f in os.listdir(parameters['input_folder'])
          if os.path.isfile(os.path.join(parameters['input_folder'], f))
      ],
  }

  file_splits['not_in_root'] = [
      f for f in file_splits['all'] if f not in file_splits['in_root']
  ]
  # Preserve arXiv's anc/ ancillary files folder verbatim (excluding deleted junk).
  file_splits['anc_files'] = _remove_pattern(
      _keep_pattern(file_splits['not_in_root'], [r'^anc/']),
      parameters['to_delete'],
  )
  non_anc_not_in_root = _remove_pattern(file_splits['not_in_root'], [r'^anc/'])
  file_splits['to_copy_in_root'] = _remove_pattern(
      file_splits['in_root'],
      parameters['to_delete'] + parameters['figures_to_copy_if_referenced'],
  )
  file_splits['to_copy_not_in_root'] = _remove_pattern(
      non_anc_not_in_root,
      parameters['to_delete'] + parameters['figures_to_copy_if_referenced'],
  )
  file_splits['figures'] = _keep_pattern(
      file_splits['in_root'] + non_anc_not_in_root,
      parameters['figures_to_copy_if_referenced'],
  )

  file_splits['tex_in_root'] = _keep_pattern(
      file_splits['to_copy_in_root'], ['.tex$', '.tikz$']
  )
  file_splits['tex_not_in_root'] = _keep_pattern(
      file_splits['to_copy_not_in_root'], ['.tex$', '.tikz$']
  )

  file_splits['non_tex_in_root'] = _remove_pattern(
      file_splits['to_copy_in_root'], ['.tex$', '.tikz$']
  )
  file_splits['non_tex_not_in_root'] = _remove_pattern(
      file_splits['to_copy_not_in_root'], ['.tex$', '.tikz$']
  )

  if parameters.get('use_external_tikz', None) is not None:
    file_splits['external_tikz_figures'] = _keep_pattern(
        file_splits['all'], [parameters['use_external_tikz']]
    )
  else:
    file_splits['external_tikz_figures'] = []

  if parameters.get('svg_inkscape', None) is not None:
    file_splits['svg_inkscape'] = _keep_pattern(
        file_splits['all'], [parameters['svg_inkscape']]
    )
  else:
    file_splits['svg_inkscape'] = []

  return file_splits

def _create_out_folder(input_folder):
  """Creates the output folder, erasing it if existed."""
  out_folder = os.path.abspath(input_folder).removesuffix('.zip') + '_arXiv'
  _create_dir_erase_if_exists(out_folder)

  return out_folder
