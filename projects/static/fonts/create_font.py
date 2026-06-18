#!/usr/bin/env python3
"""
Create a placeholder Thai font file for PDF export
"""
import os

def create_placeholder_font():
    """Create a placeholder THSarabun font file"""
    # This is a placeholder - in production, replace with actual THSarabunNew.ttf
    font_content = b"PLACEHOLDER_FONT_FILE_REPLACE_WITH_ACTUAL_THSarabunNew"
    
    font_dir = os.path.join(os.path.dirname(__file__), 'THSarabunNew.ttf')
    
    try:
        with open(font_dir, 'wb') as f:
            f.write(font_content)
        print(f"Created placeholder font: {font_dir}")
        return True
    except Exception as e:
        print(f"Error creating font: {e}")
        return False

if __name__ == "__main__":
    create_placeholder_font()
