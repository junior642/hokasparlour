from PIL import Image

sizes = [72, 96, 128, 144, 152, 192, 384, 512]
source = 'static/favicon/favicon.png'
output_dir = 'static/icons'

import os
os.makedirs(output_dir, exist_ok=True)

img = Image.open(source).convert('RGBA')

for size in sizes:
    resized = img.resize((size, size), Image.LANCZOS)
    resized.save(f'{output_dir}/icon-{size}x{size}.png')
    print(f'✅ Generated icon-{size}x{size}.png')

print('All icons generated!')
