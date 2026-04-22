import os
import base64
import mimetypes
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt


def is_local_image_file(file_path: str | Path) -> bool:    
    path = Path(file_path)

    try:
        if not path.is_file():
            return False
    except Exception:
        return False
    
    mime_type, _ = mimetypes.guess_type(path)
    return mime_type is not None and mime_type.startswith("image/")


def is_online_image(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    _, ext = os.path.splitext(parsed.path)

    return ext.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
        ".tiff",
        ".svg",
        ".ico",
    }


def encode_resized_image(
    image_path: str | Path,
    max_dim: int = 1024,
    format: str = "PNG",
    jpeg_quality: int = 90,
) -> str:
    """
    Resize an image so its longest side is `max_dim`, then encode it as Base64.

    Args:
        image_path: Path to the image file.
        max_dim: Maximum size of the longest image dimension.
        format: Output image format ("PNG", "JPEG", "WEBP").
        jpeg_quality: JPEG quality (only used if format == "JPEG").

    Returns:
        Base64-encoded image string (no data URL prefix).
    """
    path = Path(image_path)

    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")

    with Image.open(path) as img:
        # Ensure consistent color mode
        if format.upper() in {"JPEG", "JPG"} and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Resize while preserving aspect ratio
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        buffer = BytesIO()

        save_kwargs = {}
        if format.upper() in {"JPEG", "JPG"}:
            save_kwargs.update({
                "quality": jpeg_quality,
                "optimize": True,
                "subsampling": 0,
            })

        img.save(buffer, format=format.upper(), **save_kwargs)
        buffer.seek(0)

        mime_type, _ = mimetypes.guess_type(path)
        encoded = base64.b64encode(buffer.read()).decode("utf-8")
    
    return f"data:{mime_type};base64,{encoded}"


def encode_image(image_path: str | Path) -> str:
    path = Path(image_path)

    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")

    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type or not mime_type.startswith("image/"):
        raise ValueError(f"Unsupported image type: {path.suffix}")

    with path.open("rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{encoded}"


def resize_and_pad(img, size, pad_color=(255, 255, 255)):
    img.thumbnail(size, Image.LANCZOS)
    new_img = Image.new("RGB", size, pad_color)
    offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
    new_img.paste(img, offset)
    return new_img

def matplotlib_image_grid(img_paths, grid_size, img_size=(400, 400), 
                          font_size=14, line_color='black', save_path=None):
    rows, cols = grid_size
    assert len(img_paths) <= rows * cols, "Not enough space in grid for all images"

    fig_width = cols * (img_size[0]/100)
    fig_height = rows * (img_size[1]/100)

    fig, axes = plt.subplots(rows, cols, figsize=(fig_width, fig_height))

    # Normalize axes for different grid sizes
    if rows == 1 and cols == 1:
        axes = [[axes]]
    elif rows == 1 or cols == 1:
        axes = axes.reshape(rows, cols)

    for idx, (ax, img_path) in enumerate(zip(axes.flatten(), img_paths)):
        img = Image.open(img_path).convert('RGB')
        img = resize_and_pad(img, img_size)
        ax.imshow(img)
        ax.axis('off')

        # Add numbering
        ax.text(0.05, 0.95, str(idx + 1), fontsize=font_size, color='yellow',
                ha='left', va='top', transform=ax.transAxes,
                bbox=dict(facecolor='black', alpha=0.5, pad=3))

    # Fill remaining grid cells with blank images
    for i in range(len(img_paths), len(axes.flatten())):
        ax = axes.flatten()[i]
        ax.imshow(np.ones((img_size[1], img_size[0], 3), dtype=np.uint8) * 255)  # White placeholder
        ax.axis('off')

    plt.subplots_adjust(wspace=0.02, hspace=0.02)

    # Grid lines
    for r in range(1, rows):
        fig.add_artist(plt.Line2D([0, 1], [r/rows, r/rows], color=line_color, 
                                  linewidth=2, transform=fig.transFigure))
    for c in range(1, cols):
        fig.add_artist(plt.Line2D([c/cols, c/cols], [0, 1], color=line_color, 
                                  linewidth=2, transform=fig.transFigure))

    if save_path:
        plt.tight_layout()
        plt.savefig(save_path, bbox_inches='tight', dpi=300)
        plt.close()
    else:
        plt.tight_layout()
        plt.show()