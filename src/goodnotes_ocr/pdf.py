from __future__ import annotations

import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

from goodnotes_ocr.errors import DependencyError, PageOutOfRangeError


def download_pdf(url: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
            )
        },
    )
    with urllib.request.urlopen(request) as response:
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            raise DependencyError(f"URL did not return a PDF: {content_type}")
        output_path.write_bytes(response.read())
    return output_path


def page_count(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError:
        return _page_count_with_pdfinfo(pdf_path)

    return len(PdfReader(str(pdf_path)).pages)


def render_page(pdf_path: Path, page: int, output_path: Path, dpi: int = 300) -> Path:
    count = page_count(pdf_path)
    if page < 1 or page > count:
        raise PageOutOfRangeError(f"Page {page} is outside document range 1-{count}.")
    if shutil.which("pdftoppm") is None:
        raise DependencyError(
            "Poppler's pdftoppm is required to render PDF pages. "
            "Install it with `brew install poppler` locally or add "
            "`poppler-utils` to the Docker image."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = output_path.with_suffix("")
    proc = subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page),
            "-l",
            str(page),
            "-r",
            str(dpi),
            "-png",
            str(pdf_path),
            str(prefix),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise DependencyError(proc.stderr.strip() or "pdftoppm failed.")

    generated = prefix.with_name(f"{prefix.name}-{page}.png")
    if not generated.exists():
        single_page_name = prefix.with_name(f"{prefix.name}-1.png")
        if single_page_name.exists():
            generated = single_page_name
        else:
            raise DependencyError("pdftoppm did not create the expected PNG.")

    if generated != output_path:
        generated.replace(output_path)
    return output_path


def _page_count_with_pdfinfo(pdf_path: Path) -> int:
    if shutil.which("pdfinfo") is None:
        raise DependencyError(
            "Install pypdf or Poppler's pdfinfo to read PDF page counts."
        )
    proc = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise DependencyError(proc.stderr.strip() or "pdfinfo failed.")
    match = re.search(r"^Pages:\s+(\d+)$", proc.stdout, re.MULTILINE)
    if not match:
        raise DependencyError("Could not read page count from pdfinfo output.")
    return int(match.group(1))
