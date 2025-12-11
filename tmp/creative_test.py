#!/usr/bin/env python3
"""
Creative test demonstration showcasing various tool capabilities.
This script generates ASCII art, processes data, and demonstrates file operations.
"""

import random
import time
from datetime import datetime

def generate_ascii_art(text):
    """Generate simple ASCII art banner."""
    border = "=" * (len(text) + 4)
    return f"\n{border}\n| {text} |\n{border}\n"

def create_mandelbrot_data():
    """Generate a simplified Mandelbrot set representation."""
    data = []
    for i in range(20):
        row = []
        for j in range(60):
            # Simplified calculation for demo purposes
            x = (j - 30) / 20
            y = (i - 10) / 8
            if x*x + y*y < 2:
                row.append("*")
            else:
                row.append(" ")
        data.append("".join(row))
    return "\n".join(data)

def create_log_entry():
    """Create a timestamped log entry."""
    return f"[{datetime.now().isoformat()}] System test completed successfully"

def main():
    """Main demonstration function."""
    print(generate_ascii_art("CREATIVE TOOL TESTING"))
    
    print("\n🎨 ASCII Art Mandelbrot Visualization:")
    mandelbrot = create_mandelbrot_data()
    print(mandelbrot)
    
    print(f"\n📊 Random Data Sample: {random.randint(1000, 9999)}")
    print(f"🕐 Current Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    log_entry = create_log_entry()
    print(f"\n📝 Log Entry: {log_entry}")
    
    return log_entry

if __name__ == "__main__":
    result = main()
    print("\n✅ Creative test completed!")