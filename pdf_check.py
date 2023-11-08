import sys
import click
from libs.commons import read_pdf
import json
import fitz
import click
import json
import os
from loguru import logger
import numpy as np
from loguru import logger
from collections import OrderedDict, Counter

TEXT_LEN_THRESHOLD = 200
TEXT_LEN_SAMPLE_RATIO=0.1 # 抽取0.1的页面进行文字长度统计


def mymax(alist: list):
    if len(alist) == 0:
        return 0  # 空是0， 0*0也是0大小q
    else:
        return max(alist)


def classify_by_area(pdf_path, total_page: int, page_width, page_height, img_sz_list, text_len_list: list):
    """
    80%页面上的最大图大小一样并且面积超过页面面积0.6则返回False，否则返回True
    :param pdf_path:
    :param total_page:
    :param page_width:
    :param page_height:
    :param img_sz_list:
    :return:
    """
    # 只要有一页没有图片，那么就是文字pdf。但是同时还需要满足一个条件就是这个页面上同时不能有文字。发现过一些扫描版pdf，上面有一些空白页面，既没有图片也没有文字。
    if any([len(img_sz) == 0 for img_sz in img_sz_list]): # 含有不含图片的页面
        # 现在找到这些页面的index
        empty_page_index = [i for i, img_sz in enumerate(img_sz_list) if len(img_sz) == 0]
        # 然后检查这些页面上是否有文字
        text_len_at_page_idx = [text_len for i, text_len in enumerate(text_len_list) if i in empty_page_index and text_len > 0]
        if len(text_len_at_page_idx) != 0: # 没有图片，但是有文字，说明可能是个文字版，如果没有文字则无法判断，留给下一步
            return True

    # 通过objid去掉重复出现10次以上的图片，这些图片是隐藏的透明图层，其特点是id都一样
    # 先对每个id出现的次数做个统计
    objid_cnt = Counter([objid for page_img_sz in img_sz_list for _, _, _, _, objid in page_img_sz])
    # 再去掉出现次数大于10的
    repeat_threshold = min(2, total_page)
    bad_image_objid = set([objid for objid, cnt in objid_cnt.items() if cnt >= repeat_threshold])
    bad_image_page_idx = [i for i, page_img_sz in enumerate(img_sz_list) if any([objid in bad_image_objid for _, _, _, _, objid in page_img_sz])]
    text_len_at_bad_image_page_idx = [text_len for i, text_len in enumerate(text_len_list) if i in bad_image_page_idx and text_len > 0]
    # 检查一下这些bad_image里有没有与page大小差不多的，如果有，那么就是文字pdf。于此同时，还应当保证这些图片出现的页面上都存在文字。
    fake_image_ids = [objid for objid in bad_image_objid if any([abs((x1 - x0) * (y1 - y0) / page_width * page_height) > 0.9 for images in img_sz_list for x0, y0, x1, y1, _ in images])]
    
    if len(fake_image_ids)>0 and any([l>TEXT_LEN_THRESHOLD for l in text_len_at_bad_image_page_idx]): #这些透明图片所在的页面上有文字大于阈值
        return True
    
    img_sz_list = [[img_sz for img_sz in page_img_sz if img_sz[-1] not in bad_image_objid] for page_img_sz in img_sz_list] # 过滤掉重复出现的图片
    
    # 计算每个页面上最大的图的面积，然后计算这个面积占页面面积的比例
    max_image_area_per_page = [mymax([(x1 - x0) * (y1 - y0) for x0, y0, x1, y1, _ in page_img_sz]) for page_img_sz in img_sz_list]
    page_area = page_width * page_height
    max_image_area_per_page = [area / page_area for area in max_image_area_per_page]
    max_image_area_per_page = [area for area in max_image_area_per_page if area > 0.6]
    if len(max_image_area_per_page) >= 0.8 * total_page: # 这里条件成立的前提是把反复出现的图片去掉了。这些图片是隐藏的透明图层，其特点是id都一样
        return False
    else:
        return True


def classify_by_text_len(text_len_list: list, total_page: int):
    """
    随机抽取10%的页面，如果少于5个页面，那么就取全部页面。
    查看页面上的文字长度，如果有任何一个页面的文字长度大于TEXT_LEN_THRESHOLD，那么就是文字pdf
    :param total_page:
    :param text_len_list:
    :return:
    """
    select_page_cnt = int(total_page*TEXT_LEN_SAMPLE_RATIO)  # 选取10%的页面
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
    is_text_pdf_1 = classify_by_area(pdf_path, total_page, page_width, page_height, img_sz_list, text_len_list)
    is_text_pdf_2 = classify_by_text_len(text_len_list, total_page)
    if all([is_text_pdf_1, is_text_pdf_2]):
        return True
    elif not any([is_text_pdf_1, is_text_pdf_2]):
        return False
    else:
        logger.warning(f"WARNING: {pdf_path} is not classified by area and text_len, by_image_area: {is_text_pdf_1}, by_text: {is_text_pdf_2}") # 利用这种情况可以快速找出来哪些pdf比较特殊，针对性修正分类算法
        return False


def get_image_info(doc: fitz.Document) -> list:
    """
    返回每个页面里的图片的四元组，每个页面多个图片。
    :param doc:
    :return:
    """
    result = []
    for page in doc:
        page_result = []  # 存每个页面里的多张图四元组信息
        dedup = set()
        result.append(page_result)
        items = page.get_images()
        for img in items:
            # 这里返回的是图片在page上的实际展示的大小。返回一个数组，每个元素第一部分是
            img_bojid = img[0] # 在pdf文件中是全局唯一的，如果这个图反复出现在pdf里那么就可能是垃圾信息，例如水印、页眉页脚等
            recs = page.get_image_rects(img, transform=True)
            if recs:
                rec = recs[0][0]
                x0, y0, x1, y1 = int(rec[0]), int(rec[1]), int(rec[2]), int(rec[3])
                width = x1 - x0
                height = y1 - y0

                if (x0, y0, x1, y1) in dedup:  # 这里面会出现一些重复的bbox，无需重复出现，需要去掉
                    continue
                if not all([width, height]):  # 长和宽任何一个都不能是0，否则这个图片不可见，没有实际意义
                    continue
                dedup.add((x0, y0, x1, y1))

                page_result.append((x0, y0, x1, y1, img_bojid))

    return result


def get_pdf_page_size_pts(doc: fitz.Document):
    page_cnt = len(doc)
    l: int = min(page_cnt, 5)
    # 取页面最大的宽和高度
    page_width_pts = 0
    page_height_pts = 0
    for i in range(l):
        page = doc[i]
        page_rect = page.rect
        page_width_pts, page_height_pts = max(page_rect.width, page_width_pts), max(page_rect.height, page_height_pts)

    return page_width_pts, page_height_pts


def get_pdf_textlen_per_page(doc: fitz.Document):
    text_len_lst = []
    for page in doc:
        text_block = page.get_text("blocks")
        text_block_len = sum([len(t[4]) for t in text_block])
        text_len_lst.append(text_block_len)

    return text_len_lst


def pdf_meta_scan(s3_pdf_path: str, pdf_bytes: bytes):
    """
    :param s3_pdf_path:
    :param pdf_bytes: pdf文件的二进制数据
    几个维度来评价：是否加密，是否需要密码，纸张大小，总页数，是否文字可提取
    """
    doc = fitz.open("pdf", pdf_bytes)
    is_needs_password = doc.needs_pass
    is_encrypted = doc.is_encrypted
    total_page = len(doc)
    page_width_pts, page_height_pts = get_pdf_page_size_pts(doc)
    image_info_per_page = get_image_info(doc)
    text_len_per_page = get_pdf_textlen_per_page(doc)

    # 最后输出一条json
    res = {
        "pdf_path": s3_pdf_path,
        "is_needs_password": is_needs_password,
        "is_encrypted": is_encrypted,
        "total_page": total_page,
        "page_width_pts": int(page_width_pts),
        "page_height_pts": int(page_height_pts),
        "image_info_per_page": image_info_per_page,
        "text_len_per_page": text_len_per_page,
        "metadata": doc.metadata
    }
    return res

def find_pdfs(dir_path):
    pdf_files = []

    for root, dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith(".pdf"):
                pdf_files.append(os.path.join(root, file))

    return pdf_files

@click.command()
@click.option('--pdf-dir', help='pdf文件所在的目录', required=True)
def main(pdf_dir: str):
    """

    """
    pdf_file_paths = find_pdfs(pdf_dir)
    pdf_check_result = []
    try:
        for pdf in pdf_file_paths:
            file_content = read_pdf(pdf, None)
            pdf_meta = pdf_meta_scan(pdf, file_content)
            
            total_page = pdf_meta["total_page"]
            page_width = pdf_meta["page_width_pts"]
            page_height = pdf_meta["page_height_pts"]
            img_sz_list = pdf_meta["image_info_per_page"]
            text_len_list = pdf_meta['text_len_per_page']
            pdf_path = pdf_meta['pdf_path']
            is_encrypted = pdf_meta['is_encrypted']
            is_needs_password = pdf_meta['is_needs_password']
            
            if is_encrypted or total_page == 0 or is_needs_password:  # 加密的，需要密码的，没有页面的，都不处理
                logger.error(f"{pdf_path} is encrypted or needs password or has no page")
                
            is_text_pdf = classify(pdf_path, total_page, page_width, page_height, img_sz_list, text_len_list)
            check_result = is_text_pdf
            pdf_check_result.append([pdf, check_result])
            
            # 保存结果到文件里
            result_file = os.path.join(pdf_dir, "pdf_check_result.txt")
            with open(result_file, "w", encoding="utf-8") as f:
                for pdf_file, result in pdf_check_result:
                    f.write(f"{pdf_file}\t{result}\n")
                    
        # 打印统计结果
        total = len(pdf_check_result)
        text_pdf = len([pdf for pdf, result in pdf_check_result if result])
        scan_pdf = len([pdf for pdf, result in pdf_check_result if not result])
        text_ratio = round(text_pdf / total, 2)
        print("-"*100)
        print("总共（本）: {}, 文字版（本）: {}, 扫描版（本）: {}, 文字占比：{}".format(total, text_pdf, scan_pdf, text_ratio))
        print(f"详细结果参考日志文件：{result_file}\n")
        
    except Exception as e:
        logger.exception(e)


if __name__ == '__main__':
    main()