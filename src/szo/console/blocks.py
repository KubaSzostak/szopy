"""Card-shaped terminal output: a header column plus hanging-indent detail lines."""

import sys

from typing import TextIO
from dataclasses import dataclass, field


@dataclass
class Block:
    header: str
    lines: list[str] = field(default_factory=list)

    def append_line(self, line: str | None) -> None:
        if line:
            self.lines.append(line)

    def append_error(self, error: BaseException) -> None:
        """Append the error's message and every message in its cause chain."""
        current: BaseException | None = error
        while current is not None:
            self.append_line(str(current))
            # Mirror Python's chaining rules: explicit ``from`` wins, bare
            # context is shown unless suppressed by ``raise ... from None``.
            if current.__cause__ is not None:
                current = current.__cause__
            elif current.__suppress_context__:
                current = None
            else:
                current = current.__context__


def print_block(block: Block, file: TextIO | None = None, width: int = 25) -> None:
    """Print one block; a header wider than ``width`` gets its own line."""
    file = sys.stdout if file is None else file
    # One dumb rule: every block is preceded by a blank line.
    print(file=file)
    if len(block.header) > width or not block.lines:
        # The header does not fit the column: own line, everything hangs.
        print(f"  {block.header}", file=file)
        hanging_lines = block.lines
    else:
        print(f"  {block.header:<{width}}  {block.lines[0]}", file=file)
        hanging_lines = block.lines[1:]
    for line in hanging_lines:
        print(f"  {'':<{width}}  {line}", file=file)


def print_header(title: str, file: TextIO | None = None) -> None:
    """Print a section header above a run of blocks: a blank line, then ``title:``."""
    file = sys.stdout if file is None else file
    print(file=file)
    print(f"{title}:", file=file)


def print_blocks(blocks: list[Block], file: TextIO | None = None, max_width: int = 25) -> None:
    """Print blocks with a shared header column sized to the widest fitting header."""
    width = _get_header_width(blocks, max_width)
    for block in blocks:
        print_block(block, file, width)


def _get_header_width(blocks: list[Block], max_width: int) -> int:
    # Headers over max_width go on their own line, so they don't widen the column.
    widths = [len(block.header) for block in blocks if len(block.header) <= max_width]
    return max(widths, default=max_width)
