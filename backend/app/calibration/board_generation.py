from __future__ import annotations

import binascii
import struct

import cv2
import numpy as np

from app.core.exceptions import CalibrationError
from app.models.calibration_models import CalibrationBoardProfile


BOARD_DPI = 300
FIXED_ARUCO_DICTIONARY = "DICT_5X5_100"
FIXED_MARKER_TO_SQUARE_RATIO = 11 / 15
FIXED_PRINT_MARGIN_MM = 10.0
MM_PER_INCH = 25.4
PAPER_DIMENSIONS_MM = {
    "a3": (297.0, 420.0),
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
    "letter": (215.9, 279.4),
}


def paper_dimensions_mm(
    paper_size: str,
    orientation: str,
) -> tuple[float, float]:
    dimensions = PAPER_DIMENSIONS_MM.get(paper_size)
    if dimensions is None:
        raise CalibrationError("不支援指定的校正板紙張尺寸。")
    width, height = dimensions
    if orientation == "landscape":
        return max(width, height), min(width, height)
    return min(width, height), max(width, height)


def fixed_board_values(
    paper_size: str,
    orientation: str,
    squares_x: int,
    squares_y: int,
) -> dict[str, object]:
    page_width_mm, page_height_mm = paper_dimensions_mm(
        paper_size,
        orientation,
    )
    printable_width_mm = page_width_mm - FIXED_PRINT_MARGIN_MM * 2
    printable_height_mm = page_height_mm - FIXED_PRINT_MARGIN_MM * 2
    if printable_width_mm <= 0 or printable_height_mm <= 0:
        raise CalibrationError("校正板紙張尺寸不足以保留列印邊界。")
    square_length_mm = min(
        printable_width_mm / squares_x,
        printable_height_mm / squares_y,
    )
    marker_length_mm = square_length_mm * FIXED_MARKER_TO_SQUARE_RATIO
    paper_label = paper_size.upper() if paper_size != "letter" else "Letter"
    orientation_label = "橫向" if orientation == "landscape" else "直向"
    return {
        "name": f"{paper_label} {orientation_label} OpenCV 校正板",
        "board_type": "charuco",
        "squares_x": squares_x,
        "squares_y": squares_y,
        "square_length_mm": round(square_length_mm, 6),
        "marker_length_mm": round(marker_length_mm, 6),
        "aruco_dictionary": FIXED_ARUCO_DICTIONARY,
        "paper_size": paper_size,
        "paper_orientation": orientation,
        "print_margin_mm": FIXED_PRINT_MARGIN_MM,
    }


def _pixels(mm_value: float) -> int:
    return max(1, round(mm_value / MM_PER_INCH * BOARD_DPI))


def _board_dimensions(
    board: CalibrationBoardProfile,
) -> tuple[int, int, int, int]:
    page_width_mm, page_height_mm = paper_dimensions_mm(
        board.paper_size,
        board.paper_orientation,
    )
    return (
        _pixels(page_width_mm),
        _pixels(page_height_mm),
        _pixels(board.square_length_mm * board.squares_x),
        _pixels(board.square_length_mm * board.squares_y),
    )


def _aruco_dictionary(name: str):
    if not hasattr(cv2, "aruco"):
        raise CalibrationError("目前的 OpenCV 未包含 ArUco 校正板功能。")
    identifier = getattr(cv2.aruco, name, None)
    if identifier is None:
        raise CalibrationError(f"不支援 ArUco 字典 {name}。")
    return cv2.aruco.getPredefinedDictionary(identifier)


def _charuco_image(
    board: CalibrationBoardProfile,
    width: int,
    height: int,
) -> np.ndarray:
    dictionary = _aruco_dictionary(board.aruco_dictionary)
    charuco = cv2.aruco.CharucoBoard(
        (board.squares_x, board.squares_y),
        float(board.square_length_mm),
        float(board.marker_length_mm),
        dictionary,
    )
    return charuco.generateImage(
        (width, height),
        marginSize=0,
        borderBits=1,
    )


def _chessboard_image(
    board: CalibrationBoardProfile,
    width: int,
    height: int,
) -> np.ndarray:
    square_size = width // board.squares_x
    image = np.full(
        (height, width),
        255,
        dtype=np.uint8,
    )
    for row in range(board.squares_y):
        for column in range(board.squares_x):
            if (row + column) % 2 == 0:
                x1 = column * square_size
                y1 = row * square_size
                x2 = (column + 1) * square_size
                y2 = (row + 1) * square_size
                cv2.rectangle(image, (x1, y1), (x2, y2), 0, thickness=-1)
    return image


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    payload = chunk_type + data
    return (
        struct.pack(">I", len(data))
        + payload
        + struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)
    )


def _with_print_resolution(png_bytes: bytes) -> bytes:
    pixels_per_meter = round(BOARD_DPI / 0.0254)
    physical_dimensions = struct.pack(
        ">IIB",
        pixels_per_meter,
        pixels_per_meter,
        1,
    )
    ihdr_end = 33
    return (
        png_bytes[:ihdr_end]
        + _png_chunk(b"pHYs", physical_dimensions)
        + png_bytes[ihdr_end:]
    )


def render_calibration_board(board: CalibrationBoardProfile) -> bytes:
    page_width, page_height, board_width, board_height = _board_dimensions(board)
    if board.board_type == "charuco":
        board_image = _charuco_image(board, board_width, board_height)
    else:
        board_image = _chessboard_image(board, board_width, board_height)

    image = np.full(
        (page_height, page_width),
        255,
        dtype=np.uint8,
    )
    offset_x = (page_width - board_width) // 2
    offset_y = (page_height - board_height) // 2
    image[
        offset_y:offset_y + board_height,
        offset_x:offset_x + board_width,
    ] = board_image

    encoded, buffer = cv2.imencode(".png", image)
    if not encoded:
        raise CalibrationError("OpenCV 無法生成校正板圖片。")
    return _with_print_resolution(buffer.tobytes())
