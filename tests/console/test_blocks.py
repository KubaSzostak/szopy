import sys

from szo.console import blocks


class TestPrintBlock:
    def test_block_starts_at_header_line(self, capsys):
        blocks.print_block(blocks.Block("--x", ["v"]), sys.stdout)
        assert capsys.readouterr().out.startswith("  --x")

    def test_header_fits_first_line_shared(self, capsys):
        blocks.print_block(blocks.Block("--x", ["v", "w"]), sys.stdout, width=4)
        assert capsys.readouterr().out == "  --x   v\n        w\n"

    def test_header_overflow_gets_own_line(self, capsys):
        blocks.print_block(blocks.Block("--very-long", ["v"]), sys.stdout, width=4)
        assert capsys.readouterr().out == "  --very-long\n        v\n"

    def test_file_defaults_to_stdout_at_call_time(self, capsys):
        blocks.print_block(blocks.Block("--x", ["v"]))
        assert "--x" in capsys.readouterr().out

    def test_append_line_skips_empty(self):
        block = blocks.Block("--x")
        block.append_line(None)
        block.append_line("")
        block.append_line("v")
        assert block.lines == ["v"]

    def test_append_error_appends_cause_chain(self):
        block = blocks.Block("--x")
        try:
            try:
                raise ValueError("inner")
            except ValueError as exc:
                raise RuntimeError("outer") from exc
        except RuntimeError as exc:
            block.append_error(exc)
        assert block.lines == ["outer", "inner"]

    def test_append_error_respects_suppressed_context(self):
        block = blocks.Block("--x")
        try:
            try:
                raise ValueError("hidden")
            except ValueError:
                raise RuntimeError("shown") from None
        except RuntimeError as exc:
            block.append_error(exc)
        assert block.lines == ["shown"]


class TestPrintHeader:
    def test_blank_line_then_title(self, capsys):
        blocks.print_header("db", sys.stdout)
        assert capsys.readouterr().out == "\ndb\n"


class TestPrintBlocks:
    def test_column_shrinks_to_widest_header(self, capsys):
        blocks.print_blocks([
            blocks.Block("--x", ["a"]),
            blocks.Block("--wide", ["b"]),
        ], sys.stdout)
        assert capsys.readouterr().out == "  --x     a\n  --wide  b\n"

    def test_overflowing_header_does_not_widen_column(self, capsys):
        blocks.print_blocks([
            blocks.Block("--x", ["a"]),
            blocks.Block("--far-too-long-header", ["b"]),
        ], sys.stdout, max_width=5)
        assert capsys.readouterr().out == (
            "  --x  a\n"
            "  --far-too-long-header\n       b\n"
        )
