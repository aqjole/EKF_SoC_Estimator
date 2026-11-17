"""Writing the markdown reports: a file written with the same bytes on every platform, and markdown tables."""


def write_text(path, text):
    """Write `text` to `path`, creating the folder; newline="\\n" so the bytes are the same on every platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, newline="\n")


def md_row(cells):
    """Return one markdown table row from a list of text cells."""
    return "| " + " | ".join(cells) + " |"


def md_table(header, rows):
    """Return the lines of a markdown table: `header` is a list of column titles and `rows` a list of lists of text."""
    return [md_row(header), "|" + "---|" * len(header)] + [md_row(row) for row in rows]
