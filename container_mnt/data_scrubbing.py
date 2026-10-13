#!/usr/bin/env python3
from PIL import Image # type: ignore
import os


# def scrub_static_crop(input_folder, output_folder, crop_height=65):
#     os.makedirs(output_folder, exist_ok=True)
    
#     for filename in os.listdir(input_folder):
#         if filename.lower().endswith(".tif"):
#             img_path = os.path.join(input_folder, filename)
#             img = Image.open(img_path)
#             width, height = img.size
            
#             # Crop top part
#             cropped_img = img.crop((0, crop_height, width, height))
#             output_path = os.path.join(output_folder, filename)
#             cropped_img.save(output_path)

#     print("Scrubbing complete.")

def scrub_static_crop(input_folder, output_folder, crop_height=68, output_format="tif"):
    count = 0
    for root, _, files in os.walk(input_folder):
        for filename in files:
            if filename.lower().endswith((".tif", ".tiff", ".png")):
                input_path = os.path.join(root, filename)

                # Construct the corresponding output path
                relative_path = os.path.relpath(root, input_folder)
                output_dir = os.path.join(output_folder, relative_path)
                os.makedirs(output_dir, exist_ok=True)

                # save all in the requested format (.tif or .png)
                output_path = os.path.join(output_dir, os.path.splitext(filename)[0] + "." + output_format)

                print(f"Processing: {input_path} -> {output_path}")
                
                img = Image.open(input_path)
                width, height = img.size
                cropped_img = img.crop((0, crop_height, width, height))
                # PNG does not support some TIFF modes (e.g. CMYK, float)
                if output_format == "png" and cropped_img.mode not in ("1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"):
                    cropped_img = cropped_img.convert("RGB")
                cropped_img.save(output_path)
                count += 1

    if count == 0:
        print(f"No .tif, .tiff or .png images found in {input_folder}")
        return 1
    print(f"Scrubbing complete ({count} images).")
    return 0

def visualize_scrubbing(input_folder, output_folder, filename, crop_height=68):
    input_path = os.path.join(input_folder, filename)
    output_path = os.path.join(output_folder, filename)

    # Open images
    original = Image.open(input_path)
    if not os.path.exists(output_path):
        print(f"Scrubbed image not found: {output_path}")
        return
    scrubbed = Image.open(output_path)

    # Plot side by side
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    axes[0].imshow(original)
    axes[0].set_title("Original")
    axes[0].axis("on")
    axes[1].imshow(scrubbed)
    axes[1].set_title("Scrubbed")
    axes[1].axis("on")
    plt.show()

if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Crop a fixed band at the top of .tif, .tiff or .png images (saved as .tif or .png) to remove burned-in identifying data.")
    parser.add_argument("input_folder", help="Input directory (searched recursively)")
    parser.add_argument("output_folder", help="Output directory")
    parser.add_argument("--crop-height", type=int, default=68, help="Number of pixel rows removed at the top (default: 68)")
    parser.add_argument("--output-format", choices=["tif", "png"], default="tif", help="Format of the output images (default: tif)")
    args = parser.parse_args()
    sys.exit(scrub_static_crop(args.input_folder, args.output_folder, crop_height=args.crop_height, output_format=args.output_format))
