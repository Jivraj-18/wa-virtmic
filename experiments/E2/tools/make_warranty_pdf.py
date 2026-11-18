#!/usr/bin/env python3
"""Writes the fictional warranty policy PDF of the E2 test context (no PDF library needed)."""
import sys
from pathlib import Path

PAGES = [
    ["Tindleworth Robotics - Kestrel K2 Warranty Policy (fictional test document, experiment E2)", "",
     "1. Scope", "This policy covers Kestrel K2 drones, charging docks and battery packs delivered under any plan.",
     "It does not cover damage from flying outside the limits in the programme specification,",
     "unauthorised firmware, or accidents caused by third parties.", "",
     "2. How to make a claim", "Open a ticket in the maintenance app with the drone serial number and flight logs.",
     "A replacement drone is shipped within five working days in pilot cities.", "",
     "3. Exclusions", "Propellers and parcel boxes are wear parts and are not covered.",
     "Cosmetic scratches are not covered.", "", "(continued on page 2)"],
    ["4. Warranty periods", "",
     "Standard warranty: 18 months from delivery, included in every plan.",
     "Battery packs: 12 months or 400 charge cycles, whichever comes first.", "",
     "5. Extended warranty", "",
     "The extended warranty raises the cover to 36 months from delivery.",
     "Price: 410 US dollars per drone, paid once at order time.",
     "It can only be added when the drone is ordered, not later.", "",
     "6. Contact", "Warranty desk, Tindleworth Robotics (fictional)."],
]


def pdf(pages) -> bytes:
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        body = "BT /F1 11 Tf 14 TL 60 780 Td " + " ".join(f"({esc(l)}) Tj T*" for l in lines) + " ET"
        objs.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {len(objs)} 0 R >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return out


if __name__ == "__main__":
    dst = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "context/knowledge/warranty_policy.pdf")
    dst.write_bytes(pdf(PAGES))
    print(dst)
