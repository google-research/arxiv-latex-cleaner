# `arxiv_latex_cleaner`

[![Run unit tests](https://github.com/google-research/arxiv-latex-cleaner/actions/workflows/tests.yml/badge.svg)](https://github.com/google-research/arxiv-latex-cleaner/actions/workflows/tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/arxiv-latex-cleaner.svg)](https://pypi.org/project/arxiv-latex-cleaner/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

`arxiv_latex_cleaner` cleans the LaTeX source of your paper for submission to
arXiv. Given a folder (or `.zip` archive) containing your LaTeX project, e.g.
`/path/to/latex/`, it creates a cleaned copy at `/path/to/latex_arXiv/` ready to
zip and upload to arXiv.

## Quick start

```bash
arxiv_latex_cleaner /path/to/latex --resize_images --im_size 500 --images_allowlist='{"images/im.png":2000}'
```

Or pass a YAML configuration file (see [cleaner_config.yaml](cleaner_config.yaml)):

```bash
arxiv_latex_cleaner /path/to/latex --config cleaner_config.yaml
```

## Installation

> [!NOTE]
> `arxiv_latex_cleaner` requires Python >= 3.9.

### pip

```bash
pip install arxiv-latex-cleaner
```

### uv / uvx

With [uv](https://docs.astral.sh/uv/getting-started/installation/), you can
install the command in an isolated tool environment:

```bash
uv tool install arxiv-latex-cleaner
arxiv_latex_cleaner /path/to/latex
```

If the installed command is not on your `PATH`, run `uv tool update-shell` and
restart your shell.

For a one-off run without a persistent installation, use `uvx`:

```bash
uvx --from arxiv-latex-cleaner arxiv_latex_cleaner /path/to/latex
```

The `--from` option specifies the package name, while `arxiv_latex_cleaner` is
the command it provides. All standard cleaner arguments can follow the command,
including `--help`.

### Homebrew (macOS)

```bash
brew install arxiv_latex_cleaner
```

### From source

```bash
git clone https://github.com/google-research/arxiv-latex-cleaner
cd arxiv-latex-cleaner/
pip install .
```

Or run directly without installing:

```bash
python -m arxiv_latex_cleaner --help
```

## Main features

### Privacy-oriented

*   Removes auxiliary build files (`.aux`, `.log`, `.out`, etc.).
*   Removes AI coding agent config/instruction files so they do not leak into
    the arXiv source (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`,
    `.windsurfrules`, `.claude/`, `.cursor/`, `.github/copilot-instructions.md`,
    and many others). Pass `--keep_agent_files` to keep them.
*   Removes all LaTeX comments (yes, those are visible on arXiv!). This also
    handles `\begin{comment}\end{comment}`, `\iffalse\fi`, and `\if0\fi` blocks.
    A `%` inside `verbatim`, `Verbatim`, `lstlisting`, and `minted` environments
    is treated as code and preserved; additional environments can be specified
    with `--verbatim_environments`.
*   Optionally removes user-defined commands via `--commands_to_delete` (such as
    `\todo{}`), or removes only the command wrapper while keeping its text via
    `--commands_only_to_delete`.
*   Optionally applies custom regex replacement rules defined in a
    `cleaner_config.yaml` file.

### Size-oriented

arXiv enforces a 50 MB submission limit. To help stay under it, the cleaner:

*   Removes unused `.tex` files (files not in the root and not included by any
    other `.tex` file).
*   Removes unused images (not referenced in any kept `.tex` file).
*   Optionally resizes images to `--im_size` pixels (longest side), with
    per-file overrides via `--images_allowlist`.
*   Optionally compresses `.pdf` figures using Ghostscript (Linux and macOS
    only), with per-file DPI overrides via `--images_allowlist`.
*   Optionally converts PNG images to JPG (`--convert_png_to_jpg`,
    `--png_quality`, `--png_size_threshold`) and updates the `.tex` references.

### Merging TeX files into a single file

Sometimes it is useful to submit a single `.tex` file instead of the full folder
structure, similar to [`latexpand`](https://ctan.org/pkg/latexpand). With
`--merge_tex_files`, the tool:

*   Recursively replaces `\input{...}` and `\include{...}` commands in root
    `.tex` files with the contents of the referenced files and omits the merged
    files from the output folder.
*   Replaces `\include{...}` together with its implicit `\clearpage` commands so
    the compiled document remains unchanged.
*   Applies all other cleaning steps as usual to the merged output. Note that
    `\includeonly` is not supported.

### TikZ picture source code concealment

To avoid uploading `tikzpicture` source code or raw simulation data,
`--use_external_tikz`:

*   Replaces `\begin{tikzpicture} ... \end{tikzpicture}` with
    `\includegraphics{EXTERNAL_TIKZ_FOLDER/picture_name.pdf}`.
*   Requires externally compiled `.pdf` figures in `EXTERNAL_TIKZ_FOLDER` (see
    the Externalization Library section of the
    [PGF/TikZ manual](https://ctan.org/pkg/pgf?lang=en)).
*   Only replaces environments preceded by `\tikzsetnextfilename{picture_name}`
    matching an externalized `picture_name.pdf`.

### Custom regex replacements with named capture groups

To revert custom LaTeX macros back to plain LaTeX on submission, add regex
replacement rules to `cleaner_config.yaml`:

```yaml
{
    "pattern" : '(?:\\figcomp{\s*)(?P<first>.*?)\s*}\s*{\s*(?P<second>.*?)\s*}\s*{\s*(?P<third>.*?)\s*}',
    "insertion" : '\parbox[c]{{ {second} \linewidth}} {{ \includegraphics[width= {third} \linewidth]{{figures/{first} }} }}',
    "description" : "Replace figcomp"
}
```

The rule above replaces `\figcomp{path}{w1}{w2}` with
`\parbox[c]{w1\linewidth}{\includegraphics[width=w2\linewidth]{figures/path}}`,
filling the insertion template from
[named capture groups](https://docs.python.org/3/library/re.html#regular-expression-examples).
Replacements run **before** `\includegraphics` scanning so all referenced
figures are copied to the cleaned output. See
[cleaner_config.yaml](cleaner_config.yaml) for a full example.

## Usage

```text
usage: arxiv_latex_cleaner@v1.0.13 [-h] [--resize_images] [--im_size IM_SIZE]
                                   [--compress_pdf]
                                   [--pdf_im_resolution PDF_IM_RESOLUTION]
                                   [--images_allowlist IMAGES_ALLOWLIST]
                                   [--keep_bib] [--keep_agent_files]
                                   [--merge_tex_files]
                                   [--commands_to_delete COMMANDS_TO_DELETE [COMMANDS_TO_DELETE ...]]
                                   [--commands_only_to_delete COMMANDS_ONLY_TO_DELETE [COMMANDS_ONLY_TO_DELETE ...]]
                                   [--environments_to_delete ENVIRONMENTS_TO_DELETE [ENVIRONMENTS_TO_DELETE ...]]
                                   [--verbatim_environments VERBATIM_ENVIRONMENTS [VERBATIM_ENVIRONMENTS ...]]
                                   [--if_exceptions IF_EXCEPTIONS [IF_EXCEPTIONS ...]]
                                   [--use_external_tikz USE_EXTERNAL_TIKZ]
                                   [--svg_inkscape [SVG_INKSCAPE]]
                                   [--convert_png_to_jpg]
                                   [--png_quality PNG_QUALITY]
                                   [--png_size_threshold PNG_SIZE_THRESHOLD]
                                   [--config CONFIG] [--verbose]
                                   input_folder

Clean the LaTeX code of your paper to submit to arXiv. Check the README for
more information on the use.

positional arguments:
  input_folder          Input folder or zip archive containing the LaTeX code.

options:
  -h, --help            show this help message and exit
  --resize_images       Resize images.
  --im_size IM_SIZE     Size of the output images (in pixels, longest side).
                        Fine tune this to get as close to 10MB as possible.
  --compress_pdf        Compress PDF images using ghostscript (Linux and Mac
                        only).
  --pdf_im_resolution PDF_IM_RESOLUTION
                        Resolution (in dpi) to which the tool resamples the
                        PDF images.
  --images_allowlist IMAGES_ALLOWLIST
                        Images (and PDFs) that won't be resized to the default
                        resolution,but the one provided here. Value is pixel
                        for images, and dpi forPDFs, as in --im_size and
                        --pdf_im_resolution, respectively. Format is a
                        dictionary as: '{"path/to/im.jpg": 1000}'
  --keep_bib            Avoid deleting the *.bib files.
  --keep_agent_files    Avoid deleting AI coding agent config/instruction
                        files (e.g. CLAUDE.md, AGENTS.md, GEMINI.md, .cursor/,
                        .github/copilot-instructions.md). By default these are
                        removed so they do not leak into the arXiv source.
  --merge_tex_files     Merge the TeX files into a single file, by recursively
                        replacing the \input and \include commands in the root
                        TeX files with the contents of the files they
                        reference; \include is replaced together with its
                        implicit \clearpage commands. The merged files are not
                        copied to the output folder. Note that \includeonly is
                        not supported.
  --commands_to_delete COMMANDS_TO_DELETE [COMMANDS_TO_DELETE ...]
                        LaTeX commands that will be deleted. Useful for e.g.
                        user-defined \todo commands. For example, to delete
                        all occurrences of \todo1{} and \todo2{}, run the tool
                        with `--commands_to_delete todo1 todo2`.Please note
                        that the positional argument `input_folder` cannot
                        come immediately after `commands_to_delete`, as the
                        parser does not have any way to know if it's another
                        command to delete.
  --commands_only_to_delete COMMANDS_ONLY_TO_DELETE [COMMANDS_ONLY_TO_DELETE ...]
                        LaTeX commands that will be deleted but the text
                        wrapped in the commands will be retained. Useful for
                        commands that change text formats and colors, which
                        you may want to remove but keep the text within.
                        Usages are exactly the same as commands_to_delete.
                        Note that if the commands listed here duplicate that
                        after commands_to_delete, the default action will be
                        retaining the wrapped text.
  --environments_to_delete ENVIRONMENTS_TO_DELETE [ENVIRONMENTS_TO_DELETE ...]
                        LaTeX environments that will be deleted. Useful for
                        e.g. user-defined comment environments. For example,
                        to delete all occurrences of \begin{note} ...
                        \end{note}, run the tool with
                        `--environments_to_delete note`. Please note that the
                        positional argument `input_folder` cannot come
                        immediately after `environments_to_delete`, as the
                        parser does not have any way to know if it's another
                        environment to delete.
  --verbatim_environments VERBATIM_ENVIRONMENTS [VERBATIM_ENVIRONMENTS ...]
                        LaTeX environments whose content is left alone,
                        comments included, on top of verbatim, Verbatim,
                        lstlisting and minted. Useful for environments that
                        show code, where a % is part of the code. Please note
                        that the positional argument `input_folder` cannot
                        come immediately after `verbatim_environments`, as the
                        parser does not have any way to know if it's another
                        environment.
  --if_exceptions IF_EXCEPTIONS [IF_EXCEPTIONS ...]
                        Constant TeX primitive conditionals (\iffalse,
                        \iftrue, etc.) are simplified, i.e., true branches are
                        kept, false branches deleted. To parse the conditional
                        constructs correctly, all commands starting with `\if`
                        are assumed to be TeX primitive conditionals (e.g.,
                        declared by \newif\ifvar). Some known exceptions to
                        this rule are already included (e.g., \iff,
                        \ifthenelse, etc.), but you can add custom exceptions
                        using `--if_exceptions iffalt`.
  --use_external_tikz USE_EXTERNAL_TIKZ
                        Folder (relative to input folder) containing
                        externalized tikz figures in PDF format.
  --svg_inkscape [SVG_INKSCAPE]
                        Include PDF files generated by Inkscape via the
                        `\includesvg` command from the `svg` package. This is
                        done by replacing the `\includesvg` calls with
                        `\includeinkscape` calls pointing to the generated
                        `.pdf_tex` files. By default, these files and the
                        generated PDFs are located under `./svg-inkscape`
                        (relative to the input folder), but a different path
                        (relative to the input folder) can be provided in case
                        a different `inkscapepath` was set when loading the
                        `svg` package.
  --convert_png_to_jpg  Convert PNG images to JPG format to reduce file size.
                        Note that this will override --resize_images for PNG
                        files.
  --png_quality PNG_QUALITY
                        JPG quality for PNG conversion (0-100, default: 50)
  --png_size_threshold PNG_SIZE_THRESHOLD
                        Minimum PNG file size in MB to apply quality reduction
                        (default: 0.5)
  --config CONFIG       Read settings from `.yaml` config file. If command
                        line arguments are provided additionally, the config
                        file parameters are updated with the command line
                        parameters.
  --verbose             Enable detailed output.
```

## Testing

Install the test dependencies and run the full test suite:

```bash
pip install -r requirements.txt absl-py
python -m unittest discover -s arxiv_latex_cleaner/tests -p "*_test.py" -v
```

## Note

This is not an officially supported Google product.
