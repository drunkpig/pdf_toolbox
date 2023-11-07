import sys
from typing import Tuple

import click
from libs.commons import parse_aws_param, parse_bucket_key, read_pdf
import boto3, json
from botocore.config import Config
import fitz
from loguru import logger

from pdf2text_recongFigure_20231106 import parse_images    #从当前page获取figures的bboxes

def parse_tables(page: fitz.Page, exclude_bboxes: list[Tuple] = None) -> (list[Tuple], list):
    pass


# def parse_images(page: fitz.Page, exclude_bboxes: list[Tuple] = None) -> (list[Tuple], list):
#     pass


def parse_paragraph(page: fitz.Page, exclude_bboxes: list[Tuple] = None) -> (list[Tuple], list):
    pass


def parse_equations(page: fitz.Page, exclude_bboxes: list[Tuple] = None) -> (list[Tuple], list):
    """
    解析公式 TODO
    :param page:
    :param exclude_bboxes:
    :return:
    """
    return [], []


def link2markdown(all_content: list):
    """
    拼接成markdown
    :param all_content:
    :return:
    """
    pass

def cut_image(bbox: Tuple, book_id:str,   page_num: int, page: fitz.Page, save_path: str, s3_profile: str):
    """
    从第page_num页的page中，根据bbox进行裁剪出一张jpg图片，返回图片路径
    save_path：需要同时支持s3和本地, 图片的命名为  {save_path}/{book_id}_{page_num}_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}.jpg, bbox内数字取整。
    """
    pass


@click.command()
@click.option('--s3-pdf-path', help='s3上pdf文件的路径')
@click.option('--s3-profile', help='s3上的profile')
def main(s3_pdf_path: str, s3_profile: str):
    """

    """
    
    exclude_bboxes = []  # 上一阶段产生的bbox，加入到这个里。例如图片产生的bbox,在下一阶段进行表格识别的时候就不能和这些bbox重叠。
    try:
        pdf_bytes = read_pdf(s3_pdf_path, s3_profile)
        pdf_docs = fitz.open("pdf", pdf_bytes)
        for pageID, page in enumerate(pdf_docs):
            # 先解析table
            table_bboxes, table_contents = parse_tables(page)
            exclude_bboxes.append(table_bboxes)

            # 解析图片
            image_bboxes, image_contents = parse_images(page_ID, page, res_dir_path, json_from_DocXchain_dir, exclude_bboxes)
            exclude_bboxes.append(image_bboxes)

            # 解析公式
            equations_bboxes, equation_contents = parse_equations(page, exclude_bboxes)
            exclude_bboxes.append(equations_bboxes)

            # 解析文字段落
            text_bboxes, text_content = parse_paragraph(page, exclude_bboxes)

            # 最后一步，根据bbox进行从左到右，从上到下的排序，之后拼接起来
            # 排序 TODO

            # 拼接内容 TODO

    except Exception as e:
        print(f"ERROR: {s3_pdf_path}, {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
