"""Checks for the CV evaluation helpers. Written with SI assistance (Claude Code)."""

from pipeline.cv.evaluate import DSWX_RAW, dswx_files


def test_dswx_files_accept_both_slash_styles():
    # Indexes written on Windows before the fix use backslashes; new ones use forward slashes.
    windows = dswx_files({"files": ["albufera\\058_A_021\\20260618\\x_B01_WTR.tif"]})
    posix = dswx_files({"files": ["albufera/058_A_021/20260618/x_B01_WTR.tif"]})
    assert windows == posix == [DSWX_RAW / "albufera" / "058_A_021" / "20260618" / "x_B01_WTR.tif"]
    assert dswx_files({"files": None}) == [] and dswx_files({}) == []
