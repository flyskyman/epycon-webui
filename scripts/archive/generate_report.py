
import os
import sys
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# Fix import
sys.path.append(os.getcwd())
from epycon.iou.parsers import _readentries

LOG_FILE = r'c:\backup\LOG_DHR51337676_0000067d\entries.log'
OUTPUT_PDF = r'c:\Projects\epycon\parsed_entries_report.pdf'

def generate_pdf():
    # 1. Parse Entries
    try:
        entries = _readentries(LOG_FILE)
    except Exception as e:
        print(f"Error parsing log: {e}")
        return

    # Sort by timestamp to match original PDF behavior
    entries.sort(key=lambda x: x.timestamp)

    # 2. Setup PDF Canvas
    c = canvas.Canvas(OUTPUT_PDF, pagesize=A4)
    width, height = A4
    margin = 50
    line_height = 14
    y = height - margin
    
    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, "Parsed Epycon Log Report")
    y -= 25
    
    c.setFont("Helvetica", 10)
    c.drawString(margin, y, f"Source: {LOG_FILE}")
    y -= 15
    c.drawString(margin, y, f"Total Records: {len(entries)}")
    y -= 25

    # Header
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Time")
    c.drawString(margin + 120, y, "Description (Message)")
    
    # Draw line
    y -= 5
    c.line(margin, y, width - margin, y)
    y -= 15

    c.setFont("Helvetica", 9)

    # 3. Draw Content
    page_num = 1
    for i, e in enumerate(entries):
        if y < margin:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = height - margin
            page_num += 1
        
        # Format Time
        dt_str = datetime.fromtimestamp(e.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        c.drawString(margin, y, dt_str)
        c.drawString(margin + 120, y, e.message or "")
        
        y -= line_height

    c.save()
    print(f"PDF Report generated: {OUTPUT_PDF}")

if __name__ == '__main__':
    generate_pdf()
