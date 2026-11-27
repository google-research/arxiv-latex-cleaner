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
"""Image resizing, PNG-to-JPG conversion, and PDF compression helpers."""

import collections
import logging
import os
import shutil
import subprocess

from PIL import Image
import regex

from . import file_ops

_create_dir_if_not_exists = file_ops._create_dir_if_not_exists
_keep_only_referenced = file_ops._keep_only_referenced


def _convert_image_to_rgb(im):
  """Converts a PIL Image to RGB, compositing transparency onto white."""
  if im.mode in ('RGBA', 'LA') or (
      im.mode == 'P' and 'transparency' in im.info
  ):
    rgba = im.convert('RGBA')
    background = Image.new('RGB', rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.getchannel('A'))
    return background
  return im.convert('RGB')

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
    verbose=False,
):
  """Resizes and copies the input figure (either JPG, PNG, or PDF).

  Args:
    filename: The input filename.
    origin_folder: The folder containing the input filename.
    destination_folder: The folder to copy the output filename to.
    resize_image: Whether to resize the image.
    image_size: The maximum size of the image in pixels.
    compress_pdf: Whether to compress the PDF file.
    pdf_resolution: Resolution (in dpi) for compressed PDFs.
    convert_png_to_jpg: Whether to convert PNG files to JPG format. Note that
      this overrides resize_image for PNG files.
    png_quality: JPG quality for converted PNG files (0-100).
    png_size_threshold: Minimum file size in MB to apply quality reduction.
    verbose: Unused (retained for backwards compatibility; use logging level).

  Returns:
    The actual output filename (may differ from input if PNG was converted).
  """
  del verbose  # Handled via logging level.
  _create_dir_if_not_exists(
      os.path.join(destination_folder, os.path.dirname(filename))
  )
  src_path = os.path.join(origin_folder, filename)
  ext = os.path.splitext(filename)[1].lower()

  if convert_png_to_jpg and ext == '.png':
    try:
      original_size_mb = os.path.getsize(src_path) / (1024 * 1024)
      with Image.open(src_path) as im:
        if original_size_mb < png_size_threshold:
          quality = 100  # Keep high quality for small files.
          logging.info('Keeping original quality for small PNG: %s', filename)
        else:
          quality = png_quality
          logging.info(
              'Converting PNG to JPG with quality %d: %s', quality, filename
          )

        output_filename = os.path.splitext(filename)[0] + '.jpg'
        rgb_img = _convert_image_to_rgb(im)
        rgb_img.save(
            os.path.join(destination_folder, output_filename),
            'JPEG',
            quality=quality,
        )
        logging.info('Converted: %s -> %s', filename, output_filename)
        return output_filename
    except Exception as e:
      logging.warning(
          'Failed to convert PNG %s to JPG (%s); copying original.', filename, e
      )
      shutil.copy(src_path, os.path.join(destination_folder, filename))
      return filename

  if resize_image and ext in ('.jpg', '.jpeg', '.png'):
    try:
      with Image.open(src_path) as im:
        if max(im.size) > image_size:
          im = im.resize(
              tuple(int(x * float(image_size) / max(im.size)) for x in im.size),
              Image.Resampling.LANCZOS,
          )
        if ext in ('.jpg', '.jpeg'):
          im.save(
              os.path.join(destination_folder, filename), 'JPEG', quality=90
          )
          return filename
        if ext == '.png':
          im.save(os.path.join(destination_folder, filename), 'PNG')
          return filename
    except Exception as e:
      logging.warning(
          'Failed to process image %s (%s); copying original.', filename, e
      )
      shutil.copy(src_path, os.path.join(destination_folder, filename))
      return filename

  if compress_pdf and ext == '.pdf':
    _resize_pdf_figure(
        filename, origin_folder, destination_folder, pdf_resolution
    )
    return filename

  shutil.copy(src_path, os.path.join(destination_folder, filename))
  return filename

def _update_image_references(
    tex_contents_dict, old_filename, new_filename, verbose=False
):
  """Updates references from old_filename to new_filename in all tex content."""
  del verbose  # Handled via logging level.
  if old_filename == new_filename:
    return  # No change needed

  old_base = os.path.splitext(old_filename)[0]
  new_base = os.path.splitext(new_filename)[0]

  logging.info('Updating LaTeX references: %s -> %s', old_filename, new_filename)

  for tex_file in tex_contents_dict:
    # Handle both string and list content.
    if isinstance(tex_contents_dict[tex_file], list):
      content = ''.join(tex_contents_dict[tex_file])
    else:
      content = tex_contents_dict[tex_file]

    content_changed = False

    # Pattern 1: Direct filename with full extension, handling comments/newlines.
    pattern1 = (
        r'(\{(?:%\s*\n\s*)?[^}]*?)'
        + regex.escape(old_filename)
        + r'((?:%\s*\n\s*)?[^}]*?\})'
    )
    replacement1 = r'\1' + new_filename + r'\2'

    new_content = regex.sub(
        pattern1, replacement1, content, flags=regex.IGNORECASE | regex.DOTALL
    )
    if new_content != content:
      content = new_content
      content_changed = True
      logging.info('Applied pattern 1 (full filename) in %s', tex_file)
    else:
      # Pattern 2: Base filename without extension, handling comments/newlines.
      # Only apply if Pattern 1 didn't match to avoid double replacements.
      pattern2 = (
          r'(\{(?:%\s*\n\s*)?[^}]*?)'
          + regex.escape(old_base)
          + r'((?:%\s*\n\s*)?[^}]*?\})'
      )
      replacement2 = r'\1' + new_base + r'.jpg\2'

      new_content = regex.sub(
          pattern2, replacement2, content, flags=regex.IGNORECASE | regex.DOTALL
      )
      if new_content != content:
        content = new_content
        content_changed = True
        logging.info('Applied pattern 2 (base filename) in %s', tex_file)
      else:
        # Pattern 3: Extension split across lines with comments (e.g. name%\n.png).
        pattern3 = (
            r'(\{[^}]*?)'
            + regex.escape(old_base)
            + r'(%\s*\n\s*)(\.png)([^}]*?\})'
        )
        replacement3 = r'\1' + new_base + r'\2.jpg\4'

        new_content = regex.sub(
            pattern3,
            replacement3,
            content,
            flags=regex.IGNORECASE | regex.DOTALL,
        )
        if new_content != content:
          content = new_content
          content_changed = True
          logging.info('Applied pattern 3 (split extension) in %s', tex_file)

    if content_changed:
      if isinstance(tex_contents_dict[tex_file], list):
        tex_contents_dict[tex_file] = content.split('\n')
      else:
        tex_contents_dict[tex_file] = content
      logging.info('Updated references in %s', tex_file)

  return tex_contents_dict

def _resize_pdf_figure(
    filename, origin_folder, destination_folder, resolution, timeout=10
):
  """Resizes a PDF figure using Ghostscript."""
  input_file = os.path.abspath(os.path.join(origin_folder, filename))
  output_file = os.path.abspath(os.path.join(destination_folder, filename))
  escaped_output_file = output_file.replace('%', '%%')
  command = [
      'gs',
      '-sDEVICE=pdfwrite',
      '-dCompatibilityLevel=1.4',
      '-dSAFER',
      '-dNOPAUSE',
      '-dQUIET',
      '-dBATCH',
      '-dDownsampleColorImages=true',
      f'-dColorImageResolution={int(resolution)}',
      '-dColorImageDownsampleThreshold=1.0',
      '-dAutoRotatePages=/None',
      f'-sOutputFile={escaped_output_file}',
      '-f',
      input_file,
  ]
  process = subprocess.Popen(command, stdout=subprocess.PIPE)

  try:
    process.communicate(timeout=timeout)
  except subprocess.TimeoutExpired:
    process.kill()
    outs, errs = process.communicate()
    print('Output: ', outs)
    print('Errors: ', errs)

def _find_parent_relative_figures(figures, tex_contents, tex_files):
  """Resolve ../figure references relative to their source TeX files.

  Figures are still copied using their project-relative paths, preserving the
  original LaTeX reference in the copied TeX file. References escaping the
  input project root are not eligible for copying.
  """
  candidates = {
      file.casefold(): file for file in figures
  }
  referenced = set()
  for tex_file in tex_files:
    content = tex_contents[tex_file]
    if isinstance(content, list):
      content = ''.join(content)
    source_dir = os.path.dirname(tex_file)
    for match in regex.finditer(r'\{([^{}]+)\}', content):
      target = match.group(1).strip()
      if not target.startswith('../') or '\\' in target:
        continue
      relative_path = os.path.normpath(
          os.path.join(source_dir, target)
      ).replace('\\', '/')
      if (
          os.path.isabs(relative_path)
          or relative_path == '..'
          or relative_path.startswith('../')
      ):
        continue
      # In LaTeX, the extension may be omitted in \includegraphics.
      match_name = candidates.get(relative_path.casefold())
      if match_name is not None:
        referenced.add(match_name)
      else:
        for figure in figures:
          if os.path.splitext(figure)[0].casefold() == relative_path.casefold():
            referenced.add(figure)
  return referenced

def _resize_and_copy_figures_if_referenced(
    parameters, contents, splits, tex_contents=None
):
    """Copy referenced figures, including ../ paths from nested TeX files."""
    image_size = collections.defaultdict(lambda: parameters['im_size'])
    image_size.update(parameters['images_allowlist'])
    pdf_resolution = collections.defaultdict(
        lambda: parameters['pdf_im_resolution']
    )
    pdf_resolution.update(parameters['images_allowlist'])
    
    # contents is the full content string for reference checking
    
    filename_changes = {}  # Track PNG -> JPG filename changes
    
    referenced = set(
        _keep_only_referenced(splits['figures'], contents, strict=False)
    )
    if tex_contents is not None:
        referenced.update(
            _find_parent_relative_figures(
                splits['figures'], tex_contents, splits['tex_to_copy']
            )
        )

    for image_file in splits['figures']:
        if image_file not in referenced:
            continue
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
