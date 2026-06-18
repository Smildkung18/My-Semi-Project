#!/usr/bin/env python3
"""
Download Thai font for PDF export support
Run this script to download Noto Sans Thai font
"""
import os
import urllib.request
import sys

def download_font():
    """Download Noto Sans Thai font from Google Fonts"""
    font_url = "https://github.com/notofonts/notofonts.github.io/raw/main/NotoSansThai-Regular.ttf"
    font_dir = os.path.join(os.path.dirname(__file__), 'NotoSansThai-Regular.ttf')
    
    try:
        print(f"Downloading Thai font from {font_url}")
        urllib.request.urlretrieve(font_url, font_dir)
        print(f"Font downloaded successfully to {font_dir}")
        return True
    except Exception as e:
        print(f"Error downloading font: {e}")
        return False

if __name__ == "__main__":
    success = download_font()
    sys.exit(0 if success else 1)
