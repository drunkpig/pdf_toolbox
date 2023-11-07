import sys
from typing import Tuple
import os
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
    return []


def link2markdown(all_content: list):
    """
    拼接成markdown
    :param all_content:
    :return:
    """
    pass

def cut_image(bbox: Tuple, page_num: int, page: fitz.Page, save_parent_path: str, s3_profile: str):
    """
    从第page_num页的page中，根据bbox进行裁剪出一张jpg图片，返回图片路径
    save_path：需要同时支持s3和本地, 图片存放在save_path下，文件名是: {page_num}_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}.jpg
    """
    image_save_path = os.path.join(save_parent_path, f"{page_num}_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}.jpg")
    # TODO
    
    return image_save_path

def get_images_by_bboxes(book_name:str, page_num:int, page: fitz.Page, save_path:str, s3_profile:str, image_bboxes:list, table_bboxes:list, equation_bboxes:list) -> dict:
    """
    返回一个dict, key为bbox, 值是图片地址
    """
    ret = {}
    
    # 图片的保存路径组成是这样的： {s3_or_local_path}/{book_name}/{images|tables|equations}/{page_num}_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}.jpg
    image_save_path = os.path.join(save_path, book_name, "images") 
    table_save_path = os.path.join(save_path, book_name, "tables") 
    equation_save_path = os.path.join(save_path, book_name, "equations")
    
    for bbox in image_bboxes:
        image_path = cut_image(bbox, page_num, page, image_save_path, s3_profile)
        ret[bbox] = image_path
        
    for bbox in table_bboxes:
        image_path = cut_image(bbox, page_num, page, table_save_path, s3_profile)
        ret[bbox] = image_path
        
    for bbox in equation_bboxes:
        image_path = cut_image(bbox, page_num, page, equation_save_path, s3_profile)
        ret[bbox] = image_path
        
    return ret
        
        
        

@click.command()
@click.option('--s3-pdf-path', help='s3上pdf文件的路径')
@click.option('--s3-profile', help='s3上的profile')
@click.option('--save-path', help='解析出来的图片，文本的保存父目录')
def main(s3_pdf_path: str, s3_profile: str, save_path: str):
    """

    """
    book_name = os.path.basename(s3_pdf_path).split(".")[0]
    exclude_bboxes = []  # 上一阶段产生的bbox，加入到这个里。例如图片产生的bbox,在下一阶段进行表格识别的时候就不能和这些bbox重叠。
    
    try:
        pdf_bytes = read_pdf(s3_pdf_path, s3_profile)
        pdf_docs = fitz.open("pdf", pdf_bytes)
        for pageID, page in enumerate(pdf_docs):

            # 解析图片
            image_bboxes, table_bboxes = parse_images(page_ID, page, res_dir_path, json_from_DocXchain_dir, exclude_bboxes)
            exclude_bboxes.append(image_bboxes)
            exclude_bboxes.append(table_bboxes)

            # 解析公式
            equations_bboxes = parse_equations(page, exclude_bboxes)
            exclude_bboxes.append(equations_bboxes)
            
            # 把图、表、公式都进行截图，保存到本地，返回图片路径作为内容
            images_box_path_dict = get_images_by_bboxes(book_name, pageID, page, save_path, s3_profile, image_bboxes, table_bboxes, equations_bboxes)
            
            # 解析文字段落
            text_bboxes, text_content = parse_paragraph(page, exclude_bboxes)

            # 最后一步，根据bbox进行从左到右，从上到下的排序，之后拼接起来
            # 排序 TODO

            # 拼接内容 TODO

    except Exception as e:
        print(f"ERROR: {s3_pdf_path}, {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
