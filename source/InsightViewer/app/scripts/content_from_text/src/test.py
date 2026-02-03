import re

marked_heading_line = re.compile(r"^\s*<<\s*(.+?)\s*>>\s*$")
lines = [
    "<<4.1 (18.–8. stol. pr. Kr.)>>",
    "<<4.2 Egejski svet bronaste dobe>>",
    "<<4.2.1 Minojska kultura>>",
]

for line in lines:
    match = marked_heading_line.match(line)
    if match:
        print(f"Matched: {line}")
    else:
        print(f"No match: {line}")
