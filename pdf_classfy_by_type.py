"""
根据利用meta_scan得到的结果，对pdf是否为文字版进行分类。
定义标准：
一、什么pdf会是文字pdf，只要满足以下任意一条
  1. 随机抽取N页，如果有任何一页文字数目大于100
  2. 只要存在一个页面，图片的数量为0
二、什么是扫描版pdf，只要满足以下任意一条
  1. ~~80%页面上的最大图大小一样并且面积超过页面面积0.6~~
  2. 除匹配到文字版的其他所有

"""
import click
import json
import sys
from loguru import logger
import numpy as np
from loguru import logger

TEXT_LEN_THRESHOLD = 100


def mymax(alist: list):
    if len(alist) == 0:
        return 0  # 空是0， 0*0也是0大小q
    else:
        return max(alist)


def classify_by_area(pdf_path, total_page: int, page_width, page_height, img_sz_list):
    """
    80%页面上的最大图大小一样并且面积超过页面面积0.6则返回False，否则返回True
    :param pdf_path:
    :param total_page:
    :param page_width:
    :param page_height:
    :param img_sz_list:
    :return:
    """
    # 只要有一页没有图片，那么就是文字pdf
    if any([len(img_sz) == 0 for img_sz in img_sz_list]):
        return True
    max_image_area_per_page = [mymax([(x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in page_img_sz]) for page_img_sz in img_sz_list]
    page_area = page_width * page_height
    max_image_area_per_page = [area / page_area for area in max_image_area_per_page]
    max_image_area_per_page = [area for area in max_image_area_per_page if area > 0.6]
    if len(max_image_area_per_page) >= 0.8 * total_page:
        return False
    else:
        return True


def classify_by_text_len(text_len_list: list, total_page: int):
    """
    随机抽取10%的页面，如果少于5个页面，那么就取全部页面。
    查看页面上的文字长度，如果有任何一个页面的文字长度大于100，那么就是文字pdf
    :param total_page:
    :param text_len_list:
    :return:
    """
    select_page_cnt = total_page // 10  # 选取10%的页面
    if select_page_cnt < 5:
        select_page_cnt = total_page

    page_num = np.random.choice(total_page, select_page_cnt, replace=False)
    text_len_lst = [text_len_list[i] for i in page_num]
    is_text_pdf = any([text_len > TEXT_LEN_THRESHOLD for text_len in text_len_lst])
    return is_text_pdf


def classify(pdf_path, total_page: int, page_width, page_height, img_sz_list: list, text_len_list: list):
    """
    这里的图片和页面长度单位是pts
    :param total_page:
    :param text_len_list:
    :param page_width:
    :param page_height:
    :param img_sz_list:
    :param pdf_path:
    :return:
    """
    is_text_pdf_1 = classify_by_area(pdf_path, total_page, page_width, page_height, img_sz_list)
    is_text_pdf_2 = classify_by_text_len(text_len_list, total_page)
    if all([is_text_pdf_1, is_text_pdf_2]):
        return True
    elif not any([is_text_pdf_1, is_text_pdf_2]):
        return False
    else:
        print(f"WARNING: {pdf_path} is not classified by area and text_len", file=sys.stderr)
        return False


@click.command()
@click.option("--json-file", type=str, help="pdf信息")
def main(json_file):
    if json_file is None:
        print("json_file is None", file=sys.stderr)
        exit(0)
    try:
        with open(json_file, "r") as f:
            for l in f:
                if l.strip() == "":
                    continue
                o = json.loads(l)
                total_page = o["total_page"]
                page_width = o["page_width_pts"]
                page_height = o["page_height_pts"]
                img_sz_list = o["image_info_per_page"]
                text_len_list = o['text_len_per_page']
                pdf_path = o['pdf_path']
                is_encrypted = o['is_encrypted']
                if is_encrypted:
                    continue
                tag = classify(pdf_path, total_page, page_width, page_height, img_sz_list, text_len_list)
                o['is_text_pdf'] = tag
                print(json.dumps(o, ensure_ascii=False))
    except Exception as e:
        print("ERROR: ", e, file=sys.stderr)
        logger.exception(e)
        


if __name__ == "__main__":
    main()
