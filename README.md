# `arxiv_latex_cleaner`

This tool allows you to easily clean the LaTeX code of your paper to submit to
arXiv. From a folder containing all your code, e.g. `/path/to/latex/`, it
creates a new folder `/path/to/latex_arXiv/`, that is ready to ZIP and upload to
arXiv.

## Example call:

```bash
arxiv_latex_cleaner /path/to/latex --resize_images --im_size 500 --images_whitelist='{"images/im.png":2000}'
```

Or simply from a config file

```bash
arxiv_latex_cleaner /path/to/latex --config cleaner_config.yaml
```

## Installation:

```bash
pip install arxiv-latex-cleaner
```

| :exclamation: arxiv_latex_cleaner is only compatible with Python >=3 :exclamation: |
| ---------------------------------------------------------------------------------- |

Alternatively, you can download the source code:

```bash
git clone https://github.com/google-research/arxiv-latex-cleaner
cd arxiv-latex-cleaner/
python -m arxiv_latex_cleaner --help
```

And install as a command-line program directly from the source code:

```bash
python setup.py install
```

## Main features:

#### Privacy-oriented

*   Removes all auxiliary files (`.aux`, `.log`, `.out`, etc.).
*   Removes all comments from your code (yes, those are visible on arXiv and you
    do not want them to be). These also include `\begin{comment}\end{comment}`,
    `\iffalse\fi`, and `\if0\fi` environments.
*   Optionally removes user-defined commands entered with `commands_to_delete`
    (such as `\todo{}` that you redefine as the empty string at the end).
*   Optionally allows you to define custom regex replacement rules through a
    `cleaner_config.yaml` file.

#### Size-oriented

There is a 50MB limit on arXiv submissions, so to make it fit:

*   Removes all unused `.tex` files (those that are not in the root and not
    included in any other `.tex` file).
*   Removes all unused images that take up space (those that are not actually
    included in any used `.tex` file).
*   Optionally resizes all images to `im_size` pixels, to reduce the size of the
    submission. You can whitelist some images to skip the global size using
    `images_whitelist`.
*   Optionally compresses `.pdf` files using ghostscript (Linux and Mac only).
    You can whitelist some PDFs to skip the global size using
    `images_whitelist`.

#### TikZ picture source code concealment

To prevent the upload of tikzpicture source code or raw simulation data, this
feature:

*   Replaces the tikzpicture environment `\begin{tikzpicture} ...
    \end{tikzpicture}` with the respective
    `\includegraphics{EXTERNAL_TIKZ_FOLDER/picture_name.pdf}`.
*   Requires externally compiled TikZ pictures as `.pdf` files in folder
    `EXTERNAL_TIKZ_FOLDER`. See section 53 in the
    [PGF/TikZ manual](https://ctan.org/pkg/pgf?lang=en) on TikZ picture
    externalization.
*   Only replaces environments with preceding
    `\tikzsetnextfilename{picture_name}` command (as in
    `\tikzsetnextfilename{picture_name}\begin{tikzpicture} ...
    \end{tikzpicture}`) where the externalized `picture_name.pdf` filename
    matches `picture_name`.

#### More sophisticated pattern replacement based on regex group captures

Sometimes it is useful to work with a set of custom LaTeX commands when writing
a paper. To get rid of them upon arXiv submission, one can simply revert them to
plain LaTeX with a regular expression insertion.

```yaml
{
    "pattern" : '(?:\\figcomp{\s*)(?P<first>.*?)\s*}\s*{\s*(?P<second>.*?)\s*}\s*{\s*(?P<third>.*?)\s*}',
    "insertion" : '\parbox[c]{{ {second} \linewidth}} {{ \includegraphics[width= {third} \linewidth]{{figures/{first} }} }}',
    "description" : "Replace figcomp"
}
```

The pattern above will find all `\figcomp{path}{w1}{w2}` commands and replace
them with
`\parbox[c]{w1\linewidth}{\includegraphics[width=w2\linewidth]{figures/path}}`.
Note that the insertion template is filled with the
[named groups captures](https://docs.python.org/3/library/re.html#regular-expression-examples)
from the pattern. Note that the replacement is processed **before** all
`\includegraphics` commands are processed and corresponding file paths are
copied, making sure all figure files are copied to the cleaned version. See also
[cleaner_config.yaml](cleaner_config.yaml) for details on how to specify the
patterns.

## Usage:

```
usage: arxiv_latex_cleaner@v0.1.30 [-h] [--resize_images] [--im_size IM_SIZE]
                                   [--compress_pdf]
                                   [--pdf_im_resolution PDF_IM_RESOLUTION]
                                   [--images_whitelist IMAGES_WHITELIST]
                                   [--keep_bib]
                                   [--commands_to_delete COMMANDS_TO_DELETE [COMMANDS_TO_DELETE ...]]
                                   [--use_external_tikz USE_EXTERNAL_TIKZ]
                                   [--config CONFIG] [--verbose]
                                   input_folder

Clean the LaTeX code of your paper to submit to arXiv. Check the README for
more information on the use.

positional arguments:
  input_folder          Input folder containing the LaTeX code.

optional arguments:
  -h, --help            show this help message and exit
  --resize_images       Resize images.
  --im_size IM_SIZE     Size of the output images (in pixels, longest side).
                        Fine tune this to get as close to 10MB as possible.
  --compress_pdf        Compress PDF images using ghostscript (Linux and Mac
                        only).
  --pdf_im_resolution PDF_IM_RESOLUTION
                        Resolution (in dpi) to which the tool resamples the
                        PDF images.
  --images_whitelist IMAGES_WHITELIST
                        Images (and PDFs) that won't be resized to the default
                        resolution,but the one provided here. Value is pixel
                        for images, and dpi forPDFs, as in --im_size and
                        --pdf_im_resolution, respectively. Format is a
                        dictionary as: '{"path/to/im.jpg": 1000}'
  --keep_bib            Avoid deleting the *.bib files.
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
                        you may want to remove but keep the text within. Usages
                        are exactly the same as commands_to_delete. Note that if
                        the commands listed here duplicate that after
                        commands_to_delete, the default action will be retaining
                        the wrapped text.
  --use_external_tikz USE_EXTERNAL_TIKZ
                        Folder (relative to input folder) containing
                        externalized tikz figures in PDF format.
  --config CONFIG       Read settings from `.yaml` config file. If command
                        line arguments are provided additionally, the config
                        file parameters are updated with the command line
                        parameters.
  --verbose             Enable detailed output.
```

## Testing:

```bash
python -m unittest arxiv_latex_cleaner.tests.arxiv_latex_cleaner_test
```

## Note

This is not an officially supported Google product.
