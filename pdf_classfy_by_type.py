"""
根据利用meta_scan得到的结果，对pdf是否为文字版进行分类。
分类条件：
1. 页面大小不一致，波动
2. 图片占比太大
3. 文字过于稀疏，比如ppt
4. 图片大小都基本一样，也就是方差很小：具体做法是每一page最大图片的方差小于1.5个标准差。

"""
import click
import json
import sys
from loguru import logger
import numpy as np


def mymax(alist: list):
    if len(alist) == 0:
        return 0  # 空是0， 0*0也是0大小q
    else:
        return max(alist)


def classify_by_area(page_width, page_height, img_sz_list, pdf_path):
    """
    如果是文本那么返回1，如果是图片那么返回0
    """
    total_pg = len(img_sz_list)
    # 除掉没有任何图片的页面。
    no_image_pages = [[[w, h] for w, h in img_info if w and h] for img_info in img_sz_list]
    if len(no_image_pages) == 0:
        return 1  # 说明没有图片，是一种文本pdf

    # 判断方法：随机抽取3个页面，不足3个的取全部，判断这3个页面的图片面积占比是否大于0.8
    select_page_cnt = 9
    page_num = []
    if total_pg <= select_page_cnt:
        page_num = list(range(total_pg))
    else:
        page_num = np.random.choice(total_pg, select_page_cnt, replace=False)

    image_page_cnt = 0
    for i in page_num:
        img_info = img_sz_list[i]
        if len(img_info) > 0:
            img_area = max([w * h for w, h in img_info])  # 只计算最大的图片面积
            if img_area >= page_width * page_height * 0.8:
                image_page_cnt += 1

    result1 = int(image_page_cnt < select_page_cnt // 2)

    # 还有一种情况，这3个页面里图片的个数和最大图片大小一样，说明是扫描
    # 只计算图片面积有时候阈值会有问题，因为有些图片是很小。因此另一种规则则对那些
    # result2 = 0
    # img_sz_list_selected = [img_sz_list[i] for i in page_num]
    # image_per_page_cnt = [len(img_info) for img_info in img_sz_list_selected]
    # image_area_max_per_page = [mymax([w*h for w,h in img_info]) for img_info in img_sz_list_selected]

    # if image_area_max_per_page[0] == 0:
    #     result = 1
    # elif len(set(image_per_page_cnt))==1 and len(set(image_area_max_per_page))==1:
    #     result = 0

    return result1


@click.command()
@click.option("--json_file", type=str, help="pdf信息")
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
                page_width = o["page_width_pts"]
                page_height = o["page_height_pts"]
                img_sz_list = o["image_area_pix_every_page"]
                pdf_path = o['pdf_path']
                tag = classify_by_area(page_width, page_height, img_sz_list, pdf_path)
                o['is_text_pdf'] = tag
                print(json.dumps(o, ensure_ascii=False))
    except Exception as e:
        print("ERROR: ", e, file=sys.stderr)


if __name__ == "__main__":
    main()
