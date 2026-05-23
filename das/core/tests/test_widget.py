from __future__ import annotations

from unittest.mock import patch

from core.widget import get_icon_select_list


class TestGetIconSelectList:
    def test_filters_out_hashed_copies_and_compressed_variants(self) -> None:
        """Only original SVG filenames (one dot) should be passed to url() and appear in results."""
        all_files = [
            "turtle-nesting_rep.svg",
            "turtle-nesting_rep.cc9eb86883cd.svg",
            "turtle-nesting_rep.svg.gz",
            "turtle-nesting_rep.svg.br",
            "elephant.svg",
            "elephant.abc123def456.svg",
            "elephant.svg.gz",
            "lion.svg",
        ]
        original_svgs = {"turtle-nesting_rep.svg", "elephant.svg", "lion.svg"}

        def fake_url(path: str) -> str:
            filename = path.split("/")[-1]
            assert filename in original_svgs, f"url() called with unexpected filename: {filename}"
            return f"/static/sprite-src/{filename}"

        with (
            patch(
                "core.widget.staticfiles_storage.listdir",
                return_value=([], all_files),
            ),
            patch("core.widget.staticfiles_storage.url", side_effect=fake_url),
        ):
            result = get_icon_select_list()

        assert len(result) == 3
        assert [item["key"] for item in result] == [
            "elephant",
            "lion",
            "turtle-nesting_rep",
        ]

    def test_result_is_sorted_by_key(self) -> None:
        """Results must be in ascending alphabetical order by key."""
        all_files = ["zebra.svg", "antelope.svg", "buffalo.svg"]

        def fake_url(path: str) -> str:
            return f"/static/sprite-src/{path.split('/')[-1]}"

        with (
            patch(
                "core.widget.staticfiles_storage.listdir",
                return_value=([], all_files),
            ),
            patch("core.widget.staticfiles_storage.url", side_effect=fake_url),
        ):
            result = get_icon_select_list()

        assert [item["key"] for item in result] == ["antelope", "buffalo", "zebra"]

    def test_url_receives_correct_path_with_dirname(self) -> None:
        """The path passed to url() must join dirname and filename with os.sep."""
        import os

        captured_paths: list[str] = []

        def fake_url(path: str) -> str:
            captured_paths.append(path)
            return f"/static/{path}"

        with (
            patch(
                "core.widget.staticfiles_storage.listdir",
                return_value=([], ["icon.svg"]),
            ),
            patch("core.widget.staticfiles_storage.url", side_effect=fake_url),
        ):
            get_icon_select_list(dirname="sprite-src")

        assert captured_paths == [os.sep.join(("sprite-src", "icon.svg"))]

    def test_returns_empty_list_when_no_original_svgs_present(self) -> None:
        """Returns an empty list when all files are hashed or compressed variants."""
        all_files = [
            "icon.abc123.svg",
            "icon.svg.gz",
            "icon.svg.br",
        ]

        with (
            patch(
                "core.widget.staticfiles_storage.listdir",
                return_value=([], all_files),
            ),
            patch("core.widget.staticfiles_storage.url") as mock_url,
        ):
            result = get_icon_select_list()

        mock_url.assert_not_called()
        assert result == []
