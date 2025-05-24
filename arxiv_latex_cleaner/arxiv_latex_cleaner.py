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
import contextlib
import copy
import logging
import os
import pathlib
import shutil
import subprocess
import tempfile

from PIL import Image
import regex

PDF_RESIZE_COMMAND = (
    'gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dNOPAUSE -dQUIET -dBATCH '
    '-dDownsampleColorImages=true -dColorImageResolution={resolution} '
    '-dColorImageDownsampleThreshold=1.0 -dAutoRotatePages=/None '
    '-sOutputFile={output} {input}'
)
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


def _remove_command(text, command, keep_text=False):
  """Removes '\\command{*}' from the string 'text'.

  Regex `base_pattern` used to match balanced parentheses taken from:
  https://stackoverflow.com/questions/546433/regular-expression-to-match-balanced-parentheses/35271017#35271017
  """
  base_pattern = (
      r'\\'
      + command
      + r'(?:\[(?:.*?)\])*\{((?:[^{}]+|\{(?1)\})*)\}(?:\[(?:.*?)\])*'
  )

  def extract_text_inside_curly_braces(text):
    """Extract text inside of {} from command string"""
    pattern = r'\{((?:[^{}]|(?R))*)\}'

    match = regex.search(pattern, text)

    if match:
      return match.group(1)
    else:
      return ''

  # Loops in case of nested commands that need to retain text, e.g.,
  # \red{hello \red{world}}.
  while True:
    all_substitutions = []
    has_match = False
    for match in regex.finditer(base_pattern, text):
      # In case there are only spaces or nothing up to the following newline,
      # adds a percent, not to alter the newlines.
      has_match = True

      if not keep_text:
        new_substring = ''
      else:
        temp_substring = text[match.span()[0] : match.span()[1]]
        new_substring = extract_text_inside_curly_braces(temp_substring)

      if match.span()[1] < len(text):
        next_newline = text[match.span()[1] :].find('\n')
        if next_newline != -1:
          text_until_newline = text[
              match.span()[1] : match.span()[1] + next_newline
          ]
          if (
              not text_until_newline or text_until_newline.isspace()
          ) and not keep_text:
            new_substring = '%'
      all_substitutions.append(
          (match.span()[0], match.span()[1], new_substring)
      )

    for start, end, new_substring in reversed(all_substitutions):
      text = text[:start] + new_substring + text[end:]

    if not keep_text or not has_match:
      break

  return text


def _remove_environment(text, environment):
  """Removes '\\begin{environment}*\\end{environment}' from 'text'."""
  # Need to escape '{', to not trigger fuzzy matching if `environment` starts
  # with one of 'i', 'd', 's', or 'e'
  return regex.sub(
      r'\\begin\{' + environment + r'}[\s\S]*?\\end\{' + environment + r'}',
      '',
      text,
  )


def _simplify_conditional_blocks(text, if_exceptions=[]):
  r"""Simplify possibly nested conditional blocks from 'text'.

  For example, `\iffalse TEST1\else TEST2\fi` is simplified to `TEST2`,
  and `\iftrue TEST1\else TEST2\fi` is simplified to `TEST1`.
  Unknown conditionals are left untouched.

  If the conditional tree is malformed, the function will print a warning
  to stderr and return the original text.
  """
  p = regex.compile(r'(?!(?<=\\newif\s*))\\if\s*(\w+)|\\else(?!\w)|\\fi(?!\w)')
  toplevel_tree = {'left': [], 'right': [], 'kind': 'toplevel', 'parent': None}

  tree = toplevel_tree

  exceptions = [
      # TeX primitives
      'iff',
      # package etoolbox
      'ifpatchable',
      'ifpatchable*',
      'ifbool',
      'iftoggle',
      'ifdef',
      'ifcsdef',
      'ifundef',
      'ifcsundef',
      'ifdefmacro',
      'ifcsmacro',
      'ifdefparam',
      'ifcsparam',
      'ifcsprefix',
      'ifdefprotected',
      'ifcsprotected',
      'ifdefltxprotect',
      'ifcsltxprotect',
      'ifdefempty',
      'ifcsempty',
      'ifdefvoid',
      'ifcsvoid',
      'ifdefequal',
      'ifcsequal',
      'ifdefstring',
      'ifcsstring',
      'ifdefstrequal',
      'ifcsstrequal',
      'ifdefcounter',
      'ifcscounter',
      'ifltxcounter',
      'ifdeflength',
      'ifcslength',
      'ifdefdimen',
      'ifcsdimen',
      'ifstrequal',
      'ifstrempty',
      'ifblank',
      'ifnumcomp',
      'ifnumequal',
      'ifnumodd',
      'ifdimcomp',
      'ifdimequal',
      'ifdimgreater',
      'ifdimless',
      'ifboolexpr',
      'ifboolexpe',
      'ifinlist',
      'ifinlistcs',
      'ifrmnum',
      # package hyperref
      'ifpdfstringunicode',
      # package ifthen
      'ifthenelse',
  ] + if_exceptions

  def new_subtree(kind):
    return {'kind': kind, 'left': [], 'right': []}

  def add_subtree(tree, subtree):
    if 'else' not in tree:
      tree['left'].append(subtree)
    else:
      tree['right'].append(subtree)
    subtree['parent'] = tree

  def print_tree(tree, indent, write):
    if 'start' in tree:
      write(' ' * indent + tree['start'].group() + '\n')
    for subtree in tree['left']:
      print_tree(subtree, indent + 2, write)
    if 'else' in tree:
      write(' ' * indent + tree['else'].group() + '\n')
    for subtree in tree['right']:
      print_tree(subtree, indent + 2)
    if 'end' in tree:
      write(' ' * indent + tree['end'].group() + '\n')

  def print_abort(error_finding):
    os.sys.stderr.write(
        f'Warning: Found {error_finding}! Not removing any conditional'
        ' blocks...\n'
    )
    os.sys.stderr.write(
        f'         This is the matched tree (as built up to the error):\n'
    )
    print_tree(toplevel_tree, indent=9, write=os.sys.stderr.write)
    os.sys.stderr.write(
        f'         Potentially, you need to supply an exception using'
        f" --if_exceptions'.\n"
    )

  for m in p.finditer(text):
    m_no_space = m.group().replace(' ', '')
    if m_no_space == r'\iffalse' or m_no_space == r'\if0':
      subtree = new_subtree('iffalse')
      subtree['start'] = m
      add_subtree(tree, subtree)
      tree = subtree
    elif m_no_space == r'\iftrue' or m_no_space == r'\if1':
      subtree = new_subtree('iftrue')
      subtree['start'] = m
      add_subtree(tree, subtree)
      tree = subtree
    elif m_no_space.startswith(r'\if'):
      if m_no_space[1:] in exceptions:
        continue
      subtree = new_subtree('unknown')
      subtree['start'] = m
      add_subtree(tree, subtree)
      tree = subtree
    elif m_no_space == r'\else':
      if tree['parent'] is None:
        print_abort(r'unmatched \else')
        return text
      elif 'else' in tree:
        print_abort(r'duplicate \else')
        return text

      tree['else'] = m
    elif m.group() == r'\fi':
      if tree['parent'] is None:
        print_abort(r'unmatched \fi')
        return text

      tree['end'] = m
      tree = tree['parent']
    else:
      raise RuntimeError('Unreachable!')

  if tree['parent'] is not None:
    print_abort('unmatched ' + tree['start'].group())
    return text

  positions_to_delete = []

  def traverse_tree(tree):
    if tree['kind'] == 'iffalse':
      if 'else' in tree:
        positions_to_delete.append((tree['start'].start(), tree['else'].end()))
        for subtree in tree['right']:
          traverse_tree(subtree)
        positions_to_delete.append((tree['end'].start(), tree['end'].end()))
      else:
        positions_to_delete.append((tree['start'].start(), tree['end'].end()))
    elif tree['kind'] == 'iftrue':
      if 'else' in tree:
        positions_to_delete.append((tree['start'].start(), tree['start'].end()))
        for subtree in tree['left']:
          traverse_tree(subtree)
        positions_to_delete.append((tree['else'].start(), tree['end'].end()))
      else:
        positions_to_delete.append((tree['start'].start(), tree['start'].end()))
        positions_to_delete.append((tree['end'].start(), tree['end'].end()))
    elif tree['kind'] == 'unknown':
      for subtree in tree['left']:
        traverse_tree(subtree)
      for subtree in tree['right']:
        traverse_tree(subtree)
    else:
      raise ValueError('Unreachable!')

  for tree in toplevel_tree['left']:
    traverse_tree(tree)

  for start, end in reversed(positions_to_delete):
    if end < len(text) and text[end].isspace():
      end_to_del = end + 1
    else:
      end_to_del = end
    text = text[:start] + text[end_to_del:]

  return text


def _remove_comments_inline(text):
  """Removes the comments from the string 'text' and ignores % inside \\url{}."""
  auto_ignore_pattern = r'(%\s*auto-ignore).*'
  if regex.search(auto_ignore_pattern, text):
    return regex.sub(auto_ignore_pattern, r'\1', text)

  if text.lstrip(' ').lstrip('\t').startswith('%'):
    return ''

  url_pattern = r'\\url\{(?>[^{}]|(?R))*\}'

  def remove_comments(segment):
    """Check if a segment of text contains a comment and remove it."""
    if segment.lstrip().startswith('%'):
      return '', True
    match = regex.search(r'(?<!\\)%', segment)
    if match:
      return segment[: match.end()] + '\n', True
    else:
      return segment, False

  # split the text into segments based on \url{} tags
  segments = regex.split(f'({url_pattern})', text)

  for i in range(len(segments)):
    # only process segments that are not part of a \url{} tag
    if not regex.match(url_pattern, segments[i]):
      segments[i], match = remove_comments(segments[i])
      if match:
        # remove all segments after the first inline comment
        segments = segments[: i + 1]
        break

  final_text = ''.join(segments)
  return (
      final_text
      if final_text.endswith('\n') or final_text.endswith('\\n')
      else final_text + '\n'
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


def _remove_comments_and_commands_to_delete(content, parameters):
  """Erases all LaTeX comments in the content, and writes it."""
  content = [_remove_comments_inline(line) for line in content]
  content = _remove_environment(''.join(content), 'comment')
  content = _simplify_conditional_blocks(
      content, parameters.get('if_exceptions', [])
  )
  for environment in parameters.get('environments_to_delete', []):
    content = _remove_environment(content, environment)
  for command in parameters.get('commands_only_to_delete', []):
    content = _remove_command(content, command, True)
  for command in parameters['commands_to_delete']:
    content = _remove_command(content, command, False)
  return content


def _replace_tikzpictures(content, figures):
  """Replaces all tikzpicture environments (with includegraphic commands of

  external PDF figures) in the content, and writes it.
  """

  def get_figure(matchobj):
    found_tikz_filename = regex.search(
        r'\\tikzsetnextfilename{(.*?)}', matchobj.group(0)
    ).group(1)
    # search in tex split if figure is available
    matching_tikz_filenames = _keep_pattern(
        figures, ['/' + found_tikz_filename + '.pdf']
    )
    if len(matching_tikz_filenames) == 1:
      return '\\includegraphics{' + matching_tikz_filenames[0] + '}'
    else:
      return matchobj.group(0)

  content = regex.sub(
      r'\\tikzsetnextfilename{[\s\S]*?\\end{tikzpicture}', get_figure, content
  )

  return content


def _replace_includesvg(content, svg_inkscape_files):
  def repl_svg(matchobj):
    svg_path = matchobj.group(2)
    if svg_path.endswith('.svg'):
      svg_path = '_'.join(svg_path.rsplit('.', 1))
    svg_filename = os.path.basename(svg_path)

    # search in svg_inkscape split if pdf_tex file is available
    matching_pdf_tex_files = _keep_pattern(
        svg_inkscape_files, ['/' + svg_filename + '-tex.pdf_tex']
    )
    if len(matching_pdf_tex_files) == 1:
      options = '' if matchobj.group(1) is None else matchobj.group(1)
      res = f'\\includeinkscape{options}{{{matching_pdf_tex_files[0]}}}'
      return res
    else:
      return matchobj.group(0)

  content = regex.sub(r'\\includesvg(\[.*?\])?{(.*?)}', repl_svg, content)

  return content

def _resize_and_copy_figure(
    filename,
    origin_folder,
    destination_folder,
    resize_image,
    image_size,
    compress_pdf,
    pdf_resolution,
    convert_png_to_jpg=False,
    png_quality=50,
    png_size_threshold=0.5,
    verbose=False
):
    """Resizes and copies the input figure (either JPG, PNG, or PDF).
    
    New parameters:
        convert_png_to_jpg: Convert PNG files to JPG format
        png_quality: JPG quality for converted PNG files (0-100)
        png_size_threshold: Minimum file size in MB to apply quality reduction
        verbose: Enable verbose logging
    
    Returns:
        str: The actual output filename (may differ from input if PNG was converted)
    """
    _create_dir_if_not_exists(
        os.path.join(destination_folder, os.path.dirname(filename))
    )
    
    if convert_png_to_jpg and os.path.splitext(filename)[1].lower() in ['.png']:
        original_size_mb = os.path.getsize(os.path.join(origin_folder, filename)) / (1024 * 1024)
        im = Image.open(os.path.join(origin_folder, filename))
        # Determine quality based on file size
        if original_size_mb < png_size_threshold:
            quality = 100  # Keep high quality for small files
            if verbose:
                print(f"Keeping original quality for small PNG: {filename}")
        else:
            quality = png_quality
            if verbose:
                print(f"Converting PNG to JPG with quality {quality}: {filename}")
        
        # Convert PNG to JPG
        output_filename = os.path.splitext(filename)[0] + '.jpg'
        rgb_img = im.convert('RGB')
        rgb_img.save(os.path.join(destination_folder, output_filename), 'JPEG', quality=quality)
        
        if verbose:
            print(f"Converted: {filename} -> {output_filename}")
          
        return output_filename
                    
    if resize_image and os.path.splitext(filename)[1].lower() in [
        '.jpg',
        '.jpeg',
        '.png',
    ]:
        try:
            im = Image.open(os.path.join(origin_folder, filename))
            if max(im.size) > image_size:
                im = im.resize(
                    tuple([int(x * float(image_size) / max(im.size)) for x in im.size]),
                    Image.Resampling.LANCZOS,
                )
            
            if os.path.splitext(filename)[1].lower() in ['.jpg', '.jpeg']:
                im.save(os.path.join(destination_folder, filename), 'JPEG', quality=90)
                return filename
                
            elif os.path.splitext(filename)[1].lower() in ['.png']:
                im.save(os.path.join(destination_folder, filename), 'PNG')
                return filename
                    
        except Exception as e:
            if verbose:
                print(f"Failed to process image {filename}: {e}")
            # Fall back to simple copy
            shutil.copy(
                os.path.join(origin_folder, filename),
                os.path.join(destination_folder, filename),
            )
            return filename

    elif compress_pdf and os.path.splitext(filename)[1].lower() == '.pdf':
        _resize_pdf_figure(
            filename, origin_folder, destination_folder, pdf_resolution
        )
        return filename
    else:
        shutil.copy(
            os.path.join(origin_folder, filename),
            os.path.join(destination_folder, filename),
        )
        return filename


def _update_image_references(tex_contents_dict, old_filename, new_filename, verbose=False):
    """Update references from old_filename to new_filename in all tex content."""
    if old_filename == new_filename:
        return  # No change needed
    
    old_base = os.path.splitext(old_filename)[0]
    new_base = os.path.splitext(new_filename)[0]
    
    if verbose:
        print(f"Updating LaTeX references: {old_filename} -> {new_filename}")
    
    for tex_file in tex_contents_dict:
        # Handle both string and list content
        if isinstance(tex_contents_dict[tex_file], list):
            content = ''.join(tex_contents_dict[tex_file])
        else:
            content = tex_contents_dict[tex_file]
        
        content_changed = False
        
        # Pattern 1: Direct filename with extension
        pattern1 = r'(\{[^}]*?)' + regex.escape(old_filename) + r'(\})'
        replacement1 = r'\1' + new_filename + r'\2'
        
        new_content = regex.sub(pattern1, replacement1, content, flags=regex.IGNORECASE)
        if new_content != content:
            content = new_content
            content_changed = True
        
        # Pattern 2: Base filename with optional .png extension
        pattern2 = r'(\{[^}]*?)' + regex.escape(old_base) + r'(\.png)?(\})'
        replacement2 = r'\1' + new_base + r'.jpg\3'
        
        new_content = regex.sub(pattern2, replacement2, content, flags=regex.IGNORECASE)
        if new_content != content:
            content = new_content
            content_changed = True
        
        # Update the content back in the appropriate format
        if content_changed:
            if isinstance(tex_contents_dict[tex_file], list):
                # Convert back to list format, preserving line endings
                tex_contents_dict[tex_file] = content.split('\n')
            else:
                tex_contents_dict[tex_file] = content
            
            if verbose:
                print(f"Updated references in {tex_file}")
    
    # Re-write the updated tex files to the output directory
    if verbose and any(tex_contents_dict.values()):
        print("Re-writing updated tex files...")
    
    return tex_contents_dict


def _resize_pdf_figure(
    filename, origin_folder, destination_folder, resolution, timeout=10
):
  input_file = os.path.join(origin_folder, filename)
  output_file = os.path.join(destination_folder, filename)
  bash_command = PDF_RESIZE_COMMAND.format(
      input=input_file, output=output_file, resolution=resolution
  )
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
      splits['non_tex_not_in_root'], contents, strict=True
  ):
    _copy_file(fn, parameters)

def _resize_and_copy_figures_if_referenced(parameters, contents, splits):
    """Modified to handle PNG to JPG conversion and reference updates."""
    image_size = collections.defaultdict(lambda: parameters['im_size'])
    image_size.update(parameters['images_allowlist'])
    pdf_resolution = collections.defaultdict(
        lambda: parameters['pdf_im_resolution']
    )
    pdf_resolution.update(parameters['images_allowlist'])
    
    # contents is the full content string for reference checking
    
    filename_changes = {}  # Track PNG -> JPG filename changes
    
    for image_file in _keep_only_referenced(
        splits['figures'], contents, strict=False
    ):
        actual_output_filename = _resize_and_copy_figure(
            filename=image_file,
            origin_folder=parameters['input_folder'],
            destination_folder=parameters['output_folder'],
            resize_image=parameters['resize_images'],
            image_size=image_size[image_file],
            compress_pdf=parameters['compress_pdf'],
            pdf_resolution=pdf_resolution[image_file],
            convert_png_to_jpg=parameters.get('convert_png_to_jpg', False),
            png_quality=parameters.get('png_quality', 50),
            png_size_threshold=parameters.get('png_size_threshold', 0.5),
            verbose=parameters.get('verbose', False)
        )
        
        # Track filename changes for reference updates
        if actual_output_filename != image_file:
            filename_changes[image_file] = actual_output_filename
    
    return filename_changes


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
  file_splits['to_copy_in_root'] = _remove_pattern(
      file_splits['in_root'],
      parameters['to_delete'] + parameters['figures_to_copy_if_referenced'],
  )
  file_splits['to_copy_not_in_root'] = _remove_pattern(
      file_splits['not_in_root'],
      parameters['to_delete'] + parameters['figures_to_copy_if_referenced'],
  )
  file_splits['figures'] = _keep_pattern(
      file_splits['all'], parameters['figures_to_copy_if_referenced']
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

    filename_changes = _resize_and_copy_figures_if_referenced(parameters, full_content, splits)
    logging.info('Outputs written to %s', parameters['output_folder'])

    # Update LaTeX references for changed filenames if tex_contents_dict is provided
    if tex_contents and filename_changes:
        for old_filename, new_filename in filename_changes.items():
            tex_contents = _update_image_references(
                tex_contents, old_filename, new_filename, 
                verbose=parameters.get('verbose', False)
            )

        # Re-write modified tex files with new references after resizing and copying figures
        for tex_file in splits['tex_to_copy']:
            if tex_file in tex_contents:
                # Get the updated content
                if isinstance(tex_contents[tex_file], list):
                    updated_content = ''.join(tex_contents[tex_file])
                else:
                    updated_content = tex_contents[tex_file]
                
                # Write the updated content back to the output file
                output_path = os.path.join(parameters['output_folder'], tex_file)
                logging.info('Re-writing modified tex file with updated references: %s', output_path)
                _write_file_content(updated_content, output_path)
                
                if parameters.get('verbose', False):
                    print(f"Re-wrote {tex_file} with updated image references")
        
        if parameters.get('verbose', False):
            print(f"Updated {len(filename_changes)} image references and re-wrote tex files")


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
  r"""content: str

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
      content = content[: m.start()] + local_insertion + content[m.end() :]
      m = p.search(content)
    logging.info('Finished pattern: %s.', description)
  return content
