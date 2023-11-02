"""
输入： s3路径，每行一个
输出： pdf文件元信息，包括每一页上的所有图片的长宽高，bbox位置
"""

import sys
import click
from libs.commons import read_pdf
import json
import fitz


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
            recs = page.get_image_rects(img, transform=True)
            if recs:
                rec = recs[0][0]
                x0, y0, x1, y1 = int(rec[0]), int(rec[1]), int(rec[2]), int(rec[3])
                width = x1 - x0
                height = y1 - y0

                if (x0, y0, x1, y1) in dedup:  # 这里面会出现一些重复的bbox，无需重复出现，需要去掉
                    continue
                if all([width, height]):  # 长和宽任何一个都不能是0，否则这个图片不可见，没有实际意义
                    continue
                dedup.add((x0, y0, x1, y1))

                page_result.append((x0, y0, x1, y1))

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
    image_info_every_page = get_image_info(doc)
    text_len_per_page = get_pdf_textlen_per_page(doc)

    # 最后输出一条json
    res = {
        "pdf_path": s3_pdf_path,
        "is_needs_password": is_needs_password,
        "is_encrypted": is_encrypted,
        "total_page": total_page,
        "page_width_pts": int(page_width_pts),
        "page_height_pts": int(page_height_pts),
        "image_info_per_page": image_info_every_page,
        "text_len_per_page": text_len_per_page,
        "metadata": doc.metadata
    }
    print(json.dumps(res, ensure_ascii=False))


@click.command()
@click.option('--s3-pdf-path', help='s3上pdf文件的路径')
@click.option('--s3-profile', help='s3上的profile')
def main(s3_pdf_path: str, s3_profile: str):
    """

    """
    try:
        file_content = read_pdf(s3_pdf_path, s3_profile)
        pdf_meta_scan(s3_pdf_path, file_content)
    except Exception as e:
        print(f"ERROR: {s3_pdf_path}, {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
