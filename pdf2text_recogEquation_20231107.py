import os                   
import collections      # 统计库
import re               # 正则
import fitz             # pyMuPDF库
import json             # json



def parse_equations(page_ID: int, page: fitz.Page, res_dir_path: str, json_from_DocXchain_dir: str, exclude_bboxes):
    """
    :param page_ID: int类型，当前page在当前pdf文档中是第page_D页。
    :param page :fitz读取的当前页的内容
    :param res_dir_path: str类型，是每一个pdf文档，在当前.py文件的目录下生成一个与pdf文档同名的文件夹，res_dir_path就是文件夹的dir
    :param json_from_DocXchain_dir:str类型，把pdf文档送入DocXChain模型中后，提取bbox，结果保存到pdf文档同名文件夹下的 page_ID.json文件中了。json_from_DocXchain_dir就是该文件夹的dir
    """
    page_artbox = page.artbox
    pageL, pageU, pageR, pageD = page_artbox[0], page_artbox[1], page_artbox[2], page_artbox[3]
    

    #--------- 通过json_from_DocXchain来获取 table ---------#
    equation_bbox_from_DocXChain = []
    
    
    with open(json_from_DocXchain_dir + f'/{page_ID}.json', 'r') as f:
        xf_json = json.load(f)
    width_from_json = xf_json['page_info']['width']
    height_from_json = xf_json['page_info']['height']
    LR_scaleRatio = width_from_json / (pageR - pageL)
    UD_scaleRatio = height_from_json / (pageD - pageU)
    
    for xf in xf_json['layout_dets']:
    # {0: 'title', 1: 'figure', 2: 'plain text', 3: 'header', 4: 'page number', 5: 'footnote', 6: 'footer', 7: 'table', 8: 'table caption', 9: 'figure caption', 10: 'equation', 11: 'full column', 12: 'sub column'}
        L = xf['poly'][0] / LR_scaleRatio
        U = xf['poly'][1] / LR_scaleRatio
        R = xf['poly'][2] / UD_scaleRatio
        D = xf['poly'][5] / UD_scaleRatio
        L += pageL          # 有的页面，artBox偏移了。不在（0,0）
        R += pageL
        U += pageU
        D += pageU
        L, R = min(L, R), max(L, R)
        U, D = min(U, D), max(U, D)
        # equation
        if xf['category_id'] == 10 and xf['score'] >= 0.3:
            equation_bbox_from_DocXChain.append((L, U, R, D))
        
        
    equation_from_DocXChain_names = []
    equation_from_DocXChain_bboxs = []
    equation_ID = 0
    for L, U, R, D in equation_bbox_from_DocXChain:
        if not(L < R and U < D):
            continue
        try:
            cur_equation = page.get_pixmap(clip=(L,U,R,D))
            new_equation_name = "equation_{}_{}.png".format(page_ID, equation_ID)        # 公式name
            cur_equation.save(res_dir_path + '/' + new_equation_name)                       # 把公式存出在新建的文件夹，并命名
            equation_from_DocXChain_names.append(new_equation_name)                         # 把公式的名字存在list中，方便在md中插入引用
            equation_from_DocXChain_bboxs.append((L, U, R, D))
            equation_ID += 1
        except:
            pass


    curPage_all_equation_bboxs = equation_from_DocXChain_bboxs
    return curPage_all_equation_bboxs

