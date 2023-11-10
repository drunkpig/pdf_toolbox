import os
import sys
import json

import fitz  # PyMuPDF
import numpy as np

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
    for i, line in enumerate(combined_lines[1:-1], 1):  # 跳过首行和末行
        bbox = line["bbox"]
        text = line["text"]

        num_chars = len([ch for ch in text if not ch.isspace()])

        x0_values.append(bbox[0])
        x1_values.append(bbox[2])

        if num_chars > 0:
            char_width = (bbox[2] - bbox[0]) / num_chars
            char_widths.append(char_width)

        if i > 1:  # 从第二行开始计算行高
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

    if len(combined_lines) > 2:
        collect_bbox_values(
            combined_lines, x0_values, x1_values, char_widths, line_heights
        )

    return calculate_avg_values(x0_values, x1_values, char_widths, line_heights)


def combine_lines(block, y_tolerance):
    """
    This function combines the lines of the block
    
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
    combined_lines = []  # 用于存储合并后的lines
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


def is_possible_start_of_para(line_bbox, prev_line_bbox, X0, X1, avg_char_width):
    horizontal_ratio = 1.2
    N = 1
    horizontal_thres = horizontal_ratio * avg_char_width

    x0, _, x1, _ = line_bbox

    indent_condition = x0 > X0 + N * avg_char_width
    x1_near_X1 = abs(x1 - X1) < horizontal_thres
    prev_line_is_end_of_para = prev_line_bbox and (
        abs(prev_line_bbox[2] - X1) > avg_char_width
    )

    if indent_condition and x1_near_X1:
        return True
    elif not indent_condition and x1_near_X1 and prev_line_is_end_of_para:
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


def draw_block_border(page, block_color, block):
    if block["type"] == 0:  # 只处理文本块
        block_bbox = block["bbox"]
        block_rect = fitz.Rect(block_bbox)
        block_annot = page.add_rect_annot(block_rect)
        block_annot.set_colors(stroke=block_color)
        block_annot.set_border(width=2)  # 增加block边框宽度
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
    para_annot.set_border(width=2)  # 青色粗线
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
    block_color = (1, 0, 1)  # 粉色
    para_color = (0, 1, 1)  # 青色

    y_tolerance = 2.0  # 允许y坐标有2个单位的偏差

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
            paragraphs = []  # 用于存储段落的起始和结束行索引

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
                    line_bbox, prev_line_bbox, X0, X1, avg_char_width
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
                        start_of_para = None  # 重置段落开始标记
                        in_paragraph = False  # 重置段落状态

    pdf_document.save(output_pdf_path)
    pdf_document.close()


def is_bbox_overlap(bbox1, bbox2):
    x0_1, y0_1, x1_1, y1_1 = bbox1
    x0_2, y0_2, x1_2, y1_2 = bbox2

    if x0_1 > x1_2 or x0_2 > x1_1:
        return False
    if y0_1 > y1_2 or y0_2 > y1_1:
        return False

    return True


def parse_paragraph(
    page,
    page_id,
    image_bboxes,
    table_bboxes,
    equations_inline_bboxes,
    equations_interline_bboxes,
):
    """
    解析文字段落

    Parameters
    ----------
    page : fitz.Page
        一个页面
    image_bboxes : list
        图片的 bbox
    table_bboxes : list
        表格的 bbox
    equations_inline_bboxes : list
        行内公式的 bbox
    equations_interline_bboxes : list
        行间公式的 bbox

    Returns
    -------
    text_bboxes : list
        文字段落的 bbox
    text_content : list
        文字段落的内容
    """

    page_key = f"page_{page_id}"
    result_dict = {page_key: {}}

    blocks = page.get_text("dict")["blocks"]

    para_num = 0
    page_bboxes_para = []
    for block in blocks:
        if block["type"] == 0:  # 只处理文本块
            bbox = block["bbox"]
            text = " ".join(
                span["text"] for line in block["lines"] for span in line["spans"]
            )


            is_overlap = False
            
            # 检查是否被图片或者表格的 bbox 覆盖
            if any(
                is_bbox_overlap(bbox, img_bbox)
                for img_bbox in image_bboxes + table_bboxes
            ):
                is_overlap = True
                continue

            flag = 0 # 0: Pymupdf 默认识别的文字段落，1: 经过自编写段落识别的文字段落

            if len(equations_inline_bboxes) > 0:
                # 替换公式的 bbox
                for eq_inline_bbox in equations_inline_bboxes:
                    if is_bbox_overlap(bbox, eq_inline_bbox):
                        text = "$equation_inline$"
                        is_overlap = True

            for eq_btw_bbox in equations_interline_bboxes:
                if is_bbox_overlap(bbox, eq_btw_bbox):
                    text = "$equation_interline$"
                    is_overlap = True

            para_key = f"para_{para_num}"
            para_num += 1
            result_dict[page_key][para_key] = {"bbox": bbox, "text": text, "flag": flag, "is_overlap": is_overlap}
            page_bboxes_para.append(bbox)

    result_dict[page_key]["bboxes_para"] = page_bboxes_para

    return result_dict


def get_test_data(file_path, not_print_data=True):
    """
    从文件中获取测试数据
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


from pdf2text_recogFigure_20231107 import parse_images  # 获取figures的bbox
from pdf2text_recogTable_20231107 import parse_tables  # 获取tables的bbox
from pdf2text_recogEquation_20231108 import parse_equations  # 获取equations的bbox


if __name__ == "__main__":
    
    if os.name == "nt":
        DEFAULT_PDF_PATH = "test\\assets\\paper\\paper.pdf"
    else:
        DEFAULT_PDF_PATH = "test/assets/paper/paper.pdf"
    
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = DEFAULT_PDF_PATH
    
    try:
        output_pdf_path = sys.argv[2]
    except IndexError:
        output_pdf_path = None
        
    if output_pdf_path is None:
        output_pdf_path = pdf_path.split(".")[0] + "_recogPara.pdf"

    if os.path.exists(output_pdf_path):
        import stat
        os.chmod(output_pdf_path, stat.S_IWRITE)
        os.remove(output_pdf_path)

    pdf_doc = open_pdf(pdf_path)

    if os.name == "nt":
        test_json_file = "test\\assets\\paper\\images_tables_equations.json"
    else:
        test_json_file = "test/assets/paper/images_tables_equations.json"

    (
        pageID_imageBboxs,
        pageID_tableBboxs,
        pageID_interline_equationBboxs,
    ) = get_test_data(test_json_file, not_print_data=True)
    pageID_inline_equationBboxs = []

    pdf_dic = {}

    for page_id, page in enumerate(pdf_doc):
        result_dict = parse_paragraph(
            page,
            page_id,
            pageID_imageBboxs[page_id],
            pageID_tableBboxs[page_id],
            pageID_inline_equationBboxs,
            pageID_interline_equationBboxs[page_id],
        )

        page_key = f"page_{page_id}"
        pdf_dic[page_key] = result_dict[page_key]

    if os.name == "nt":
        output_json_file = "test\\assets\\paper\\pdf_dic.json"
    else:
        output_json_file = "test/assets/paper/pdf_dic.json"

    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(pdf_dic, f, ensure_ascii=False, indent=4)

    for page_id, page in enumerate(pdf_doc):
        page_key = f"page_{page_id}"
        page_bboxes_para = pdf_dic[page_key]["bboxes_para"]
        for para_id, para in enumerate(page_bboxes_para):
            para_key = f"para_{para_id}"
            para_bbox = pdf_dic[page_key][para_key]["bbox"]
            para_text = pdf_dic[page_key][para_key]["text"]
            para_flag = pdf_dic[page_key][para_key]["flag"]
            is_overlap = pdf_dic[page_key][para_key]["is_overlap"]

            if is_overlap: # 被图片或者表格、公式的 bbox 覆盖， 红色
                para_rect = fitz.Rect(para_bbox)
                print(para_text)
                para_annot = page.add_rect_annot(para_rect)
                para_annot.set_colors(stroke=(1, 0, 0)) # 红色
                para_annot.set_border(width=2)

                para_annot.update()

            if para_flag == 1: # 经过段落识别的文字段落，绿色
                para_rect = fitz.Rect(para_bbox)
                para_annot = page.add_rect_annot(para_rect)
                para_annot.set_colors(stroke=(0, 1, 0)) # 绿色
                para_annot.set_border(width=0.5)

                para_annot.update()
            else: # Pymupdf 默认识别的文字段落，蓝色
                para_rect = fitz.Rect(para_bbox)
                para_annot = page.add_rect_annot(para_rect)
                para_annot.set_colors(stroke=(0, 0, 1))
                para_annot.set_border(width=1)

                para_annot.update()

    pdf_doc.save(output_pdf_path)
    pdf_doc.close()
