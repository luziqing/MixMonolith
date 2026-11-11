import re

# Read current base file
with open('c:/Users/lzq/codearts/Android/MixMonolithBuild/assets/index.html', 'r', encoding='utf-8') as f:
    base = f.read()

# Let's inspect where styles and scripts are
print("Base length:", len(base))
