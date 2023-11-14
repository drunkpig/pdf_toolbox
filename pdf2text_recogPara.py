import os
import sys
import json

import fitz  # PyMuPDF
import numpy as np

from difflib import SequenceMatcher
from collections import defaultdict


def open_pdf(pdf_path):
    try:
        pdf_document = fitz.open(pdf_path)  # type: ignore
        return pdf_document
    except Exception as e:
        print(f"无法打开PDF文件：{pdf_path}。原因是：{e}")
        raise e


def calculate_avg_values(x0_values, x1_values, char_widths, line_heights):
    """
    This function calculates the average values of the x0, x1, char_width and line_height

    Parameters
    ----------
    x0_values : list
        x0 values of the bbox
    x1_values : list
        x1 values of the bbox
    char_widths : list
        char widths of the bbox
    line_heights : list
        line heights of the bbox

    Returns
    -------
    X0 : float
        median of x0 values
    X1 : float
        median of x1 values
    avg_char_width : float
        average of char widths
    avg_char_height : float
        average of line heights

    """
    X0 = np.median(x0_values) if x0_values else 0
    X1 = np.median(x1_values) if x1_values else 0
    avg_char_width = sum(char_widths) / len(char_widths) if char_widths else 0
    avg_char_height = sum(line_heights) / len(line_heights) if line_heights else 0

    return X0, X1, avg_char_width, avg_char_height


def collect_bbox_values(
    combined_lines, x0_values, x1_values, char_widths, line_heights
):
    """
    This function collects the bbox values of the combined lines

    Parameters
    ----------
    combined_lines : list
        combined lines
    x0_values : list
        x0 values of the bbox
    x1_values : list
        x1 values of the bbox
    char_widths : list
        char widths of the bbox
    line_heights : list
        line heights of the bbox

    Returns
    -------
    x0_values : list
        x0 values of the bbox
    x1_values : list
        x1 values of the bbox
    char_widths : list
        char widths of the bbox
    line_heights : list
        line heights of the bbox
    """
    # for i, line in enumerate(combined_lines[1:-1], 1):  # Skip first and last lines
    for i, line in enumerate(combined_lines):
        bbox = line["bbox"]
        text = line["text"]

        num_chars = len([ch for ch in text if not ch.isspace()])

        x0_values.append(bbox[0])
        x1_values.append(bbox[2])

        if num_chars > 0:
            char_width = (bbox[2] - bbox[0]) / num_chars
            char_widths.append(char_width)

        if len(combined_lines) == 1:
            # 如果这是页面上的第一个块，直接使用块的高度
            if i == 0:
                line_height = bbox[3] - bbox[1]
            else:
                # 使用前一个块的下边界和当前块的上边界来计算行高
                prev_bbox = combined_lines[i - 1]["bbox"]
                line_height = bbox[1] - prev_bbox[1]
            line_heights.append(line_height)
        elif i > 0:  # Calculate row height from the second line onwards
            prev_bbox = combined_lines[i - 1]["bbox"]
            line_height = max(
                (bbox[1] - prev_bbox[1]) / 2, (prev_bbox[3] - bbox[3]) / 2
            )
            line_heights.append(line_height)



def calculate_paragraph_metrics(combined_lines):
    """
    This function calculates the paragraph metrics

    Parameters
    ----------
    combined_lines : list
        combined lines

    Returns
    -------
    X0 : float
        median of x0 values
    X1 : float
        median of x1 values
    avg_char_width : float
        average of char widths
    avg_char_height : float
        average of line heights

    """
    x0_values = []
    x1_values = []
    char_widths = []
    line_heights = []

    if len(combined_lines) > 0:
        collect_bbox_values(
            combined_lines, x0_values, x1_values, char_widths, line_heights
        )

    return calculate_avg_values(x0_values, x1_values, char_widths, line_heights)


def combine_lines(block, y_tolerance):
    """
    This function combines the lines of a block.

    Parameters
    ----------
    block : dict
        block
    y_tolerance : float
        y tolerance

    Returns
    -------
    combined_lines : list
        combined lines

    """
    combined_lines = []  # Used to store merged lines
    current_line = None
    for line in block["lines"]:
        line_bbox = line["bbox"]
        line_text = " ".join([span["text"] for span in line["spans"]])
        if current_line is None:
            current_line = {"bbox": line_bbox, "text": line_text}
        else:
            if (
                abs(line_bbox[1] - current_line["bbox"][1]) <= y_tolerance
                and abs(line_bbox[3] - current_line["bbox"][3]) <= y_tolerance
            ):
                current_line["bbox"] = (
                    min(current_line["bbox"][0], line_bbox[0]),  # left
                    current_line["bbox"][1],  # top
                    max(current_line["bbox"][2], line_bbox[2]),  # right
                    line_bbox[3],  # bottom
                )
                current_line["text"] += " " + line_text
            else:
                combined_lines.append(current_line)
                current_line = {"bbox": line_bbox, "text": line_text}
    if current_line:
        combined_lines.append(current_line)

    return combined_lines


def is_regular_line(
    line_bbox, prev_line_bbox, next_line_bbox, avg_char_height, X0, X1, avg_char_width
):
    vertical_ratio = 1.2
    vertical_thres = vertical_ratio * avg_char_height * 2

    x0, y0, x1, y1 = line_bbox

    regular_x0 = abs(x0 - X0) < avg_char_width
    regular_x1 = abs(x1 - X1) < avg_char_width

    prev_y0, prev_y1 = (
        (prev_line_bbox[1], prev_line_bbox[3]) if prev_line_bbox else (0, 0)
    )
    next_y0, next_y1 = (
        (next_line_bbox[1], next_line_bbox[3]) if next_line_bbox else (0, 0)
    )

    regular_y1 = (
        abs(y0 - prev_y0) < vertical_thres or abs(next_y0 - y0) < vertical_thres
    )
    regular_y0 = (
        abs(y1 - prev_y1) < vertical_thres or abs(next_y1 - y1) < vertical_thres
    )
    regular_y = regular_y0 or regular_y1

    return regular_x0 and regular_x1 and regular_y


def is_possible_start_of_para(
    line_bbox, prev_line_bbox, next_line_bbox, X0, X1, avg_char_width, avg_line_height
):
    horizontal_ratio = 1.5
    vertical_ratio = 0.6
    central_ratio = 2
    title_length_ratio = 0.6
    indent_ratio = 1
    horizontal_thres = horizontal_ratio * avg_char_width
    vertical_thres = vertical_ratio * avg_line_height

    x0, y0, x1, y1 = line_bbox

    indent_condition = x0 > X0 + indent_ratio * avg_char_width
    x0_near_X0 = abs(x0 - X0) < horizontal_thres
    x1_near_X1 = abs(x1 - X1) < horizontal_thres
    line_length = x1 - x0
    title_length_condition = line_length < (X1 - X0) * title_length_ratio

    prev_line_is_end_of_para = prev_line_bbox and (
        abs(prev_line_bbox[2] - X1) > avg_char_width
    )

    if prev_line_bbox:
        vertical_spacing_above = y0 - prev_line_bbox[3]
        sufficient_vertical_spacing_above = vertical_spacing_above > vertical_thres
    else:
        sufficient_vertical_spacing_above = False

    if next_line_bbox:
        vertical_spacing_below = next_line_bbox[1] - y1
        sufficient_vertical_spacing_below = vertical_spacing_below > vertical_thres
        normal_vertical_spacing_below = (
            vertical_spacing_below <= avg_line_height * vertical_ratio
        )

    else:
        sufficient_vertical_spacing_below = False
        normal_vertical_spacing_below = True

    # check if the line is a title
    if sufficient_vertical_spacing_above and (
        normal_vertical_spacing_below or sufficient_vertical_spacing_above
    ):
        center_condition = (
            abs((x0 + x1) / 2 - (X0 + X1) / 2) < avg_char_width * central_ratio
        )
        left_align_condition = x0_near_X0

        if title_length_condition and (center_condition or left_align_condition):
            return True

    if sufficient_vertical_spacing_above and sufficient_vertical_spacing_below:
        return True
    elif sufficient_vertical_spacing_above:
        return True
    elif indent_condition and (x1_near_X1 or not x0_near_X0):
        return True
    elif not indent_condition and x0_near_X0 and x1_near_X1:
        return True
    elif prev_line_is_end_of_para:
        return True
    return False


def is_possible_end_of_para(line_bbox, next_line_bbox, X0, X1, avg_char_width):
    N = 1
    x0, _, x1, y1 = line_bbox
    next_x0, next_y0, _, _ = next_line_bbox if next_line_bbox else (0, 0, 0, 0)

    x0_near_X0 = abs(x0 - X0) < avg_char_width
    x1_smaller_than_X1 = x1 < X1 - N * avg_char_width
    next_line_is_start_of_para = next_line_bbox and (next_x0 > X0 + N * avg_char_width)

    if x0_near_X0 and x1_smaller_than_X1:
        return True
    elif x0_near_X0 and x1_smaller_than_X1 and next_line_is_start_of_para:
        return True
    return False


def is_bbox_overlap(bbox1, bbox2):
    x0_1, y0_1, x1_1, y1_1 = bbox1
    x0_2, y0_2, x1_2, y1_2 = bbox2

    if x0_1 > x1_2 or x0_2 > x1_1:
        return False
    if y0_1 > y1_2 or y0_2 > y1_1:
        return False

    return True


def calculate_para_bbox(lines):
    x0 = min(line["bbox"][0] for line in lines)
    y0 = min(line["bbox"][1] for line in lines)
    x1 = max(line["bbox"][2] for line in lines)
    y1 = max(line["bbox"][3] for line in lines)
    return [x0, y0, x1, y1]


def process_block(
    raw_block,
    y_tolerance,
    image_bboxes,
    table_bboxes,
    equations_inline_bboxes,
    equations_interline_bboxes,
    header_bboxes,
    footer_bboxes,
):
    """
    Processes a raw block from PyMuPDF and returns the processed block.

    Parameters
    ----------
    raw_block : dict
        A raw block from pymupdf.

    Returns
    -------
    processed_block : dict

    structure:

    if is_segmented is True, the structure of processed_block is as follows:
    "block_0": {
        "bbox": block_bbox, # pymupdf切分出来的默认文本块的 bbox
        "text": block_text, # pymupdf切分出来的默认文本块的内容
        "is_overlap": is_overlap, # pymupdf识别出来的block是否和图片、表格、公式的 bbox 重合，若重合则删除
        "is_segmented": is_segmented, # 0: 没有经过process_block中逻辑的处理，block为pymupdf默认识别的结果，1: 经过process_block将block进行了分段，切分成了更多的para
            "paras": {
            "para_0": {
                "bbox": para_bbox,
                "text": para_text,
                "is_matched": is_matched, # 是否匹配是依据切分段落的代码得到的
            },
            "para_1": {
                "bbox": para_bbox,
                "text": para_text,
                "is_matched": is_matched,
            },
            "para_2": {
                "bbox": para_bbox,
                "text": para_text,
                "is_matched": is_matched,
            },
        },
        "bboxes_para": [para_bbox_0, para_bbox_1, para_bbox_2],
    },
    if is_segmented is False, the structure of processed_block is as follows:
    "block_1": {
        "bbox": block_bbox,
        "text": block_text,
        "is_segmented": is_segmented,
        "is_overlap": is_overlap,
        "paras": {},
        "bboxes_para": [],
    },"""

    # Extract the bounding box and text from the raw block
    bbox = raw_block["bbox"]
    text = " ".join(
        span["text"] for line in raw_block["lines"] for span in line["spans"]
    )

    font_type = raw_block["lines"][0]["spans"][0][
        "font"
    ]  # may be None if the block is an image or table or equation
    font_size = raw_block["lines"][0]["spans"][0][
        "size"
    ]  # may be None if the block is an image or table or equation

    # Check for overlap with images, tables, equations, headers, and footers
    is_overlap = any(
        is_bbox_overlap(bbox, other_bbox)
        for other_bbox in image_bboxes
        + table_bboxes
        + equations_inline_bboxes
        + equations_interline_bboxes
        + header_bboxes
        + footer_bboxes
    )

    for eq_bbox in equations_inline_bboxes + equations_interline_bboxes:
        if is_bbox_overlap(bbox, eq_bbox):
            # Replace text with placeholder if overlap found
            text = (
                "$equations_inline_bboxes$"
                if eq_bbox in equations_inline_bboxes
                else "$equations_interline_bboxes$"
            )
            break

    # If there's an overlap, return the processed block early
    if is_overlap:
        return {
            "bbox": bbox,
            "text": text,
            "is_segmented": 0,
            "is_overlap": True,
            "paras": {},
            "bboxes_para": [],
        }

    # Combine lines and calculate metrics for paragraph segmentation
    combined_lines = combine_lines(raw_block, y_tolerance)

    # print("combined_lines: ", combined_lines)

    X0, X1, avg_char_width, avg_char_height = calculate_paragraph_metrics(
        combined_lines
    )

    # Segment into paragraphs
    paragraphs = []
    start_of_para = None
    in_paragraph = False

    for line_index, line in enumerate(combined_lines):
        line_bbox = line["bbox"]
        prev_line_bbox = (
            combined_lines[line_index - 1]["bbox"] if line_index > 0 else None
        )
        next_line_bbox = (
            combined_lines[line_index + 1]["bbox"]
            if line_index < len(combined_lines) - 1
            else None
        )

        if not in_paragraph and is_possible_start_of_para(
            line_bbox,
            prev_line_bbox,
            next_line_bbox,
            X0,
            X1,
            avg_char_width,
            avg_char_height,
        ):
            in_paragraph = True
            start_of_para = line_index
        elif in_paragraph and is_possible_end_of_para(
            line_bbox, next_line_bbox, X0, X1, avg_char_width
        ):
            paragraphs.append((start_of_para, line_index))
            start_of_para = None
            in_paragraph = False

    # Add the last paragraph if needed
    if in_paragraph and start_of_para is not None:
        paragraphs.append((start_of_para, len(combined_lines) - 1))

    # Create the processed paragraphs
    processed_paras = {}
    bboxes_para = []
    processed_text = []  # Store text of processed paragraphs for comparison
    last_end_idx = 0  # Track the end index of the last paragraph

    for para_index, (start_idx, end_idx) in enumerate(paragraphs):
        # If there is unmatched text before this paragraph, add it as a separate paragraph
        if start_idx > last_end_idx:
            unmatched_text = " ".join(
                line["text"] for line in combined_lines[last_end_idx:start_idx]
            )
            unmatched_bbox = calculate_para_bbox(combined_lines[last_end_idx:start_idx])
            unmatched_key = f"para_{len(processed_paras)}"
            processed_paras[unmatched_key] = {
                "bbox": unmatched_bbox,
                "text": unmatched_text,
                "is_matched": 0,
            }
            bboxes_para.append(unmatched_bbox)

        # Process the matched paragraph
        para_bbox = calculate_para_bbox(combined_lines[start_idx : end_idx + 1])
        para_text = " ".join(
            line["text"] for line in combined_lines[start_idx : end_idx + 1]
        )
        para_key = f"para_{len(processed_paras)}"
        processed_paras[para_key] = {
            "bbox": para_bbox,
            "text": para_text,
            "is_matched": 1,
        }
        bboxes_para.append(para_bbox)
        last_end_idx = end_idx + 1

    # Add any remaining unmatched text after the last paragraph
    if last_end_idx < len(combined_lines):
        unmatched_text = " ".join(
            line["text"] for line in combined_lines[last_end_idx:]
        )
        unmatched_bbox = calculate_para_bbox(combined_lines[last_end_idx:])
        unmatched_key = f"para_{len(processed_paras)}"
        processed_paras[unmatched_key] = {
            "bbox": unmatched_bbox,
            "text": unmatched_text,
            "is_matched": 0,
        }
        bboxes_para.append(unmatched_bbox)

    # Construct the final processed block
    processed_block = {
        "bbox": bbox,
        "text": text,
        "X0": X0,
        "X1": X1,
        "avg_char_width": avg_char_width,
        "avg_char_height": avg_char_height,
        "font_type": font_type,
        "font_size": font_size,
        "is_segmented": 1 if processed_paras else 0,
        "is_overlap": is_overlap,
        "paras": processed_paras,
        "bboxes_para": bboxes_para,
    }

    return processed_block


def parse_blocks_per_page(
    page,
    page_id,
    image_bboxes,
    table_bboxes,
    equations_inline_bboxes,
    equations_interline_bboxes,
    header_bboxes,
    footer_bboxes,
):
    """
    Parses the blocks per page.

    Parameters
    ----------
    page : fitz.Page
        Page from PyMuPDF.
    page_id : int
        Page ID.
    image_bboxes : list
        Image bounding boxes.
    table_bboxes : list
        Table bounding boxes.
    equations_inline_bboxes : list
        Inline equation bounding boxes.
    equations_interline_bboxes : list
        Interline equation bounding boxes.
    header_bboxes : list
        Header bounding boxes.
    footer_bboxes : list
        Footer bounding boxes.



    Returns
    -------
    result_dict : dict
        Result dictionary.

    structure:
        "page_0": {
            "block_0": {
                "bbox": block_bbox, # pymupdf 切分出来的文本块的 bbox
                "text": block_text, # pymupdf 切分出来的文本块的内容
                "is_segmented": is_segmented, # 0: Pymupdf 默认识别的文字段落，1: 经过自编写段落识别的文字段落
                "is_overlap": is_overlap, # 是否被图片或者表格、公式的 bbox 覆盖
                "paras": {
                    "para_0": {
                        "bbox": para_bbox,
                        "text": para_text,
                        "is_matched": is_matched, # 是否匹配是依据切分段落的代码得到的
                    },
                    "para_1": {
                        "bbox": para_bbox,
                        "text": para_text,
                        "is_matched": is_matched,
                    },
                    "para_2": {
                        "bbox": para_bbox,
                        "text": para_text,
                        "is_matched": is_matched,
                    },
                },
                "bboxes_para": [para_bbox_0, para_bbox_1, para_bbox_2],
            },
            "block_1": {
                "bbox": block_bbox,
                "text": block_text,
                "is_segmented": is_segmented,
                "is_overlap": is_overlap,
                "paras": {},
                "bboxes_para": [],
            },
        }
    }
    """
    page_key = f"page_{page_id}"
    result_dict = {"page_id": page_id, page_key: {}}

    raw_blocks = page.get_text("dict")["blocks"]
    para_num = 0

    for raw_block in raw_blocks:
        if raw_block["type"] == 0:  # Only process text blocks
            # Process each block using the process_block function
            processed_block = process_block(
                raw_block,
                y_tolerance=2.0,
                image_bboxes=image_bboxes,
                table_bboxes=table_bboxes,
                equations_inline_bboxes=equations_inline_bboxes,
                equations_interline_bboxes=equations_interline_bboxes,
                header_bboxes=header_bboxes,
                footer_bboxes=footer_bboxes,
            )

            block_key = f"block_{para_num}"
            para_num += 1

            # Add the processed block to the result dictionary
            result_dict[page_key][block_key] = {
                "bbox": processed_block["bbox"],
                "text": processed_block["text"],
                "X0": processed_block["X0"],
                "X1": processed_block["X1"],
                "avg_char_width": processed_block["avg_char_width"],
                "avg_char_height": processed_block["avg_char_height"],
                "font_type": processed_block.get("font_type", ""),
                "font_size": processed_block.get("font_size", ""),
                "is_segmented": processed_block["is_segmented"],
                "is_overlap": processed_block["is_overlap"],
                "paras": {},
                "bboxes_para": processed_block["bboxes_para"],
            }

            # Add processed paragraphs to the block
            for para_key, para_info in processed_block["paras"].items():
                result_dict[page_key][block_key]["paras"][para_key] = {
                    "bbox": para_info["bbox"],
                    "text": para_info["text"],
                    "is_matched": para_info["is_matched"],
                }

    return result_dict


def get_min_bbox_by_area(bboxes):
    """
    This function gets the min bbox from the bboxes, minimum bbox is defined as the truely existed bbox with the minimum area

    Parameters
    ----------
    bboxes : list
        bboxes

    Returns
    -------
    min_bbox : list
        min bbox

    """
    min_bbox = None
    min_area = float("inf")

    for bbox in bboxes:
        x0, y0, x1, y1 = bbox
        area = (x1 - x0) * (y1 - y0)
        if area < min_area:
            min_area = area
            min_bbox = bbox

    return min_bbox


def get_min_bbox_by_coor(bboxes):
    """
    This function gets the min bbox from the bboxes, minimum bbox is defined as the bbox with the minimum x0, minimum y0, maximum x1, maximum y1

    Parameters
    ----------
    bboxes : list
        bboxes

    Returns
    -------
    min_bbox : list
        min bbox

    """
    min_bbox = None
    min_x0 = float("inf")
    min_y0 = float("inf")
    max_x1 = -float("inf")
    max_y1 = -float("inf")

    for bbox in bboxes:
        x0, y0, x1, y1 = bbox
        if x0 < min_x0:
            min_x0 = x0
        if y0 < min_y0:
            min_y0 = y0
        if x1 > max_x1:
            max_x1 = x1
        if y1 > max_y1:
            max_y1 = y1

    min_bbox = [min_x0, min_y0, max_x1, max_y1]

    return min_bbox


def compare_text_similarity(text1, text2):
    """
    This function compares the text1 and text2, use distance to measure the similarity

    Parameters
    ----------
    text1 : str
        text1
    text2 : str
        text2

    Returns
    -------
    similarity : float
        similarity between text1 and text2, keep 2 decimal places.
    """

    similarity = round(SequenceMatcher(None, text1, text2).ratio(), 2)

    return similarity


def compare_bbox(bbox1, bbox2, tolerance=1):
    """
    This function compares the bbox1 and bbox2

    Parameters
    ----------
    bbox1 : list
        bbox1
    bbox2 : list
        bbox2
    tolerance : int, optional

    Returns
    -------
    is_same : bool
        True if bbox1 and bbox2 are the same, else False

    """
    return all(abs(a - b) < tolerance for a, b in zip(bbox1, bbox2))


def get_most_common_bboxes(
    bboxes, page_height, position="top", threshold=0.25, num_bboxes=3, min_frequency=2
):
    # 根据位置筛选bbox
    if position == "top":
        filtered_bboxes = [bbox for bbox in bboxes if bbox[1] < page_height * threshold]
    else:
        filtered_bboxes = [
            bbox for bbox in bboxes if bbox[3] > page_height * (1 - threshold)
        ]

    # 找到最常见的bbox
    bbox_count = defaultdict(int)
    for bbox in filtered_bboxes:
        bbox_count[tuple(bbox)] += 1

    # 获取频率最高的几个bbox，但只有当出现次数超过min_frequency时才考虑
    common_bboxes = [
        bbox
        for bbox, count in sorted(
            bbox_count.items(), key=lambda item: item[1], reverse=True
        )
        if count >= min_frequency
    ][:num_bboxes]
    return common_bboxes


def detect_footer_header(result_dict):
    def compare_bbox_with_list(bbox, bbox_list, tolerance=1):
        return any(
            all(abs(a - b) < tolerance for a, b in zip(bbox, common_bbox))
            for common_bbox in bbox_list
        )

    def is_single_line_block(block):
        # 根据块的宽度和高度判断
        block_width = block["X1"] - block["X0"]
        block_height = block["bbox"][3] - block["bbox"][1]

        # 如果块的高度接近平均字符高度，且宽度较大，则认为是单行
        return block_height <= block["avg_char_height"] * 1.5 and block_width > block["avg_char_width"] * 10

    # 遍历文档中的所有块
    single_line_blocks = 0
    total_blocks = 0
    for page_id, blocks in result_dict.items():
        if page_id.startswith("page_"):
            for block_key, block in blocks.items():
                if block_key.startswith("block_"):
                    total_blocks += 1
                    if is_single_line_block(block):
                        single_line_blocks += 1

    # 如果大多数块是单行的，则跳过页眉页脚检测
    if single_line_blocks / total_blocks > 0.5:  # 阈值可以调整
        print("Skipping header/footer detection for text-dense document.")
        return result_dict

    # Collect the bounding boxes of all blocks
    all_bboxes = []
    for page_id, blocks in result_dict.items():
        if page_id.startswith("page_"):
            for block_key, block in blocks.items():
                if block_key.startswith("block_"):
                    all_bboxes.append(block["bbox"])

    # Get the height of the page
    page_height = max(bbox[3] for bbox in all_bboxes)

    # Get the most common bbox lists for headers and footers
    common_header_bboxes = get_most_common_bboxes(
        all_bboxes, page_height, position="top"
    )
    common_footer_bboxes = get_most_common_bboxes(
        all_bboxes, page_height, position="bottom"
    )

    # bboxes in common_header_bboxes or common_footer_bboxes should occur at least in 80% of the pages

    # print("common_header_bboxes: ", common_header_bboxes)
    # print("common_footer_bboxes: ", common_footer_bboxes)

    # Detect and mark headers and footers
    for page_id, blocks in result_dict.items():
        if page_id.startswith("page_"):
            for block_key, block in blocks.items():
                if block_key.startswith("block_"):
                    bbox = block["bbox"]
                    text = block["text"]

                    is_header = compare_bbox_with_list(bbox, common_header_bboxes)
                    is_footer = compare_bbox_with_list(bbox, common_footer_bboxes)

                    block["is_header"] = int(is_header)
                    block["is_footer"] = int(is_footer)

                    # if is_header:
                    #     print("header_bbox: ", bbox)
                    #     print("header_text: ", text)

                    # if is_footer:
                    #     print("footer_bbox: ", bbox)
                    #     print("footer_text: ", text)

    return result_dict


def draw_block_border(page, block_color, block):
    if block["type"] == 0:  # Dealing with text blocks only
        block_bbox = block["bbox"]
        block_rect = fitz.Rect(block_bbox)
        block_annot = page.add_rect_annot(block_rect)
        block_annot.set_colors(stroke=block_color)
        block_annot.set_border(width=2)
        block_annot.update()


def draw_paragraph_border(page, para_color, start_of_para, end_of_para, combined_lines):
    all_lines_bbox = [
        combined_lines[i]["bbox"] for i in range(start_of_para, end_of_para + 1)
    ]

    min_x = min(bbox[0] for bbox in all_lines_bbox)
    max_x = max(bbox[2] for bbox in all_lines_bbox)
    min_y = min(bbox[1] for bbox in all_lines_bbox)
    max_y = max(bbox[3] for bbox in all_lines_bbox)

    para_rect = fitz.Rect(min_x, min_y, max_x, max_y)
    para_annot = page.add_rect_annot(para_rect)
    para_annot.set_colors(stroke=para_color)
    para_annot.set_border(width=2)
    para_annot.update()


def draw_blocks_lines_spans(pdf_path, output_pdf_path):
    """
    绘制文本块、行、字的边框.

    Parameters
    ----------
    pdf_path : str
        pdf文件路径
    output_pdf_path : str
        输出pdf文件路径


    Returns
    -------
    None.
    """
    block_color = (1, 0, 1)
    para_color = (0, 1, 1)

    y_tolerance = 2.0  # Allow 2 units of deviation in the y-coordinate

    pdf_document = open_pdf(pdf_path)
    if not pdf_document:
        print("无法继续处理因为无法打开PDF文件。")
        return

    for page_number in range(len(pdf_document)):
        page = pdf_document[page_number]
        text_dict = page.get_text("dict")
        blocks = text_dict["blocks"]

        for block in blocks:
            draw_block_border(page, block_color, block)
            combined_lines = combine_lines(block, y_tolerance)
            X0, X1, avg_char_width, avg_char_height = calculate_paragraph_metrics(
                combined_lines
            )

            start_of_para = None
            in_paragraph = False
            paragraphs = (
                []
            )  # Used to store indexes of starting and ending line of paragraphs

            for line_index, line in enumerate(combined_lines):
                line_bbox = line["bbox"]

                prev_line_bbox = (
                    combined_lines[line_index - 1]["bbox"] if line_index > 0 else None
                )
                next_line_bbox = (
                    combined_lines[line_index + 1]["bbox"]
                    if line_index < len(combined_lines) - 1
                    else None
                )

                if not in_paragraph and is_possible_start_of_para(
                    line_bbox,
                    prev_line_bbox,
                    next_line_bbox,
                    X0,
                    X1,
                    avg_char_width,
                    avg_char_height,
                ):
                    in_paragraph = True
                    start_of_para = line_index

                elif in_paragraph and is_possible_end_of_para(
                    line_bbox, next_line_bbox, X0, X1, avg_char_width
                ):
                    end_of_para = line_index
                    if start_of_para is not None:
                        draw_paragraph_border(
                            page, para_color, start_of_para, end_of_para, combined_lines
                        )
                        paragraphs.append((start_of_para, end_of_para))
                        start_of_para = None  # Reset paragraph start markers
                        in_paragraph = False  # Reset paragraph status

    pdf_document.save(output_pdf_path)
    pdf_document.close()


def get_test_data(file_path, not_print_data=True):
    """
    This function gets the test data from json file
    """
    import json

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # read value from data by keys: pageID_imageBboxs、pageID_tableBboxs、pageID_equationBboxs
    pageID_imageBboxs = []
    pageID_tableBboxs = []
    pageID_equationBboxs = []

    pageID_imageBboxs = data["pageID_imageBboxs"]
    pageID_tableBboxs = data["pageID_tableBboxs"]
    pageID_equationBboxs = data["pageID_equationBboxs"]

    if not not_print_data:
        for pageID, (imageBboxs, tableBboxs, equationBboxs) in enumerate(
            zip(pageID_imageBboxs, pageID_tableBboxs, pageID_equationBboxs)
        ):
            print(f"pageID: {pageID}")
            print(f"imageBboxs: {imageBboxs}")
            print(f"tableBboxs: {tableBboxs}")
            print(f"equationBboxs: {equationBboxs}")
            print()

    return pageID_imageBboxs, pageID_tableBboxs, pageID_equationBboxs


from pdf2text_recogFigure_20231107 import parse_images  # Get the figures bboxes
from pdf2text_recogTable_20231107 import parse_tables  # Get the tables bboxes
from pdf2text_recogEquation_20231108 import parse_equations  # Get the equations bboxes


# Run this script to test the function:
#   command:

#       python pdf2text_recogPara.py [pdf_path] [output_pdf_path]
#
# pdf_path: the path of the pdf file
# output_pdf_path: the path of the output pdf file

if __name__ == "__main__":
    DEFAULT_PDF_PATH = (
        "test/assets/paper/paper.pdf"
        if os.name != "nt"
        else "test\\assets\\paper\\paper.pdf"
    )
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF_PATH
    output_pdf_path = (
        sys.argv[2] if len(sys.argv) > 2 else pdf_path.split(".")[0] + "_recogPara.pdf"
    )

    import stat

    # Remove existing output file if it exists
    if os.path.exists(output_pdf_path):
        os.chmod(output_pdf_path, stat.S_IWRITE)
        os.remove(output_pdf_path)

    pdf_doc = open_pdf(pdf_path)

    test_json_file = (
        "test/assets/paper/images_tables_equations.json"
        if os.name != "nt"
        else "test\\assets\\paper\\images_tables_equations.json"
    )

    (
        pageID_imageBboxs,
        pageID_tableBboxs,
        pageID_interline_equationBboxs,
    ) = get_test_data(test_json_file, not_print_data=True)

    if not pdf_path == DEFAULT_PDF_PATH:
        pageID_imageBboxs = []
        pageID_tableBboxs = []
        pageID_interline_equationBboxs = []

    pageID_inline_equationBboxs = []

    # parse paragraph and save to json file
    pdf_dic = {}

    for page_id, page in enumerate(pdf_doc):
        image_bboxes = (
            pageID_imageBboxs[page_id] if page_id < len(pageID_imageBboxs) else []
        )
        table_bboxes = (
            pageID_tableBboxs[page_id] if page_id < len(pageID_tableBboxs) else []
        )
        interline_equation_bboxes = (
            pageID_interline_equationBboxs[page_id]
            if page_id < len(pageID_interline_equationBboxs)
            else []
        )

        result_dict = parse_blocks_per_page(
            page,
            page_id,
            image_bboxes,
            table_bboxes,
            pageID_inline_equationBboxs,  # Assuming this is a global list valid for all pages
            interline_equation_bboxes,
            [],  # Assuming empty lists for headers and footers for now
            [],
        )

        pdf_dic[f"page_{page_id}"] = result_dict[f"page_{page_id}"]

    # handle the header and footer
    detect_footer_header(pdf_dic)

    output_json_file = (
        "test/assets/paper/pdf_dic.json"
        if os.name != "nt"
        else "test\\assets\\paper\\pdf_dic.json"
    )

    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(pdf_dic, f, ensure_ascii=False, indent=4)

    for page_id, page in enumerate(pdf_doc):
        page_key = f"page_{page_id}"

        for block_key, block in pdf_dic[page_key].items():
            if block_key.startswith("block_"):
                is_block_segmented = block["is_segmented"]
                is_block_overlap = block["is_overlap"]
                is_block_header = block.get("is_header", 0)
                is_block_footer = block.get("is_footer", 0)

                """
                Color code:
                    Red: (1, 0, 0)
                    Green: (0, 1, 0)
                    Blue: (0, 0, 1)
                    Yellow: (1, 1, 0) - mix of red and green
                    Cyan: (0, 1, 1) - mix of green and blue
                    Magenta: (1, 0, 1) - mix of red and blue
                    White: (1, 1, 1) - red, green and blue full intensity
                    Black: (0, 0, 0) - no color component whatsoever
                    Gray: (0.5, 0.5, 0.5) - equal and medium intensity of red, green and blue color components
                    Orange: (1, 0.65, 0) - maximum intensity of red, medium intensity of green, no blue component
                """

                # 如果块是页眉或页脚，使用橙色标注
                if is_block_header or is_block_footer:
                    rect_color = (1, 0.65, 0)  # 橙色
                    rect_width = 2  # 页眉和页脚的边框宽度
                    block_rect = fitz.Rect(block["bbox"])
                    block_annot = page.add_rect_annot(block_rect)
                    block_annot.set_colors(stroke=rect_color)
                    block_annot.set_border(width=rect_width)
                    block_annot.update()
                elif not is_block_segmented:
                    # 绘制整个块的矩形
                    rect_color = (0, 1, 1) if is_block_overlap else (0, 0, 1)  # 蓝色或青色
                    rect_width = 2 if is_block_overlap else 1
                    block_rect = fitz.Rect(block["bbox"])
                    block_annot = page.add_rect_annot(block_rect)
                    block_annot.set_colors(stroke=rect_color)
                    block_annot.set_border(width=rect_width)
                    block_annot.update()
                else:
                    # 绘制每个段落的矩形
                    for para_key, para in block["paras"].items():
                        para_rect = fitz.Rect(para["bbox"])
                        para_annot = page.add_rect_annot(para_rect)
                        stroke_color = (
                            (0, 1, 0) if para["is_matched"] == 1 else (1, 0, 0)
                        )  # 绿色或红色
                        para_annot.set_colors(stroke=stroke_color)
                        para_annot.set_border(width=0.5)
                        para_annot.update()

    pdf_doc.save(output_pdf_path)
    pdf_doc.close()
