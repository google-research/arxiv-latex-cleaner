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

from setuptools import setup
from setuptools import find_packages
from os import path

# Get __version__ from _meta.py
with open(path.join("arxiv_latex_cleaner", "_version.py")) as _fh:
    exec(_fh.read())

setup(
    name="arxiv_latex_cleaner",
    version=__version__,
    packages=find_packages(exclude=["*_test.py"]),
    url="https://github.com/google-research/arxiv-latex-cleaner",
    license="Apache License, Version 2.0",
    author="Google Research Authors",
    author_email="jponttuset@gmail.com",
    description="Cleans the LaTeX code of your paper to submit to arXiv.",
    entry_points={
        "console_scripts": ["arxiv_latex_cleaner=arxiv_latex_cleaner.__main__:__main__"]
    },
    install_requires=["absl_py", "Pillow"],
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Intended Audience :: Science/Research",
    ],
)
