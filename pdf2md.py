import sys
from typing import Tuple
import os
import click
from libs.commons import parse_aws_param, parse_bucket_key, read_pdf
import boto3, json
from botocore.config import Config
import fitz
from loguru import logger
from pathlib import Path

from pdf2text_recogFigure_20231107 import parse_images        # 获取figures的bbox
from pdf2text_recogTable_20231107 import parse_tables         # 获取tables的bbox
from pdf2text_recogEquation_20231108 import parse_equations    # 获取equations的bbox
from pdf2text_recogPara import parse_blocks_per_page    
from bbox_sort import bbox_sort, CONTENT_IDX, CONTENT_TYPE_IDX


def cut_image(bbox: Tuple, page_num: int, page: fitz.Page, save_parent_path: str, s3_profile: str):
    """
    从第page_num页的page中，根据bbox进行裁剪出一张jpg图片，返回图片路径
    save_path：需要同时支持s3和本地, 图片存放在save_path下，文件名是: {page_num}_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}.jpg , bbox内数字取整。
    """
    # 拼接路径
    image_save_path = os.path.join(save_parent_path, f"{page_num}_{int(bbox[0])}_{int(bbox[1])}_{int(bbox[2])}_{int(bbox[3])}.jpg")
    try:
        # 将坐标转换为fitz.Rect对象
        rect = fitz.Rect(*bbox)
        # 配置缩放倍数为3倍
        zoom = fitz.Matrix(3, 3)
        # 截取图片
        pix = page.get_pixmap(clip=rect, matrix=zoom)
        
        # 打印图片文件名
        # print(f"Saved {image_save_path}")
        if image_save_path.startswith("s3://"):
            ak, sk, end_point, addressing_style = parse_aws_param(s3_profile)
            cli = boto3.client(service_name="s3", aws_access_key_id=ak, aws_secret_access_key=sk, endpoint_url=end_point,
                            config=Config(s3={'addressing_style': addressing_style}))
            bucket_name, bucket_key = parse_bucket_key(image_save_path)
            # 将字节流上传到s3
            cli.upload_fileobj(pix.tobytes(output='jpeg', jpg_quality=95), bucket_name, bucket_key)
        else:
            # 保存图片到本地
            # 先检查一下image_save_path的父目录是否存在，如果不存在，就创建
            parent_dir = os.path.dirname(image_save_path)
            if not os.path.exists(parent_dir):
                os.makedirs(parent_dir)
            pix.save(image_save_path, jpg_quality=95)
            # 为了直接能在markdown里看，这里把地址改为相对于mardown的地址
            pth = Path(image_save_path)
            image_save_path =  f"{pth.parent.name}/{pth.name}"
            return image_save_path
    except Exception as e:
        logger.exception(e)
        return image_save_path

    

def get_images_by_bboxes(book_name:str, page_num:int, page: fitz.Page, save_path:str, s3_profile:str, image_bboxes:list, table_bboxes:list, equation_inline_bboxes:list, equation_interline_bboxes:list) -> dict:
    """
    返回一个dict, key为bbox, 值是图片地址
    """
    ret = {}
    
    # 图片的保存路径组成是这样的： {s3_or_local_path}/{book_name}/{images|tables|equations}/{page_num}_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}.jpg
    image_save_path = os.path.join(save_path, book_name, "images") 
    table_save_path = os.path.join(save_path, book_name, "tables") 
    equation_inline_save_path = os.path.join(save_path, book_name, "equations_inline")
    equation_interline_save_path = os.path.join(save_path, book_name, "equation_interline")
    
    for bbox in image_bboxes:
        image_path = cut_image(bbox, page_num, page, image_save_path, s3_profile)
        ret[bbox] = (image_path, "image") # 第二个元素是"image"，表示是图片
        
    for bbox in table_bboxes:
        image_path = cut_image(bbox, page_num, page, table_save_path, s3_profile)
        ret[bbox] = (image_path, "table")
        
    # 对公式目前只截图，不返回
    for bbox in equation_inline_bboxes:
        cut_image(bbox, page_num, page, equation_inline_save_path, s3_profile)
        
    for bbox in equation_interline_bboxes:
        cut_image(bbox, page_num, page, equation_interline_save_path, s3_profile)
        
    return ret
        
def reformat_bboxes(images_box_path_dict:list, paras_dict:dict):
    """
    把bbox重新组装成一个list，每个元素[x0, y0, x1, y1, block_content, idx_x, idx_y], 初始时候idx_x, idx_y都是None. 对于图片、公式来说，block_content是图片的地址， 对于段落来说，block_content是段落的内容
    """
    all_bboxes = []
    for bbox, image_info in images_box_path_dict.items():
        all_bboxes.append([bbox[0], bbox[1], bbox[2], bbox[3], image_info, None, None, 'image'])
    
    paras_dict = paras_dict[f"page_{paras_dict['page_id']}"]
    
    for block_id, kvpair in paras_dict.items():
        bbox = kvpair['bbox']
        content = kvpair
        all_bboxes.append([bbox[0], bbox[1], bbox[2], bbox[3], content, None, None, 'text'])
    
    return all_bboxes
        
        
def concat2markdown(all_bboxes:list):
    """
    对排序后的bboxes拼接内容
    """
    content_md = ""
    for box in all_bboxes:
        content_type = box[CONTENT_TYPE_IDX]
        if content_type == 'image':
            image_type = box[CONTENT_IDX][1]
            image_path = box[CONTENT_IDX][0]
            content_md += f"![{image_type}]({image_path})"
            content_md += "\n\n"
        elif content_type == 'text': # 组装文本
            paras = box[CONTENT_IDX]['paras']
            text_content = ""
            for para_id, para in paras.items():# 拼装内部的段落文本
                text_content += para['text']
                text_content += "\n\n"
            
            content_md += text_content
        else:
            raise Exception(f"ERROR: {content_type} is not supported!")
        
    return content_md
    


def main(s3_pdf_path: str, s3_pdf_profile: str, pdf_model_path:str, pdf_model_profile:str, save_path: str):
    """

    """
    pth = Path(s3_pdf_path)
    book_name = pth.name
    #book_name = "".join(os.path.basename(s3_pdf_path).split(".")[0:-1])
    res_dir_path = None
    exclude_bboxes = []
    text_content_save_path = f"{save_path}/{book_name}/book.md"
    metadata_save_path = f"{save_path}/{book_name}/metadata.json"  
    
    
    try:
        pdf_bytes = read_pdf(s3_pdf_path, s3_pdf_profile)
        pdf_docs = fitz.open("pdf", pdf_bytes)
        for page_id, page in enumerate(pdf_docs):
            model_output_json = os.path.join(pdf_model_path, f"page_{page_id+1}.json") # 模型输出的页面编号从1开始的
            json_from_docx = read_pdf(model_output_json, pdf_model_profile) # TODO 这个读取方法名字应该改一下，避免语义歧义
            json_from_docx_obj = json.loads(json_from_docx)

            # 解析图片
            image_bboxes  = parse_images(page_id, page, res_dir_path, json_from_docx_obj, exclude_bboxes)

            # 解析表格
            table_bboxes  = parse_tables(page_id, page, res_dir_path, json_from_docx_obj, exclude_bboxes)

            # 解析公式
            equations_interline_bboxes, equations_inline_bboxes = parse_equations(page_id, page, res_dir_path, json_from_docx_obj, exclude_bboxes)
            
            # 把图、表、公式都进行截图，保存到本地，返回图片路径作为内容
            images_box_path_dict = get_images_by_bboxes(book_name, page_id, page, save_path, s3_pdf_profile, image_bboxes, table_bboxes, equations_inline_bboxes, equations_interline_bboxes) # 只要表格和图片的截图
            
            # 解析文字段落
            
            footer_bboxes =[]
            header_bboxes = []
            exclude_bboxes = image_bboxes + table_bboxes
            paras_dict = parse_blocks_per_page(page, page_id, image_bboxes, table_bboxes, equations_inline_bboxes, equations_interline_bboxes, footer_bboxes, header_bboxes)
            

            # 最后一步，根据bbox进行从左到右，从上到下的排序，之后拼接起来, 排序
            
            all_bboxes = reformat_bboxes(images_box_path_dict, paras_dict) # 由于公式目前还没有，所以equation_bboxes是None，多数存在段落里，暂时不解析
            # 返回的是一个数组，每个元素[x0, y0, x1, y1, block_content, idx_x, idx_y], 初始时候idx_x, idx_y都是None. 对于图片、公式来说，block_content是图片的地址， 对于段落来说，block_content是段落的内容
            sorted_bboxes = bbox_sort(all_bboxes)
            markdown_text = concat2markdown(sorted_bboxes)
            
            parent_dir = os.path.dirname(text_content_save_path)
            if not os.path.exists(parent_dir):
                os.makedirs(parent_dir)
            
            with open(text_content_save_path, "a") as f:
                f.write(markdown_text)
                f.write(chr(12)) #换页符   
        # end for
        # 写一个小的json,记录元数据
        metadata = {"book_name": book_name, "pdf_path": s3_pdf_path, "pdf_model_path": pdf_model_path, "save_path": save_path}
        with open(metadata_save_path, "w") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)
             
    except Exception as e:
        print(f"ERROR: {s3_pdf_path}, {e}", file=sys.stderr)
        logger.exception(e)


@click.command()
@click.option('--pdf-file-sub-path', help='s3上pdf文件的路径')
@click.option('--save-path', help='解析出来的图片，文本的保存父目录')
def main_shell(pdf_file_sub_path:str, save_path:str):
    #pdf_bin_file_path = "s3://llm-raw-snew/llm-raw-scihub/scimag07865000-07865999/10.1007/"
    pdf_bin_file_parent_path = "s3://llm-raw-snew/llm-raw-scihub/"
    pdf_bin_file_profile = "s2"
    #pdf_model_dir = "s3://llm-pdf-text/layout_det/scihub/scimag07865000-07865999/10.1007/"
    pdf_model_parent_dir = "s3://llm-pdf-text/layout_det/scihub/"
    pdf_model_profile = "langchao"
    
    p = Path(pdf_file_sub_path)
    pdf_parent_path = p.parent
    pdf_file_name = p.name   # pdf文静名字，含后缀
    pdf_bin_file_path  = os.path.join(pdf_bin_file_parent_path, pdf_parent_path)
    pdf_model_dir = os.path.join(pdf_model_parent_dir, pdf_parent_path)

    main(os.path.join(pdf_bin_file_path, pdf_file_name), pdf_bin_file_profile, os.path.join(pdf_model_dir, pdf_file_name), pdf_model_profile, save_path)

if __name__ == '__main__':
    # 输入可以用以下命令生成批量pdf
    # aws s3 ls s3://llm-pdf-text/layout_det/scihub/ --profile langchao | tail -n 10 | awk '{print "s3://llm-pdf-text/layout_det/scihub/"$4}' | xargs -I{}  aws s3 ls {} --recursive --profile langchao  | awk '{print substr($4,19)}' | parallel -j 1 echo {//} | sort -u
    main_shell()
