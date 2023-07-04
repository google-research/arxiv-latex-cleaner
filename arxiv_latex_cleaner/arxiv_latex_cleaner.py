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
import collections

import copy
import os
import regex
import shutil
import subprocess
import logging

from PIL import Image

PDF_RESIZE_COMMAND = (
    'gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dNOPAUSE -dQUIET -dBATCH '
    '-dDownsampleColorImages=true -dColorImageResolution={resolution} '
    '-dColorImageDownsampleThreshold=1.0 -dAutoRotatePages=/None '
    '-sOutputFile={output} {input}')
MAX_FILENAME_LENGTH = 120

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
      item for item in haystack
      if item not in _keep_pattern([item], patterns_to_remove)
  ]


def _list_all_files(in_folder, ignore_dirs=None):
  if ignore_dirs is None:
    ignore_dirs = []
  to_consider = [
      os.path.join(os.path.relpath(path, in_folder), name)
      if path != in_folder else name
      for path, _, files in os.walk(in_folder)
      for name in files
  ]
  return _remove_pattern(to_consider, ignore_dirs)


def _copy_file(filename, params):
  _create_dir_if_not_exists(
      os.path.join(params['output_folder'], os.path.dirname(filename)))
  shutil.copy(
      os.path.join(params['input_folder'], filename),
      os.path.join(params['output_folder'], filename))


def _remove_command(text, command, keep_text=False):
  """Removes '\\command{*}' from the string 'text'.

  Regex `base_pattern` used to match balanced parentheses taken from:
  https://stackoverflow.com/questions/546433/regular-expression-to-match-balanced-parentheses/35271017#35271017
  """
  base_pattern = r'\\' + command + r'\{((?:[^{}]+|\{(?1)\})*)\}'
  # Loops in case of nested commands that need to retain text, e.g.,
  # \red{hello \red{world}}.
  while True:
    all_substitutions = []
    has_match = False
    for match in regex.finditer(base_pattern, text):
      # In case there are only spaces or nothing up to the following newline,
      # adds a percent, not to alter the newlines.
      has_match = True
      new_substring = '' if not keep_text else text[match.span()[0] +
                                                    len(command) +
                                                    2:match.span()[1] - 1]
      if match.span()[1] < len(text):
        next_newline = text[match.span()[1]:].find('\n')
        if next_newline != -1:
          text_until_newline = text[match.span()[1]:match.span()[1] +
                                    next_newline]
          if (not text_until_newline or
              text_until_newline.isspace()) and not keep_text:
            new_substring = '%'
      all_substitutions.append(
          (match.span()[0], match.span()[1], new_substring))

    for (start, end, new_substring) in reversed(all_substitutions):
      text = text[:start] + new_substring + text[end:]

    if not keep_text or not has_match:
      break

  return text


def _remove_environment(text, environment):
  """Removes '\\begin{environment}*\\end{environment}' from 'text'."""
  # Need to escape '{', to not trigger fuzzy matching if `environment` starts
  # with one of 'i', 'd', 's', or 'e'
  return regex.sub(
      r'\\begin\{' + environment + r'}[\s\S]*?\\end\{' + environment + r'}', '',
      text)


def _remove_iffalse_block(text):
  """Removes possibly nested r'\iffalse*\fi' blocks from 'text'."""
  p = regex.compile(r'\\if\s*(\w+)|\\fi(?!\w)')
  level = -1
  positions_to_delete = []
  start, end = 0, 0
  for m in p.finditer(text):
    if (m.group().replace(' ', '') == r'\iffalse' or
        m.group().replace(' ', '') == r'\if0') and level == -1:
      level += 1
      start = m.start()
    elif m.group().startswith(r'\if') and level >= 0:
      level += 1
    elif m.group() == r'\fi' and level >= 0:
      if level == 0:
        end = m.end()
        positions_to_delete.append((start, end))
      level -= 1
    else:
      pass

  for (start, end) in reversed(positions_to_delete):
    if end < len(text) and text[end].isspace():
      end_to_del = end + 1
    else:
      end_to_del = end
    text = text[:start] + text[end_to_del:]

  return text


def _remove_comments_inline(text):
  """Removes the comments from the string 'text'."""
  if 'auto-ignore' in text:
    return text
  if text.lstrip(' ').lstrip('\t').startswith('%'):
    return ''
  match = regex.search(r'(?<!\\)%', text)
  if match:
    return text[:match.end()] + '\n'
  else:
    return text


def _strip_tex_contents(lines, end_str):
  """Removes everything after end_str."""
  for i in range(len(lines)):
    if end_str in lines[i]:
      if '%' not in lines[i]:
        return lines[:i + 1]
      elif lines[i].index('%') > lines[i].index(end_str):
        return lines[:i + 1]
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
        os.path.join(parameters['input_folder'], fn))
  return contents


def _write_file_content(content, filename):
  _create_dir_if_not_exists(os.path.dirname(filename))
  with open(filename, 'w', encoding='utf-8') as fp:
    return fp.write(content)


def _remove_comments_and_commands_to_delete(content, parameters):
  """Erases all LaTeX comments in the content, and writes it."""
  content = [_remove_comments_inline(line) for line in content]
  content = _remove_environment(''.join(content), 'comment')
  content = _remove_iffalse_block(content)
  for environment in parameters.get('environments_to_delete', []):
    content = _remove_environment(content, environment)
  for command in parameters.get('commands_only_to_delete', []):
    content = _remove_command(content, command, True)
  for command in parameters['commands_to_delete']:
    content = _remove_command(content, command, False)
  return content


def _replace_tikzpictures(content, figures):
  """
    Replaces all tikzpicture environments (with includegraphic commands of
    external PDF figures) in the content, and writes it.
  """

  def get_figure(matchobj):
    found_tikz_filename = regex.search(r'\\tikzsetnextfilename{(.*?)}',
                                       matchobj.group(0)).group(1)
    # search in tex split if figure is available
    matching_tikz_filenames = _keep_pattern(
        figures, ['/' + found_tikz_filename + '.pdf'])
    if len(matching_tikz_filenames) == 1:
      return '\\includegraphics{' + matching_tikz_filenames[0] + '}'
    else:
      return matchobj.group(0)

  content = regex.sub(r'\\tikzsetnextfilename{[\s\S]*?\\end{tikzpicture}',
                      get_figure, content)

  return content


def _replace_includesvg(content, svg_inkscape_files):

  def repl_svg(matchobj):
    svg_path = matchobj.group(2)
    svg_filename = os.path.basename(svg_path)
    # search in svg_inkscape split if pdf_tex file is available
    matching_pdf_tex_files = _keep_pattern(
        svg_inkscape_files, ['/' + svg_filename + '-tex.pdf_tex'])
    if len(matching_pdf_tex_files) == 1:
      options = '' if matchobj.group(1) is None else matchobj.group(1)
      return f'\\includeinkscape{options}{{{matching_pdf_tex_files[0]}}}'
    else:
      return matchobj.group(0)

  content = regex.sub(r'\\includesvg(\[.*?\])?{(.*?)}', repl_svg, content)

  return content


def _resize_and_copy_figure(filename, origin_folder, destination_folder,
                            resize_image, image_size, compress_pdf,
                            pdf_resolution):
  """Resizes and copies the input figure (either JPG, PNG, or PDF)."""
  _create_dir_if_not_exists(
      os.path.join(destination_folder, os.path.dirname(filename)))

  if resize_image and os.path.splitext(filename)[1].lower() in [
      '.jpg', '.jpeg', '.png'
  ]:
    im = Image.open(os.path.join(origin_folder, filename))
    if max(im.size) > image_size:
      im = im.resize(
          tuple([int(x * float(image_size) / max(im.size)) for x in im.size]),
          Image.Resampling.LANCZOS)
    if os.path.splitext(filename)[1].lower() in ['.jpg', '.jpeg']:
      im.save(os.path.join(destination_folder, filename), 'JPEG', quality=90)
    elif os.path.splitext(filename)[1].lower() in ['.png']:
      im.save(os.path.join(destination_folder, filename), 'PNG')

  elif compress_pdf and os.path.splitext(filename)[1].lower() == '.pdf':
    _resize_pdf_figure(filename, origin_folder, destination_folder,
                       pdf_resolution)
  else:
    shutil.copy(
        os.path.join(origin_folder, filename),
        os.path.join(destination_folder, filename))


def _resize_pdf_figure(filename,
                       origin_folder,
                       destination_folder,
                       resolution,
                       timeout=10):
  input_file = os.path.join(origin_folder, filename)
  output_file = os.path.join(destination_folder, filename)
  bash_command = PDF_RESIZE_COMMAND.format(
      input=input_file, output=output_file, resolution=resolution)
  process = subprocess.Popen(bash_command.split(), stdout=subprocess.PIPE)

  try:
    process.communicate(timeout=timeout)
  except subprocess.TimeoutExpired:
    process.kill()
    outs, errs = process.communicate()
    print('Output: ', outs)
    print('Errors: ', errs)


def _copy_only_referenced_non_tex_not_in_root(parameters, contents, splits):
  for fn in _keep_only_referenced(
      splits['non_tex_not_in_root'], contents, strict=True):
    _copy_file(fn, parameters)


def _resize_and_copy_figures_if_referenced(parameters, contents, splits):
  image_size = collections.defaultdict(lambda: parameters['im_size'])
  image_size.update(parameters['images_allowlist'])
  pdf_resolution = collections.defaultdict(
      lambda: parameters['pdf_im_resolution'])
  pdf_resolution.update(parameters['images_allowlist'])
  for image_file in _keep_only_referenced(
      splits['figures'], contents, strict=False):
    _resize_and_copy_figure(
        filename=image_file,
        origin_folder=parameters['input_folder'],
        destination_folder=parameters['output_folder'],
        resize_image=parameters['resize_images'],
        image_size=image_size[image_file],
        compress_pdf=parameters['compress_pdf'],
        pdf_resolution=pdf_resolution[image_file])


def _search_reference(filename, contents, strict=False):
  """Returns a match object if filename is referenced in contents, and None otherwise.

  If not strict mode, path prefix and extension are optional.
  """
  if strict:
    # regex pattern for strict=True for path/to/img.ext:
    # \{[\s%]*path/to/img\.ext[\s%]*\}
    filename_regex = filename.replace('.', r'\.')
  else:
    basename = os.path.basename(filename)
    # make extension optional
    root, extension = os.path.splitext(basename)
    unescaped_basename_regex = '{}({})?'.format(root, extension)
    basename_regex = unescaped_basename_regex.replace('.', r'\.')

    # since os.path.split only splits into two parts
    # need to iterate and collect all the fragments
    fragments = []
    cur_head = os.path.dirname(filename)
    while cur_head:
      cur_head, tail = os.path.split(cur_head)
      fragments.insert(0, tail)  # insert at the beginning

    path_prefix_regex = ''
    for fragment in fragments:
      path_prefix_regex = '({}{}{})?'.format(path_prefix_regex, fragment,
                                             os.sep)

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
      fn for fn in filenames
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
        if regex.search(r'(' + os.path.splitext(fn)[0] + r'[.}])',
                        '\n'.join(contents[fn2])):
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
      'all':
          _list_all_files(
              parameters['input_folder'], ignore_dirs=['.git' + os.sep]),
      'in_root': [
          f for f in os.listdir(parameters['input_folder'])
          if os.path.isfile(os.path.join(parameters['input_folder'], f))
      ]
  }

  file_splits['not_in_root'] = [
      f for f in file_splits['all'] if f not in file_splits['in_root']
  ]
  file_splits['to_copy_in_root'] = _remove_pattern(
      file_splits['in_root'],
      parameters['to_delete'] + parameters['figures_to_copy_if_referenced'])
  file_splits['to_copy_not_in_root'] = _remove_pattern(
      file_splits['not_in_root'],
      parameters['to_delete'] + parameters['figures_to_copy_if_referenced'])
  file_splits['figures'] = _keep_pattern(
      file_splits['all'], parameters['figures_to_copy_if_referenced'])

  file_splits['tex_in_root'] = _keep_pattern(file_splits['to_copy_in_root'],
                                             ['.tex$', '.tikz$'])
  file_splits['tex_not_in_root'] = _keep_pattern(
      file_splits['to_copy_not_in_root'], ['.tex$', '.tikz$'])

  file_splits['non_tex_in_root'] = _remove_pattern(
      file_splits['to_copy_in_root'], ['.tex$', '.tikz$'])
  file_splits['non_tex_not_in_root'] = _remove_pattern(
      file_splits['to_copy_not_in_root'], ['.tex$', '.tikz$'])

  if parameters.get('use_external_tikz', None) is not None:
    file_splits['external_tikz_figures'] = _keep_pattern(
        file_splits['all'], [parameters['use_external_tikz']])
  else:
    file_splits['external_tikz_figures'] = []

  if parameters.get('svg_inkscape', None) is not None:
    file_splits['svg_inkscape'] = _keep_pattern(
        file_splits['all'], [parameters['svg_inkscape']])
  else:
    file_splits['svg_inkscape'] = []

  return file_splits


def _create_out_folder(input_folder):
  """Creates the output folder, erasing it if existed."""
  out_folder = os.path.abspath(input_folder) + '_arXiv'
  _create_dir_erase_if_exists(out_folder)

  return out_folder


def run_arxiv_cleaner(parameters):
  """Core of the code, runs the actual arXiv cleaner."""

  files_to_delete = [
      r'\.aux$', r'\.sh$', r'\.blg$', r'\.brf$', r'\.log$', r'\.out$', r'\.ps$',
      r'\.dvi$', r'\.synctex.gz$', '~$', r'\.backup$', r'\.gitignore$',
      r'\.DS_Store$', r'\.svg$', r'^\.idea', r'\.dpth$', r'\.md5$', r'\.dep$',
      r'\.auxlock$', r'\.fls$', r'\.fdb_latexmk$'
  ]

  if not parameters['keep_bib']:
    files_to_delete.append(r'\.bib$')

  parameters.update({
      'to_delete':
          files_to_delete,
      'figures_to_copy_if_referenced': [
          r'\.png$', r'\.jpg$', r'\.jpeg$', r'\.pdf$'
      ]
  })

  logging.info('Collecting file structure.')
  parameters['output_folder'] = _create_out_folder(parameters['input_folder'])

  splits = _split_all_files(parameters)

  logging.info('Reading all tex files')
  tex_contents = _read_all_tex_contents(
      splits['tex_in_root'] + splits['tex_not_in_root'], parameters)

  for tex_file in tex_contents:
    logging.info('Removing comments in file %s.', tex_file)
    tex_contents[tex_file] = _remove_comments_and_commands_to_delete(
        tex_contents[tex_file], parameters)

  for tex_file in tex_contents:
    logging.info('Replacing \\includesvg calls in file %s.', tex_file)
    tex_contents[tex_file] = _replace_includesvg(tex_contents[tex_file],
                                                 splits['svg_inkscape'])

  for tex_file in tex_contents:
    logging.info('Replacing Tikz Pictures in file %s.', tex_file)
    content = _replace_tikzpictures(tex_contents[tex_file],
                                    splits['external_tikz_figures'])
    # If file ends with '\n' already, the split in last line would add an extra
    # '\n', so we remove it.
    tex_contents[tex_file] = content.split('\n')

  _keep_only_referenced_tex(tex_contents, splits)
  _add_root_tex_files(splits)

  for tex_file in splits['tex_to_copy']:
    logging.info('Replacing patterns in file %s.', tex_file)
    content = '\n'.join(tex_contents[tex_file])
    content = _find_and_replace_patterns(
        content, parameters.get('patterns_and_insertions', list()))
    tex_contents[tex_file] = content
    new_path = os.path.join(parameters['output_folder'], tex_file)
    logging.info('Writing modified contents to %s.', new_path)
    _write_file_content(
        content,
        new_path,
    )

  full_content = '\n'.join(
      ''.join(tex_contents[fn]) for fn in splits['tex_to_copy'])
  _copy_only_referenced_non_tex_not_in_root(parameters, full_content, splits)
  for non_tex_file in splits['non_tex_in_root']:
    logging.info('Copying non-tex file %s.', non_tex_file)
    _copy_file(non_tex_file, parameters)

  _resize_and_copy_figures_if_referenced(parameters, full_content, splits)
  logging.info('Outputs written to %s', parameters['output_folder'])


def strip_whitespace(text):
  """Strips all whitespace characters.

  https://stackoverflow.com/questions/8270092/remove-all-whitespace-in-a-string
  """
  pattern = regex.compile(r'\s+')
  text = regex.sub(pattern, '', text)
  return text


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


def _find_and_replace_patterns(content, patterns_and_insertions):
  r"""

    content: str
    patterns_and_insertions: List[Dict]

    Example for patterns_and_insertions:

        [
            {
                "pattern" :
                r"(?:\\figcompfigures{\s*)(?P<first>.*?)\s*}\s*{\s*(?P<second>.*?)\s*}\s*{\s*(?P<third>.*?)\s*}",
                "insertion" :
                r"\parbox[c]{{{second}\linewidth}}{{\includegraphics[width={third}\linewidth]{{figures/{first}}}}}}",
                "description": "Replace figcompfigures"
            },
        ]
  """
  for pattern_and_insertion in patterns_and_insertions:
    pattern = pattern_and_insertion['pattern']
    insertion = pattern_and_insertion['insertion']
    description = pattern_and_insertion['description']
    logging.info('Processing pattern: %s.', description)
    p = regex.compile(pattern)
    m = p.search(content)
    while m is not None:
      local_insertion = insertion.format(**m.groupdict())
      if pattern_and_insertion.get('strip_whitespace', True):
        local_insertion = strip_whitespace(local_insertion)
      logging.info(f'Found {content[m.start():m.end()]:<70}')
      logging.info(f'Replacing with {local_insertion:<30}')
      content = content[:m.start()] + local_insertion + content[m.end():]
      m = p.search(content)
    logging.info('Finished pattern: %s.', description)
  return content
