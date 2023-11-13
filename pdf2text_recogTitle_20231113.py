import os                   
import collections      # 统计库
import re               # 正则
import fitz             # pyMuPDF库
import json             # json


def parse_titles(page_ID: int, page: fitz.Page, res_dir_path: str, json_from_DocXchain_dir: str, exclude_bboxes):
    """
    :param page_ID: int类型，当前page在当前pdf文档中是第page_D页。
    :param page :fitz读取的当前页的内容
    :param res_dir_path: str类型，是每一个pdf文档，在当前.py文件的目录下生成一个与pdf文档同名的文件夹，res_dir_path就是文件夹的dir
    :param json_from_DocXchain_dir:str类型，把pdf文档送入DocXChain模型中后，提取bbox，结果保存到pdf文档同名文件夹下的 page_ID.json文件中了。json_from_DocXchain_dir就是该文件夹的dir
    """
    page_artbox = page.artbox
    pageL, pageU, pageR, pageD = page_artbox[0], page_artbox[1], page_artbox[2], page_artbox[3]
    

    #--------- 通过json_from_DocXchain来获取 title ---------#
    title_bbox_from_DocXChain = []

    
    with open(json_from_DocXchain_dir + f'/{page_ID}.json', 'r') as f:
        xf_json = json.load(f)
    width_from_json = xf_json['page_info']['width']
    height_from_json = xf_json['page_info']['height']
    LR_scaleRatio = width_from_json / (pageR - pageL)
    UD_scaleRatio = height_from_json / (pageD - pageU)

    
    for xf in xf_json['layout_dets']:
    # {0: 'title', 1: 'figure', 2: 'plain text', 3: 'header', 4: 'page number', 5: 'footnote', 6: 'footer', 7: 'table', 8: 'table caption', 9: 'figure caption', 10: 'equation', 11: 'full column', 12: 'sub column'}
    #  13: 'embedding',     # 嵌入公式
    #  14: 'isolated'}      # 单行公式
        L = xf['poly'][0] / LR_scaleRatio
        U = xf['poly'][1] / UD_scaleRatio
        R = xf['poly'][2] / LR_scaleRatio
        D = xf['poly'][5] / UD_scaleRatio
        L += pageL          # 有的页面，artBox偏移了。不在（0,0）
        R += pageL
        U += pageU
        D += pageU
        L, R = min(L, R), max(L, R)
        U, D = min(U, D), max(U, D)
        if xf['category_id'] == 0 and xf['score'] >= 0.3:
            title_bbox_from_DocXChain.append((L, U, R, D))
            
    
    title_final_names = []
    title_final_bboxs = []
    title_ID = 0
    for L, U, R, D in title_bbox_from_DocXChain:
        # cur_title = page.get_pixmap(clip=(L,U,R,D))
        new_title_name = "title_{}_{}.png".format(page_ID, title_ID)    # 标题name
        # cur_title.save(res_dir_path + '/' + new_title_name)           # 把标题存储在新建的文件夹，并命名
        title_final_names.append(new_title_name)                        # 把标题的名字存在list中
        title_final_bboxs.append((L, U, R, D))
        title_ID += 1
        

    title_final_bboxs.sort(key = lambda LURD: (LURD[1], LURD[0]))
    curPage_all_title_bboxs = title_final_bboxs
    return curPage_all_title_bboxs

