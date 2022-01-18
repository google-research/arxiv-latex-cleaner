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
"""Main module for ``arxiv_latex_cleaner``.

.. code-block:: bash

    $ python -m arxiv_latex_cleaner --help
"""
import argparse
import json
import logging

from ._version import __version__
from .arxiv_latex_cleaner import merge_args_into_config
from .arxiv_latex_cleaner import run_arxiv_cleaner

import yaml

PARSER = argparse.ArgumentParser(
    prog="arxiv_latex_cleaner@{0}".format(__version__),
    description=("Clean the LaTeX code of your paper to submit to arXiv. "
                 "Check the README for more information on the use."),
)

PARSER.add_argument(
    "input_folder", type=str, help="Input folder containing the LaTeX code.")

PARSER.add_argument(
    "--resize_images",
    action="store_true",
    help="Resize images.",
)

PARSER.add_argument(
    "--im_size",
    default=500,
    type=int,
    help=("Size of the output images (in pixels, longest side). Fine tune this "
          "to get as close to 10MB as possible."),
)

PARSER.add_argument(
    "--compress_pdf",
    action="store_true",
    help="Compress PDF images using ghostscript (Linux and Mac only).",
)

PARSER.add_argument(
    "--pdf_im_resolution",
    default=500,
    type=int,
    help="Resolution (in dpi) to which the tool resamples the PDF images.",
)

PARSER.add_argument(
    "--images_whitelist",
    default={},
    type=json.loads,
    help=("Images (and PDFs) that won't be resized to the default resolution,"
          "but the one provided here. Value is pixel for images, and dpi for"
          "PDFs, as in --im_size and --pdf_im_resolution, respectively. Format "
          "is a dictionary as: '{\"path/to/im.jpg\": 1000}'"),
)

PARSER.add_argument(
    "--keep_bib",
    action="store_true",
    help="Avoid deleting the *.bib files.",
)

PARSER.add_argument(
    "--commands_to_delete",
    nargs="+",
    default=[],
    required=False,
    help=(
        "LaTeX commands that will be deleted. Useful for e.g. user-defined "
        "\\todo commands. For example, to delete all occurrences of \\todo1{} "
        "and \\todo2{}, run the tool with `--commands_to_delete todo1 todo2`."
        "Please note that the positional argument `input_folder` cannot come "
        "immediately after `commands_to_delete`, as the parser does not have "
        "any way to know if it's another command to delete."),
)

PARSER.add_argument(
    "--use_external_tikz",
    type=str,
    help=("Folder (relative to input folder) containing externalized tikz "
          "figures in PDF format."))

PARSER.add_argument(
    "--config",
    type=str,
    help=("Read settings from `.yaml` config file. If command line arguments "
          "are provided additionally, the config file parameters are updated "
          "with the command line parameters."),
    required=False,
)

PARSER.add_argument(
    "--verbose",
    action="store_true",
    help="Enable detailed output.",
)

ARGS = vars(PARSER.parse_args())

if ARGS["config"] is not None:
  try:
    with open(ARGS["config"], "r") as config_file:
      config_params = yaml.safe_load(config_file)
    final_args = merge_args_into_config(ARGS, config_params)

  except FileNotFoundError:
    print(f"config file {ARGS.config} not found.")
    final_args = ARGS
    final_args.pop("config", None)
else:
  final_args = ARGS

if final_args.get("verbose", False):
  logging.basicConfig(level=logging.INFO)
else:
  logging.basicConfig(level=logging.ERROR)

run_arxiv_cleaner(final_args)
exit(0)
