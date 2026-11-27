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
"""Pure LaTeX text cleaning, comment removal, and macro rewriting."""

import dataclasses
import enum
import logging
import os
import sys
from typing import List, Optional

import regex

from .file_ops import _keep_pattern


def _remove_command(text, command, keep_text=False):
  """Removes '\\command{*}' from the string 'text'.

  Regex `base_pattern` used to match balanced parentheses taken from:
  https://stackoverflow.com/questions/546433/regular-expression-to-match-balanced-parentheses/35271017#35271017
  """
  base_pattern = (
      r'\\'
      + regex.escape(command)
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

      if keep_text:
        # A command on its own line may wrap text with newlines inside its
        # braces. Removing just the command leaves two newlines at the opening
        # and closing boundaries, creating a TeX paragraph (invalid inside
        # commands such as \\caption). Remove only these redundant boundaries.
        before = text[: match.start()]
        after = text[match.end() :]
        if regex.search(r'(?:^|\n)[ \t]*$', before):
          new_substring = regex.sub(r'^\n[ \t]*', '', new_substring, count=1)
        if regex.match(r'[ \t]*\n', after):
          new_substring = regex.sub(r'\n[ \t]*$', '', new_substring)

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

def _simplify_conditional_blocks(text, if_exceptions=None):
  r"""Simplify possibly nested conditional blocks from 'text'.

  For example, `\iffalse TEST1\else TEST2\fi` is simplified to `TEST2`,
  and `\iftrue TEST1\else TEST2\fi` is simplified to `TEST1`.
  Unknown conditionals are left untouched.

  If the conditional tree is malformed, the function will print a warning
  to stderr and return the original text.
  """

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
  ] + list(if_exceptions or ())

  @dataclasses.dataclass
  class TokenRange:
    start: int
    end: int
    gobble_trailing_space: bool = True

    def extend_to(self, other: 'TokenRange') -> 'TokenRange':
      assert self.end <= other.start
      return TokenRange(self.start, other.end, other.gobble_trailing_space)

  class NodeKind(enum.Enum):
    TOPLEVEL = 'toplevel'
    IFFALSE = 'iffalse'
    IFTRUE = 'iftrue'
    UNKNOWN = 'unknown'

  @dataclasses.dataclass
  class ConditionNode:
    kind: NodeKind
    left: List['ConditionNode'] = dataclasses.field(default_factory=list)
    right: List['ConditionNode'] = dataclasses.field(default_factory=list)
    parent: Optional['ConditionNode'] = None
    if_token: Optional[TokenRange] = None
    else_token: Optional[TokenRange] = None
    fi_token: Optional[TokenRange] = None

    def add_subtree(self, subtree: 'ConditionNode') -> None:
      if self.else_token is None:
        self.left.append(subtree)
      else:
        self.right.append(subtree)
      subtree.parent = self
  
    def print(self, indent, write):
      if self.if_token is not None:
        write(' ' * indent + text[self.if_token.start : self.if_token.end] + '\n')
      for subtree in self.left:
        subtree.print(indent + 2, write)
      if self.else_token is not None:
        write(' ' * indent + text[self.else_token.start : self.else_token.end] + '\n')
      for subtree in self.right:
        subtree.print(indent + 2, write)
      if self.fi_token is not None:
        write(' ' * indent + text[self.fi_token.start : self.fi_token.end] + '\n')

  def _parse_conditional_tree() -> Optional[ConditionNode]:

    def print_abort(error_finding, tree):
      sys.stderr.write(
          f'Warning: Found {error_finding}! Not removing any conditional'
          ' blocks...\n'
      )
      sys.stderr.write(
          '         This is the matched tree (as built up to the error):\n'
      )
      tree.print(indent=9, write=sys.stderr.write)
      sys.stderr.write(
          '         Potentially, you need to supply an exception using'
          " --if_exceptions'.\n"
      )

    toplevel_tree = ConditionNode(NodeKind.TOPLEVEL)
    tree = toplevel_tree
    p = regex.compile(r'(?!(?<=\\newif\s*))\\if([a-zA-Z]*)|\\else(?![a-zA-Z])|\\fi(?![a-zA-Z])')
    for m in p.finditer(text):
      match = m.group()

      if match == r'\iffalse':
        subtree = ConditionNode(
          NodeKind.IFFALSE,
          if_token = TokenRange(m.start(), m.end())
        )
        tree.add_subtree(subtree)
        tree = subtree
      elif match == r'\iftrue':
        subtree = ConditionNode(
          NodeKind.IFTRUE,
          if_token = TokenRange(m.start(), m.end())
        )
        tree.add_subtree(subtree)
        tree = subtree
      elif match == r'\if':
        tokens = regex.match(r'^\s*([a-zA-Z0-9])([a-zA-Z0-9 \n])', text[m.end():])
        if tokens:
          subtree = ConditionNode(
            NodeKind.IFTRUE if tokens.group(1) == tokens.group(2) else NodeKind.IFFALSE,
            if_token = TokenRange(m.start(), m.end() + tokens.end(), False)
          )
        else:
          subtree = ConditionNode(
            NodeKind.UNKNOWN,
            if_token = TokenRange(m.start(), m.end())
          )
        tree.add_subtree(subtree)
        tree = subtree
      elif match.startswith(r'\if'):
        if match[1:] in exceptions:
          continue
        subtree = ConditionNode(
          NodeKind.UNKNOWN,
          if_token = TokenRange(m.start(), m.end())
        )
        tree.add_subtree(subtree)
        tree = subtree
      elif match == r'\else':
        if tree.parent is None:
          print_abort(r'unmatched \else', toplevel_tree)
          return None
        elif tree.else_token is not None:
          print_abort(r'duplicate \else', toplevel_tree)
          return None

        tree.else_token = TokenRange(m.start(), m.end())
      elif m.group() == r'\fi':
        if tree.parent is None:
          print_abort(r'unmatched \fi', toplevel_tree)
          return None

        tree.fi_token = TokenRange(m.start(), m.end())
        tree = tree.parent
      else:
        raise RuntimeError('Unreachable!')

    if tree.parent is not None:
      print_abort('unmatched ' + text[tree.if_token.start : tree.if_token.end], toplevel_tree)
      return None

    return toplevel_tree

  def _get_deletion_ranges(tree: ConditionNode):
    ranges = []
    if tree.kind == NodeKind.TOPLEVEL:
      for subtree in tree.left:
        ranges.extend(_get_deletion_ranges(subtree))
    elif tree.kind == NodeKind.IFFALSE:
      if tree.else_token is not None:
        ranges.append(tree.if_token.extend_to(tree.else_token))
        for subtree in tree.right:
          ranges.extend(_get_deletion_ranges(subtree))
        ranges.append(tree.fi_token)
      else:
        ranges.append(tree.if_token.extend_to(tree.fi_token))
    elif tree.kind == NodeKind.IFTRUE:
      ranges.append(tree.if_token)
      for subtree in tree.left:
        ranges.extend(_get_deletion_ranges(subtree))
      if tree.else_token is not None:
        ranges.append(tree.else_token.extend_to(tree.fi_token))
      else:
        ranges.append(tree.fi_token)
    elif tree.kind == NodeKind.UNKNOWN:
      for subtree in tree.left:
        ranges.extend(_get_deletion_ranges(subtree))
      for subtree in tree.right:
        ranges.extend(_get_deletion_ranges(subtree))
    else:
      raise ValueError('Unreachable!')
    return ranges

  def _delete_ranges(text: str, ranges: List[TokenRange]):
    for token_range in reversed(ranges):
      start = token_range.start
      end = token_range.end
      gobble_trailing_space = token_range.gobble_trailing_space

      # Check if a blank line would be created by this deletion.
      # TeX interprets blank lines specially, so we avoid these.
      prev_newline_idx = text.rfind('\n', 0, start)
      line_start_idx = prev_newline_idx + 1
      deletion_starts_new_line = text[line_start_idx : start].isspace() or len(text[line_start_idx : start]) == 0
      next_newline_idx = text.find('\n', end)
      line_end_idx = next_newline_idx + 1 if next_newline_idx > -1 else len(text)
      text_after_deletion = (
        text[end:next_newline_idx]
        if next_newline_idx > -1
        else text[end:]
      )
      deletion_ends_new_line = (
        text_after_deletion.isspace() or len(text_after_deletion) == 0
      )
      if deletion_starts_new_line and deletion_ends_new_line:
        start_to_del = line_start_idx
        end_to_del = line_end_idx
      else:
        start_to_del = start
        end_to_del = end
        # We sometimes have to remove trailing whitespace.
        # Example: `ab\iftrue cd\fi ef` produces `abcdef`.
        # We should not remove trailing whitespace, if there is a command in front of
        # the deletion, e.g. `\test\iftrue ab\fi` should produce `\test ab`, not `\testab`.
        if gobble_trailing_space:
          command_in_front = (regex.search(r'\\[a-zA-Z]*\Z', text[:start]) != None)
          if not command_in_front:
            while len(text) > end_to_del and text[end_to_del] in ["\t", " "]:
              end_to_del += 1

      text = text[:start_to_del] + text[end_to_del:]

    return text

  tree = _parse_conditional_tree()
  if tree is None:
    return text

  ranges = _get_deletion_ranges(tree)
  return _delete_ranges(text, ranges)

# A % inside these environments is code, not a comment.
VERBATIM_ENVIRONMENTS = ['verbatim', 'Verbatim', 'lstlisting', 'minted']

def _find_unescaped_percent(text):
  r"""Returns the first match of an unescaped '%' in 'text', or None.

  A '%' preceded by an odd number of backslashes (e.g. '\%') is escaped; an
  even number (e.g. '\\%', line break + comment) starts a comment.
  """
  for match in regex.finditer(r'\\*%', text):
    if (len(match[0]) - 1) % 2 == 0:
      return match
  return None

def _remove_comments_inline(text):
  """Removes the comments from the string 'text' and ignores % inside \\url{}."""
  auto_ignore_pattern = r'(%\s*auto-ignore).*'
  if regex.search(auto_ignore_pattern, text):
    return regex.sub(auto_ignore_pattern, r'\1', text)

  # Preserve TeX/BibTeX magic directives such as '% !BIB program = biber' or
  # '% !TeX program = pdflatex'.
  if regex.match(r'^\s*%\s*!(?:BIB|TeX)\b', text, flags=regex.IGNORECASE):
    return text

  if text.lstrip().startswith('%'):
    return ''

  url_pattern = r'\\url\{(?>[^{}]|(?R))*\}'

  def remove_comments(segment):
    """Check if a segment of text contains a comment and remove it."""
    if segment.lstrip().startswith('%'):
      return '', True
    match = _find_unescaped_percent(segment)
    if match is not None:
      return segment[: match.end()] + '\n', True
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

def _remove_comments_from_lines(text, continues_line=False):
  """Removes the comments from every line of 'text'.

  'continues_line' says that 'text' starts in the middle of a line, right
  after a verbatim environment, so its first line cannot be a comment line.
  """
  lines = text.splitlines(True)
  if not lines:
    return text
  cleaned = []
  for i, line in enumerate(lines):
    if i == 0 and continues_line:
      # A % at the start of this piece is an inline comment, not a comment
      # line. A leading character keeps _remove_comments_inline from dropping
      # the whole line.
      cleaned.append(_remove_comments_inline('x' + line)[1:])
    else:
      cleaned.append(_remove_comments_inline(line))
  if not lines[-1].endswith('\n') and cleaned[-1] == lines[-1] + '\n':
    # The last line stops short, at the \begin of a verbatim environment. It
    # only gets a newline when a comment was cut from it, since the comment
    # would run on into the environment otherwise.
    cleaned[-1] = lines[-1]
  return ''.join(cleaned)

def _is_commented_out(text, position):
  """Says whether 'position' in 'text' comes after an unescaped % on its line."""
  line_start = text.rfind('\n', 0, position) + 1
  return _find_unescaped_percent(text[line_start:position]) is not None

def _find_verbatim_environments(text, environments):
  """Yields a match per verbatim environment in 'text'.

  A \\begin behind a % is commented out, TeX never enters the environment
  there, so it does not count.
  """
  names = '|'.join(regex.escape(name) for name in environments)
  pattern = regex.compile(
      r'\\begin\{((?:' + names + r')\*?)}[\s\S]*?\\end\{\1}'
  )

  position = 0
  while True:
    match = pattern.search(text, position)
    if match is None:
      return
    if _is_commented_out(text, match.start()):
      # The rest of that line is commented out too, so carry on below it.
      line_end = text.find('\n', match.start())
      if line_end < 0:
        return
      position = line_end + 1
    else:
      yield match
      position = match.end()

def _remove_comments(text, verbatim_environments=()):
  """Removes the comments from 'text', leaving verbatim environments alone."""
  environments = list(VERBATIM_ENVIRONMENTS) + list(verbatim_environments)

  pieces = []
  position = 0
  for match in _find_verbatim_environments(text, environments):
    pieces.append(
        _remove_comments_from_lines(text[position : match.start()], position > 0)
    )
    pieces.append(match.group(0))
    position = match.end()
  pieces.append(_remove_comments_from_lines(text[position:], position > 0))
  return ''.join(pieces)

def _remove_comments_and_commands_to_delete(content, parameters):
  """Erases all LaTeX comments in the content, and writes it."""
  content = _remove_comments(
      ''.join(content), parameters.get('verbatim_environments', [])
  )
  content = _remove_environment(content, 'comment')
  content = _simplify_conditional_blocks(
      content, parameters.get('if_exceptions', [])
  )
  for environment in parameters.get('environments_to_delete', []):
    content = _remove_environment(content, environment)
  for command in parameters.get('commands_only_to_delete', []):
    content = _remove_command(content, command, True)
  for command in parameters.get('commands_to_delete', []):
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
      r'\\tikzsetnextfilename{[\s\S]*?(:?\\end{tikzpicture}|\\input{\S*?})', get_figure, content
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

def _merge_tex_files(filename, tex_contents, merged_files=None):
  """Returns the contents of 'filename' with the referenced files merged in.

  Replaces the '\\input{*}' and '\\include{*}' commands with the contents of
  the files they reference, recursively; an '\\include{*}' command is
  replaced together with the implicit '\\clearpage' before and after the file
  contents, as in 'latexpand'. A command is only replaced if the referenced
  file is a key of 'tex_contents'; the '.tex' extension may be omitted in the
  command. Unknown and circular references are left untouched. The names of
  the replaced files are added to the set 'merged_files'.
  """
  if merged_files is None:
    merged_files = set()

  def merge_file(filename, open_files):
    def replace_reference(match):
      input_filename = match.group(2)
      if input_filename.startswith('.' + os.sep):
        input_filename = input_filename[2:]
      if input_filename not in tex_contents:
        input_filename += '.tex'
      if input_filename not in tex_contents or input_filename in open_files:
        return match.group(0)
      merged_files.add(input_filename)
      merged_content = merge_file(
          input_filename, open_files | {input_filename}
      )
      # Removes the BOM potentially present at the beginning of the merged
      # file, as it is only valid there and would end up in the middle of the
      # merged output.
      merged_content = merged_content.removeprefix('\ufeff')
      if match.group(1) == 'include':
        # '\include' implies a '\clearpage' before and after the file
        # contents.
        merged_content = '\\clearpage{}\n' + merged_content + '\\clearpage{}\n'
      return merged_content

    return regex.sub(
        r'\\(input|include)[\s%]*\{[\s%]*([^\s%}]+)[\s%]*\}',
        replace_reference,
        tex_contents[filename],
    )

  return merge_file(filename, {filename})

def strip_whitespace(text):
  """Strips all whitespace characters.

  https://stackoverflow.com/questions/8270092/remove-all-whitespace-in-a-string
  """
  pattern = regex.compile(r'\s+')
  text = regex.sub(pattern, '', text)
  return text

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
