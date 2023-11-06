"""
根据利用meta_scan得到的结果，对pdf是否为文字版进行分类。
定义标准：
一、什么pdf会是文字pdf，只要满足以下任意一条
  1. 随机抽取N页，如果有任何一页文字数目大于100
  2. 只要存在一个页面，图片的数量为0
二、什么是扫描版pdf，只要满足以下任意一条
  1. ~~80%页面上的最大图大小一样并且面积超过页面面积0.6~~
  2. 大部分页面上文字的长度都是相等的。

"""
import click
import json
import sys
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
        print(f"WARNING: {pdf_path} is not classified by area and text_len, by_image_area: {is_text_pdf_1}, by_text: {is_text_pdf_2}", file=sys.stderr) # 利用这种情况可以快速找出来哪些pdf比较特殊，针对性修正分类算法
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
                is_needs_password = o['is_needs_password']
                if is_encrypted or total_page == 0 or is_needs_password:  # 加密的，需要密码的，没有页面的，都不处理
                    continue
                tag = classify(pdf_path, total_page, page_width, page_height, img_sz_list, text_len_list)
                o['is_text_pdf'] = tag
                print(json.dumps(o, ensure_ascii=False))
    except Exception as e:
        print("ERROR: ", e, file=sys.stderr)
        


if __name__ == "__main__":
    # main()
    false = False
    true = True
    null = None
    o = {"pdf_path":"s3://llm-raw-snew/llm-raw-the-eye/raw/World%20Tracker%20Library/worldtracker.org/media/library/Science/Computer%20Science/Shreiner%20-%20OpenGL%20Programming%20Guide%206e%20%5BThe%20Redbook%5D%20%28AW%2C%202008%29.pdf","is_needs_password":false,"is_encrypted":false,"total_page":978,"page_width_pts":368,"page_height_pts":513,"image_info_per_page":[[[0,0,368,513,10037]],[[0,0,368,513,4]],[[0,0,368,513,7]],[[0,0,368,513,10]],[[0,0,368,513,13]],[[0,0,368,513,16]],[[0,0,368,513,19]],[[0,0,368,513,22]],[[0,0,368,513,25]],[[0,0,368,513,28]],[[0,0,368,513,31]],[[0,0,368,513,34]],[[0,0,368,513,37]],[[0,0,368,513,40]],[[0,0,368,513,43]],[[0,0,368,513,46]],[[0,0,368,513,49]],[[0,0,368,513,52]],[[0,0,368,513,55]],[[0,0,368,513,58]],[[0,0,368,513,61]],[[0,0,368,513,64]],[[0,0,368,513,67]],[[0,0,368,513,70]],[[0,0,368,513,73]],[[0,0,368,516,76]],[[0,0,368,516,79]],[[0,0,368,513,82]],[[0,0,368,513,85]],[[0,0,368,513,88]],[[0,0,368,513,91]],[[0,0,368,513,94]],[[0,0,368,513,97]],[[0,0,368,513,100]],[[0,0,368,513,103]],[[0,0,368,513,106]],[[0,0,368,513,109]],[[0,0,368,513,112]],[[0,0,368,513,115]],[[0,0,368,513,118]],[[0,0,368,513,121]],[[0,0,368,513,124]],[[0,0,368,513,127]],[[0,0,368,513,130]],[[0,0,368,513,133]],[[0,0,368,513,136]],[[0,0,368,513,139]],[[0,0,368,513,142]],[[0,0,368,513,145]],[[0,0,368,513,148]],[[0,0,368,513,151]],[[0,0,368,513,154]],[[0,0,368,513,157]],[[0,0,368,513,160]],[[0,0,368,513,163]],[[0,0,368,513,166]],[[0,0,368,513,169]],[[0,0,368,513,172]],[[0,0,368,513,175]],[[0,0,368,513,178]],[[0,0,368,513,181]],[[0,0,368,513,184]],[[0,0,368,513,187]],[[0,0,368,513,190]],[[0,0,368,513,193]],[[0,0,368,513,196]],[[0,0,368,513,199]],[[0,0,368,513,202]],[[0,0,368,513,205]],[[0,0,368,513,208]],[[0,0,368,513,211]],[[0,0,368,513,214]],[[0,0,368,513,217]],[[0,0,368,513,220]],[[0,0,368,513,223]],[[0,0,368,513,226]],[[0,0,368,513,229]],[[0,0,368,513,232]],[[0,0,368,513,235]],[[0,0,368,513,238]],[[0,0,368,513,241]],[[0,0,368,513,244]],[[0,0,368,513,247]],[[0,0,368,513,250]],[[0,0,368,513,253]],[[0,0,368,513,256]],[[0,0,368,513,259]],[[0,0,368,513,262]],[[0,0,368,513,265]],[[0,0,368,513,268]],[[0,0,368,513,271]],[[0,0,368,513,274]],[[0,0,368,513,277]],[[0,0,368,513,280]],[[0,0,368,513,283]],[[0,0,368,513,286]],[[0,0,368,513,289]],[[0,0,368,513,292]],[[0,0,368,513,295]],[[0,0,368,513,298]],[[0,0,368,513,301]],[[0,0,368,513,304]],[[0,0,368,513,307]],[[0,0,368,513,310]],[[0,0,368,513,313]],[[0,0,368,513,316]],[[0,0,368,513,319]],[[0,0,368,513,322]],[[0,0,368,513,325]],[[0,0,368,513,328]],[[0,0,368,513,331]],[[0,0,368,513,334]],[[0,0,368,513,337]],[[0,0,368,513,340]],[[0,0,368,513,343]],[[0,0,368,513,346]],[[0,0,368,513,349]],[[0,0,368,513,352]],[[0,0,368,513,355]],[[0,0,368,513,358]],[[0,0,368,513,361]],[[0,0,368,513,364]],[[0,0,368,513,367]],[[0,0,368,513,370]],[[0,0,368,513,373]],[[0,0,368,513,376]],[[0,0,368,513,379]],[[0,0,368,513,382]],[[0,0,368,513,385]],[[0,0,368,513,388]],[[0,0,368,513,391]],[[0,0,368,513,394]],[[0,0,368,513,397]],[[0,0,368,513,400]],[[0,0,368,513,403]],[[0,0,368,513,406]],[[0,0,368,513,409]],[[0,0,368,513,412]],[[0,0,368,513,415]],[[0,0,368,513,418]],[[0,0,368,513,421]],[[0,0,368,513,424]],[[0,0,368,513,427]],[[0,0,368,513,430]],[[0,0,368,513,433]],[[0,0,368,513,436]],[[0,0,368,513,439]],[[0,0,368,513,442]],[[0,0,368,513,445]],[[0,0,368,513,448]],[[0,0,368,513,451]],[[0,0,368,513,454]],[[0,0,368,513,457]],[[0,0,368,513,460]],[[0,0,368,513,463]],[[0,0,368,513,466]],[[0,0,368,513,469]],[[0,0,368,513,472]],[[0,0,368,513,475]],[[0,0,368,513,478]],[[0,0,368,513,481]],[[0,0,368,513,484]],[[0,0,368,513,487]],[[0,0,368,513,490]],[[0,0,368,513,493]],[[0,0,368,513,496]],[[0,0,368,513,499]],[[0,0,368,513,502]],[[0,0,368,513,505]],[[0,0,368,513,508]],[[0,0,368,513,511]],[[0,0,368,513,514]],[[0,0,368,513,517]],[[0,0,368,513,520]],[[0,0,368,513,523]],[[0,0,368,513,526]],[[0,0,368,513,529]],[[0,0,368,513,532]],[[0,0,368,513,535]],[[0,0,368,513,538]],[[0,0,368,513,541]],[[0,0,368,513,544]],[[0,0,368,513,547]],[[0,0,368,513,550]],[[0,0,368,513,553]],[[0,0,368,513,556]],[[0,0,368,513,559]],[[0,0,368,513,562]],[[0,0,368,513,565]],[[0,0,368,513,568]],[[0,0,368,513,571]],[[0,0,368,513,574]],[[0,0,368,513,577]],[[0,0,368,513,580]],[[0,0,368,513,583]],[[0,0,368,513,586]],[[0,0,368,513,589]],[[0,0,368,513,592]],[[0,0,368,513,595]],[[0,0,368,513,598]],[[0,0,368,513,601]],[[0,0,368,513,604]],[[0,0,368,513,607]],[[0,0,368,513,610]],[[0,0,368,513,613]],[[0,0,368,513,616]],[[0,0,368,513,619]],[[0,0,368,513,622]],[[0,0,368,513,625]],[[0,0,368,513,628]],[[0,0,368,513,631]],[[0,0,368,513,634]],[[0,0,368,513,637]],[[0,0,368,513,640]],[[0,0,368,513,643]],[[0,0,368,513,646]],[[0,0,368,513,649]],[[0,0,368,513,652]],[[0,0,368,513,655]],[[0,0,368,513,658]],[[0,0,368,513,661]],[[0,0,368,513,664]],[[0,0,368,513,667]],[[0,0,368,513,670]],[[0,0,368,513,673]],[[0,0,368,513,676]],[[0,0,368,513,679]],[[0,0,368,513,682]],[[0,0,368,513,685]],[[0,0,368,513,688]],[[0,0,368,513,691]],[[0,0,368,513,694]],[[0,0,368,513,697]],[[0,0,368,513,700]],[[0,0,368,513,703]],[[0,0,368,513,706]],[[0,0,368,513,709]],[[0,0,368,513,712]],[[0,0,368,513,715]],[[0,0,368,513,718]],[[0,0,368,513,721]],[[0,0,368,513,724]],[[0,0,368,513,727]],[[0,0,368,513,730]],[[0,0,368,513,733]],[[0,0,368,513,736]],[[0,0,368,513,739]],[[0,0,368,513,742]],[[0,0,368,513,745]],[[0,0,368,513,748]],[[0,0,368,513,751]],[[0,0,368,513,754]],[[0,0,368,513,757]],[[0,0,368,513,760]],[[0,0,368,513,763]],[[0,0,368,513,766]],[[0,0,368,513,769]],[[0,0,368,513,772]],[[0,0,368,513,775]],[[0,0,368,513,778]],[[0,0,368,513,781]],[[0,0,368,513,784]],[[0,0,368,513,787]],[[0,0,368,513,790]],[[0,0,368,513,793]],[[0,0,368,513,796]],[[0,0,368,513,799]],[[0,0,368,513,802]],[[0,0,368,513,805]],[[0,0,368,513,808]],[[0,0,368,513,811]],[[0,0,368,513,814]],[[0,0,368,513,817]],[[0,0,368,513,820]],[[0,0,368,513,823]],[[0,0,368,513,826]],[[0,0,368,513,829]],[[0,0,368,513,832]],[[0,0,368,513,835]],[[0,0,368,513,838]],[[0,0,368,513,841]],[[0,0,368,513,844]],[[0,0,368,513,847]],[[0,0,368,513,850]],[[0,0,368,513,853]],[[0,0,368,513,856]],[[0,0,368,513,859]],[[0,0,368,513,862]],[[0,0,368,513,865]],[[0,0,368,513,868]],[[0,0,368,513,871]],[[0,0,368,513,874]],[[0,0,368,513,877]],[[0,0,368,513,880]],[[0,0,368,513,883]],[[0,0,368,513,886]],[[0,0,368,513,889]],[[0,0,368,513,892]],[[0,0,368,513,895]],[[0,0,368,513,898]],[[0,0,368,513,901]],[[0,0,368,513,904]],[[0,0,368,513,907]],[[0,0,368,513,910]],[[0,0,368,513,913]],[[0,0,368,513,916]],[[0,0,368,513,919]],[[0,0,368,513,922]],[[0,0,368,513,925]],[[0,0,368,513,928]],[[0,0,368,513,931]],[[0,0,368,513,934]],[[0,0,368,513,937]],[[0,0,368,513,940]],[[0,0,368,513,943]],[[0,0,368,513,946]],[[0,0,368,513,949]],[[0,0,368,513,952]],[[0,0,368,513,955]],[[0,0,368,513,958]],[[0,0,368,513,961]],[[0,0,368,513,964]],[[0,0,368,513,967]],[[0,0,368,513,970]],[[0,0,368,513,973]],[[0,0,368,513,976]],[[0,0,368,513,979]],[[0,0,368,513,982]],[[0,0,368,513,985]],[[0,0,368,513,988]],[[0,0,368,513,991]],[[0,0,368,513,994]],[[0,0,368,513,997]],[[0,0,368,513,1000]],[[0,0,368,513,1003]],[[0,0,368,513,1006]],[[0,0,368,513,1009]],[[0,0,368,513,1012]],[[0,0,368,513,1015]],[[0,0,368,513,1018]],[[0,0,368,513,2797]],[[0,0,368,513,2798]],[[0,0,368,513,2799]],[[0,0,368,513,2800]],[[0,0,368,513,2801]],[[0,0,368,513,2802]],[[0,0,368,513,2803]],[[0,0,368,513,2804]],[[0,0,368,513,2805]],[[0,0,368,513,2806]],[[0,0,368,513,2807]],[[0,0,368,513,2808]],[[0,0,368,513,2809]],[[0,0,368,513,2810]],[[0,0,368,513,2811]],[[0,0,368,513,2812]],[[0,0,368,513,2813]],[[0,0,368,513,2814]],[[0,0,368,513,2815]],[[0,0,368,513,2816]],[[0,0,368,513,2817]],[[0,0,368,513,2818]],[[0,0,368,513,2819]],[[0,0,368,513,2820]],[[0,0,368,513,2821]],[[0,0,368,513,2822]],[[0,0,368,513,2823]],[[0,0,368,513,2824]],[[0,0,368,513,2825]],[[0,0,368,513,2826]],[[0,0,368,513,2827]],[[0,0,368,513,2828]],[[0,0,368,513,2829]],[[0,0,368,513,2830]],[[0,0,368,513,2831]],[[0,0,368,513,2832]],[[0,0,368,513,2833]],[[0,0,368,513,2834]],[[0,0,368,513,2835]],[[0,0,368,513,2836]],[[0,0,368,513,2837]],[[0,0,368,513,2838]],[[0,0,368,513,2839]],[[0,0,368,513,2840]],[[0,0,368,513,2841]],[[0,0,368,513,2842]],[[0,0,368,513,2843]],[[0,0,368,513,2844]],[[0,0,368,513,2845]],[[0,0,368,513,2846]],[[0,0,368,513,2847]],[[0,0,368,513,2848]],[[0,0,368,513,2849]],[[0,0,368,513,2850]],[[0,0,368,513,2851]],[[0,0,368,513,2852]],[[0,0,368,513,2853]],[[0,0,368,513,2854]],[[0,0,368,513,2855]],[[0,0,368,513,2856]],[[0,0,368,513,2857]],[[0,0,368,513,2858]],[[0,0,368,513,2859]],[[0,0,368,513,2860]],[[0,0,368,513,2861]],[[0,0,368,513,2862]],[[0,0,368,513,2863]],[[0,0,368,513,2864]],[[0,0,368,513,2797]],[[0,0,368,513,2798]],[[0,0,368,513,2799]],[[0,0,368,513,2800]],[[0,0,368,513,2801]],[[0,0,368,513,2802]],[[0,0,368,513,2803]],[[0,0,368,513,2804]],[[0,0,368,513,2805]],[[0,0,368,513,2806]],[[0,0,368,513,2807]],[[0,0,368,513,2808]],[[0,0,368,513,2809]],[[0,0,368,513,2810]],[[0,0,368,513,2811]],[[0,0,368,513,2812]],[[0,0,368,513,2813]],[[0,0,368,513,2814]],[[0,0,368,513,2815]],[[0,0,368,513,2816]],[[0,0,368,513,2817]],[[0,0,368,513,2818]],[[0,0,368,513,2819]],[[0,0,368,513,2820]],[[0,0,368,513,2821]],[[0,0,368,513,2822]],[[0,0,368,513,2823]],[[0,0,368,513,2824]],[[0,0,368,513,2825]],[[0,0,368,513,2826]],[[0,0,368,513,2827]],[[0,0,368,513,2828]],[[0,0,368,513,2829]],[[0,0,368,513,2830]],[[0,0,368,513,2831]],[[0,0,368,513,2832]],[[0,0,368,513,2833]],[[0,0,368,513,2834]],[[0,0,368,513,2835]],[[0,0,368,513,2836]],[[0,0,368,513,2837]],[[0,0,368,513,2838]],[[0,0,368,513,2839]],[[0,0,368,513,2840]],[[0,0,368,513,2841]],[[0,0,368,513,2842]],[[0,0,368,513,2843]],[[0,0,368,513,2844]],[[0,0,368,513,2845]],[[0,0,368,513,2846]],[[0,0,368,513,2847]],[[0,0,368,513,2848]],[[0,0,368,513,2849]],[[0,0,368,513,2850]],[[0,0,368,513,2851]],[[0,0,368,513,2852]],[[0,0,368,513,2853]],[[0,0,368,513,2854]],[[0,0,368,513,2855]],[[0,0,368,513,2856]],[[0,0,368,513,2857]],[[0,0,368,513,2858]],[[0,0,368,513,2859]],[[0,0,368,513,2860]],[[0,0,368,513,2861]],[[0,0,368,513,2862]],[[0,0,368,513,2863]],[[0,0,368,513,2864]],[[0,0,368,513,1293]],[[0,0,368,513,1296]],[[0,0,368,513,1299]],[[0,0,368,513,1302]],[[0,0,368,513,1305]],[[0,0,368,513,1308]],[[0,0,368,513,1311]],[[0,0,368,513,1314]],[[0,0,368,513,1317]],[[0,0,368,513,1320]],[[0,0,368,513,1323]],[[0,0,368,513,1326]],[[0,0,368,513,1329]],[[0,0,368,513,1332]],[[0,0,368,513,1335]],[[0,0,368,513,1338]],[[0,0,368,513,1341]],[[0,0,368,513,1344]],[[0,0,368,513,1347]],[[0,0,368,513,1350]],[[0,0,368,513,1353]],[[0,0,368,513,1356]],[[0,0,368,513,1359]],[[0,0,368,513,1362]],[[0,0,368,513,1365]],[[0,0,368,513,1368]],[[0,0,368,513,1371]],[[0,0,368,513,1374]],[[0,0,368,513,1377]],[[0,0,368,513,1380]],[[0,0,368,513,1383]],[[0,0,368,513,1386]],[[0,0,368,513,1389]],[[0,0,368,513,1392]],[[0,0,368,513,1395]],[[0,0,368,513,1398]],[[0,0,368,513,1401]],[[0,0,368,513,1404]],[[0,0,368,513,1407]],[[0,0,368,513,1410]],[[0,0,368,513,1413]],[[0,0,368,513,1416]],[[0,0,368,513,1419]],[[0,0,368,513,1422]],[[0,0,368,513,1425]],[[0,0,368,513,1428]],[[0,0,368,513,1431]],[[0,0,368,513,1434]],[[0,0,368,513,1437]],[[0,0,368,513,1440]],[[0,0,368,513,1443]],[[0,0,368,513,1446]],[[0,0,368,513,1449]],[[0,0,368,513,1452]],[[0,0,368,513,1455]],[[0,0,368,513,1458]],[[0,0,368,513,1461]],[[0,0,368,513,1464]],[[0,0,368,513,1467]],[[0,0,368,513,1470]],[[0,0,368,513,1473]],[[0,0,368,513,1476]],[[0,0,368,513,1479]],[[0,0,368,513,1482]],[[0,0,368,513,1485]],[[0,0,368,513,1488]],[[0,0,368,513,1491]],[[0,0,368,513,1494]],[[0,0,368,513,1497]],[[0,0,368,513,1500]],[[0,0,368,513,1503]],[[0,0,368,513,1506]],[[0,0,368,513,1509]],[[0,0,368,513,1512]],[[0,0,368,513,1515]],[[0,0,368,513,1518]],[[0,0,368,513,1521]],[[0,0,368,513,1524]],[[0,0,368,513,1527]],[[0,0,368,513,1530]],[[0,0,368,513,1533]],[[0,0,368,513,1536]],[[0,0,368,513,1539]],[[0,0,368,513,1542]],[[0,0,368,513,1545]],[[0,0,368,513,1548]],[[0,0,368,513,1551]],[[0,0,368,513,1554]],[[0,0,368,513,1557]],[[0,0,368,513,1560]],[[0,0,368,513,1563]],[[0,0,368,513,1566]],[[0,0,368,513,1569]],[[0,0,368,513,1572]],[[0,0,368,513,1575]],[[0,0,368,513,1578]],[[0,0,368,513,1581]],[[0,0,368,513,1584]],[[0,0,368,513,1587]],[[0,0,368,513,1590]],[[0,0,368,513,1593]],[[0,0,368,513,1596]],[[0,0,368,513,1599]],[[0,0,368,513,1602]],[[0,0,368,513,1605]],[[0,0,368,513,1608]],[[0,0,368,513,1611]],[[0,0,368,513,1614]],[[0,0,368,513,1617]],[[0,0,368,513,1620]],[[0,0,368,513,1623]],[[0,0,368,513,1626]],[[0,0,368,513,1629]],[[0,0,368,513,1632]],[[0,0,368,513,1635]],[[0,0,368,513,1638]],[[0,0,368,513,1641]],[[0,0,368,513,1644]],[[0,0,368,513,1647]],[[0,0,368,513,1650]],[[0,0,368,513,1653]],[[0,0,368,513,1656]],[[0,0,368,513,1659]],[[0,0,368,513,1662]],[[0,0,368,513,1665]],[[0,0,368,513,1668]],[[0,0,368,513,1671]],[[0,0,368,513,1674]],[[0,0,368,513,1677]],[[0,0,368,513,1680]],[[0,0,368,513,1683]],[[0,0,368,513,1686]],[[0,0,368,513,1689]],[[0,0,368,513,1692]],[[0,0,368,513,1695]],[[0,0,368,513,1698]],[[0,0,368,513,1701]],[[0,0,368,513,1704]],[[0,0,368,513,1707]],[[0,0,368,513,1710]],[[0,0,368,513,1713]],[[0,0,368,513,1716]],[[0,0,368,513,1719]],[[0,0,368,513,1722]],[[0,0,368,513,1725]],[[0,0,368,513,1728]],[[0,0,368,513,1731]],[[0,0,368,513,1734]],[[0,0,368,513,1737]],[[0,0,368,513,1740]],[[0,0,368,513,1743]],[[0,0,368,513,1746]],[[0,0,368,513,1749]],[[0,0,368,513,1752]],[[0,0,368,513,1755]],[[0,0,368,513,1758]],[[0,0,368,513,1761]],[[0,0,368,513,1764]],[[0,0,368,513,1767]],[[0,0,368,513,1770]],[[0,0,368,513,1773]],[[0,0,368,513,1776]],[[0,0,368,513,1779]],[[0,0,368,513,1782]],[[0,0,368,513,1785]],[[0,0,368,513,1788]],[[0,0,368,513,1791]],[[0,0,368,513,1794]],[[0,0,368,513,1797]],[[0,0,368,513,1800]],[[0,0,368,513,1803]],[[0,0,368,513,1806]],[[0,0,368,513,1809]],[[0,0,368,513,1812]],[[0,0,368,513,1815]],[[0,0,368,513,1818]],[[0,0,368,513,1821]],[[0,0,368,513,1824]],[[0,0,368,513,1827]],[[0,0,368,513,1830]],[[0,0,368,513,1833]],[[0,0,368,513,1836]],[[0,0,368,513,1839]],[[0,0,368,513,1842]],[[0,0,368,513,1845]],[[0,0,368,513,1848]],[[0,0,368,513,1851]],[[0,0,368,513,1854]],[[0,0,368,513,1857]],[[0,0,368,513,1860]],[[0,0,368,513,1863]],[[0,0,368,513,1866]],[[0,0,368,513,1869]],[[0,0,368,513,1872]],[[0,0,368,513,1875]],[[0,0,368,513,1878]],[[0,0,368,513,1881]],[[0,0,368,513,1884]],[[0,0,368,513,1887]],[[0,0,368,513,1890]],[[0,0,368,513,1893]],[[0,0,368,513,1896]],[[0,0,368,513,1899]],[[0,0,368,513,1902]],[[0,0,368,513,1905]],[[0,0,368,513,1908]],[[0,0,368,513,1911]],[[0,0,368,513,1914]],[[0,0,368,513,1917]],[[0,0,368,513,1920]],[[0,0,368,513,1923]],[[0,0,368,513,1926]],[[0,0,368,513,1929]],[[0,0,368,513,1932]],[[0,0,368,513,1935]],[[0,0,368,513,1938]],[[0,0,368,513,1941]],[[0,0,368,513,1944]],[[0,0,368,513,1947]],[[0,0,368,513,1950]],[[0,0,368,513,1953]],[[0,0,368,513,1956]],[[0,0,368,513,1959]],[[0,0,368,513,1962]],[[0,0,368,513,1965]],[[0,0,368,513,1968]],[[0,0,368,513,1971]],[[0,0,368,513,1974]],[[0,0,368,513,1977]],[[0,0,368,513,1980]],[[0,0,368,513,1983]],[[0,0,368,513,1986]],[[0,0,368,513,1989]],[[0,0,368,513,1992]],[[0,0,368,513,1995]],[[0,0,368,513,1998]],[[0,0,368,513,2001]],[[0,0,368,513,2004]],[[0,0,368,513,2007]],[[0,0,368,513,2010]],[[0,0,368,513,2013]],[[0,0,368,513,2016]],[[0,0,368,513,2019]],[[0,0,368,513,2022]],[[0,0,368,513,2025]],[[0,0,368,513,2028]],[[0,0,368,513,2031]],[[0,0,368,513,2034]],[[0,0,368,513,2037]],[[0,0,368,513,2040]],[[0,0,368,513,2043]],[[0,0,368,513,2046]],[[0,0,368,513,2049]],[[0,0,368,513,2052]],[[0,0,368,513,2055]],[[0,0,368,513,2058]],[[0,0,368,513,2061]],[[0,0,368,513,2064]],[[0,0,368,513,2067]],[[0,0,368,513,2070]],[[0,0,368,513,2073]],[[0,0,368,513,2076]],[[0,0,368,513,2079]],[[0,0,368,513,2082]],[[0,0,368,513,2085]],[[0,0,368,513,2088]],[[0,0,368,513,2091]],[[0,0,368,513,2094]],[[0,0,368,513,2097]],[[0,0,368,513,2100]],[[0,0,368,513,2103]],[[0,0,368,513,2106]],[[0,0,368,513,2109]],[[0,0,368,513,2112]],[[0,0,368,513,2115]],[[0,0,368,513,2118]],[[0,0,368,513,2121]],[[0,0,368,513,2124]],[[0,0,368,513,2127]],[[0,0,368,513,2130]],[[0,0,368,513,2133]],[[0,0,368,513,2136]],[[0,0,368,513,2139]],[[0,0,368,513,2142]],[[0,0,368,513,2145]],[[0,0,368,513,2148]],[[0,0,368,513,2151]],[[0,0,368,513,2154]],[[0,0,368,513,2157]],[[0,0,368,513,2160]],[[0,0,368,513,2163]],[[0,0,368,513,2166]],[[0,0,368,513,2169]],[[0,0,368,513,2172]],[[0,0,368,513,2175]],[[0,0,368,513,2178]],[[0,0,368,513,2181]],[[0,0,368,513,2184]],[[0,0,368,513,2187]],[[0,0,368,513,2190]],[[0,0,368,513,2193]],[[0,0,368,513,2196]],[[0,0,368,513,2199]],[[0,0,368,513,2202]],[[0,0,368,513,2205]],[[0,0,368,513,2208]],[[0,0,368,513,2211]],[[0,0,368,513,2214]],[[0,0,368,513,2217]],[[0,0,368,513,2220]],[[0,0,368,513,2223]],[[0,0,368,513,2226]],[[0,0,368,513,2229]],[[0,0,368,513,2232]],[[0,0,368,513,2235]],[[0,0,368,513,2238]],[[0,0,368,513,2241]],[[0,0,368,513,2244]],[[0,0,368,513,2247]],[[0,0,368,513,2250]],[[0,0,368,513,2253]],[[0,0,368,513,2256]],[[0,0,368,513,2259]],[[0,0,368,513,2262]],[[0,0,368,513,2265]],[[0,0,368,513,2268]],[[0,0,368,513,2271]],[[0,0,368,513,2274]],[[0,0,368,513,2277]],[[0,0,368,513,2280]],[[0,0,368,513,2283]],[[0,0,368,513,2286]],[[0,0,368,513,2289]],[[0,0,368,513,2292]],[[0,0,368,513,2295]],[[0,0,368,513,2298]],[[0,0,368,513,2301]],[[0,0,368,513,2304]],[[0,0,368,513,2307]],[[0,0,368,513,2310]],[[0,0,368,513,2313]],[[0,0,368,513,2316]],[[0,0,368,513,2319]],[[0,0,368,513,2322]],[[0,0,368,513,2325]],[[0,0,368,513,2328]],[[0,0,368,513,2331]],[[0,0,368,513,2334]],[[0,0,368,513,2337]],[[0,0,368,513,2340]],[[0,0,368,513,2343]],[[0,0,368,513,2346]],[[0,0,368,513,2349]],[[0,0,368,513,2352]],[[0,0,368,513,2355]],[[0,0,368,513,2358]],[[0,0,368,513,2361]],[[0,0,368,513,2364]],[[0,0,368,513,2367]],[[0,0,368,513,2370]],[[0,0,368,513,2373]],[[0,0,368,513,2376]],[[0,0,368,513,2379]],[[0,0,368,513,2382]],[[0,0,368,513,2385]],[[0,0,368,513,2388]],[[0,0,368,513,2391]],[[0,0,368,513,2394]],[[0,0,368,513,2397]],[[0,0,368,513,2400]],[[0,0,368,513,2403]],[[0,0,368,513,2406]],[[0,0,368,513,2409]],[[0,0,368,513,2412]],[[0,0,368,513,2415]],[[0,0,368,513,2418]],[[0,0,368,513,2421]],[[0,0,368,513,2424]],[[0,0,368,513,2427]],[[0,0,368,513,2430]],[[0,0,368,513,2433]],[[0,0,368,513,2436]],[[0,0,368,513,2439]],[[0,0,368,513,2442]],[[0,0,368,513,2445]],[[0,0,368,513,2448]],[[0,0,368,513,2451]],[[0,0,368,513,2454]],[[0,0,368,513,2457]],[[0,0,368,513,2460]],[[0,0,368,513,2463]],[[0,0,368,513,2466]],[[0,0,368,513,2469]],[[0,0,368,513,2472]],[[0,0,368,513,2475]],[[0,0,368,513,2478]],[[0,0,368,513,2481]],[[0,0,368,513,2484]],[[0,0,368,513,2487]],[[0,0,368,513,2490]],[[0,0,368,513,2493]],[[0,0,368,513,2496]],[[0,0,368,513,2499]],[[0,0,368,513,2502]],[[0,0,368,513,2505]],[[0,0,368,513,2508]],[[0,0,368,513,2511]],[[0,0,368,513,2514]],[[0,0,368,513,2517]],[[0,0,368,513,2520]],[[0,0,368,513,2523]],[[0,0,368,513,2526]],[[0,0,368,513,2529]],[[0,0,368,513,2532]],[[0,0,368,513,2535]],[[0,0,368,513,2538]],[[0,0,368,513,2541]],[[0,0,368,513,2544]],[[0,0,368,513,2547]],[[0,0,368,513,2550]],[[0,0,368,513,2553]],[[0,0,368,513,2556]],[[0,0,368,513,2559]],[[0,0,368,513,2562]],[[0,0,368,513,2565]],[[0,0,368,513,2568]],[[0,0,368,513,2571]],[[0,0,368,513,2574]],[[0,0,368,513,2577]],[[0,0,368,513,2580]],[[0,0,368,513,2583]],[[0,0,368,513,2586]],[[0,0,368,513,2589]],[[0,0,368,513,2592]],[[0,0,368,513,2595]],[[0,0,368,513,2598]],[[0,0,368,513,2601]],[[0,0,368,513,2604]],[[0,0,368,513,2607]],[[0,0,368,513,2610]],[[0,0,368,513,2613]],[[0,0,368,513,2616]],[[0,0,368,513,2619]],[[0,0,368,513,2622]],[[0,0,368,513,2625]],[[0,0,368,513,2628]],[[0,0,368,513,2631]],[[0,0,368,513,2634]],[[0,0,368,513,2637]],[[0,0,368,513,2640]],[[0,0,368,513,2643]],[[0,0,368,513,2646]],[[0,0,368,513,2649]],[[0,0,368,513,2652]],[[0,0,368,513,2655]],[[0,0,368,513,2658]],[[0,0,368,513,2661]],[[0,0,368,513,2664]],[[0,0,368,513,2667]],[[0,0,368,513,2670]],[[0,0,368,513,2673]],[[0,0,368,513,2676]],[[0,0,368,513,2679]],[[0,0,368,513,2682]],[[0,0,368,513,2685]],[[0,0,368,513,2688]],[[0,0,368,513,2691]],[[0,0,368,513,2694]],[[0,0,368,513,2697]],[[0,0,368,513,2700]],[[0,0,368,513,2703]],[[0,0,368,513,2706]],[[0,0,368,513,2709]],[[0,0,368,513,2712]],[[0,0,368,513,2715]],[[0,0,368,513,2718]],[[0,0,368,513,2721]],[[0,0,368,513,2724]],[[0,0,368,513,2727]],[[0,0,368,513,2730]],[[0,0,368,513,2733]],[[0,0,368,513,2736]],[[0,0,368,513,2739]],[[0,0,368,513,2742]],[[0,0,368,513,2745]],[[0,0,368,513,2748]],[[0,0,368,513,2751]],[[0,0,368,513,2754]],[[0,0,368,513,2757]],[[0,0,368,513,2760]],[[0,0,368,513,2763]],[[0,0,368,513,2766]],[[0,0,368,513,2769]],[[0,0,368,513,2772]],[[0,0,368,513,2775]],[[0,0,368,513,2778]],[[0,0,368,513,2781]],[[0,0,368,513,2784]],[[0,0,368,513,2787]],[[0,0,368,513,2790]],[[0,0,368,513,2793]],[[0,0,368,513,2796]]],"text_len_per_page":[53,53,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54,54],"metadata":{"format":"PDF 1.6","title":"","author":"","subject":"","keywords":"","creator":"Adobe Acrobat 7.0","producer":"Adobe Acrobat 7.0 Image Conversion Plug-in","creationDate":"D:20080404141457+01'00'","modDate":"D:20080404144821+01'00'","trapped":"","encryption":null}}
    o = json.loads(json.dumps(o))
    total_page = o["total_page"]
    page_width = o["page_width_pts"]
    page_height = o["page_height_pts"]
    img_sz_list = o["image_info_per_page"]
    text_len_list = o['text_len_per_page']
    pdf_path = o['pdf_path']
    is_encrypted = o['is_encrypted']
    is_needs_password = o['is_needs_password']
    if is_encrypted or total_page == 0 or is_needs_password:  # 加密的，需要密码的，没有页面的，都不处理
        print("加密的")
        exit(0)
    tag = classify(pdf_path, total_page, page_width, page_height, img_sz_list, text_len_list)
    o['is_text_pdf'] = tag
    print(json.dumps(o, ensure_ascii=False))
    