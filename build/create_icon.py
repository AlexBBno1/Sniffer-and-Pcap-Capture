"""
Icon Generator for WiFi Sniffer Control Panel
==============================================
Generates the application icon in ICO format.

Run this script to create assets/icon.ico
"""

import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("[ERROR] Pillow is required. Install with: pip install pillow")
    exit(1)


def create_wifi_icon(size=256):
    """Create a WiFi signal icon"""
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Colors - gradient-like effect
    colors = [
        (34, 197, 94, 255),    # Green (innermost)
        (59, 130, 246, 255),   # Blue
        (168, 85, 247, 255),   # Purple (outermost)
    ]
    
    # Center point (bottom center of the icon)
    center_x = size // 2
    center_y = int(size * 0.85)
    
    # Draw signal arcs from outside to inside
    arc_widths = [size // 12, size // 14, size // 16]
    radii = [int(size * 0.65), int(size * 0.45), int(size * 0.25)]
    
    for i, (radius, color, width) in enumerate(zip(radii, colors, arc_widths)):
        bbox = [
            center_x - radius, center_y - radius,
            center_x + radius, center_y + radius
        ]
        draw.arc(bbox, 200, 340, fill=color, width=width)
    
    # Draw center dot with gradient effect
    dot_radius = size // 10
    # Outer glow
    for r in range(dot_radius + 4, dot_radius - 1, -1):
        alpha = int(255 * (1 - (r - dot_radius) / 5)) if r > dot_radius else 255
        glow_color = (34, 197, 94, alpha)
        draw.ellipse([
            center_x - r, center_y - r,
            center_x + r, center_y + r
        ], fill=glow_color)
    
    return image


def create_all_icon_sizes():
    """Create icons at all standard Windows sizes"""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []
    
    for size in sizes:
        img = create_wifi_icon(size)
        images.append(img)
    
    return images


def main():
    """Generate the icon file"""
    # Ensure assets directory exists
    assets_dir = Path(__file__).parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    
    output_path = assets_dir / "icon.ico"
    
    print("=" * 50)
    print("  WiFi Sniffer Icon Generator")
    print("=" * 50)
    print(f"  Output: {output_path}")
    print("=" * 50)
    
    # Generate icons at multiple sizes
    print("[INFO] Generating icon at multiple sizes...")
    images = create_all_icon_sizes()
    
    # Save as ICO with all sizes
    print("[INFO] Saving as ICO file...")
    
    # The first image is used as the base, others are appended
    base_image = images[-1]  # Use largest (256px) as base
    
    # Save with all sizes embedded
    base_image.save(
        output_path,
        format='ICO',
        sizes=[(img.width, img.height) for img in images]
    )
    
    print(f"[SUCCESS] Icon created: {output_path}")
    print(f"[INFO] Sizes included: {[img.width for img in images]}")
    
    # Also save a PNG version for other uses
    png_path = assets_dir / "icon.png"
    images[-1].save(png_path, format='PNG')
    print(f"[SUCCESS] PNG version: {png_path}")


if __name__ == '__main__':
    main()


