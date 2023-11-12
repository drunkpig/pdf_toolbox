import os                   
import collections      # 统计库
import re               # 正则
import fitz             # pyMuPDF库
import json             # json


def parse_equations(page_ID: int, page: fitz.Page, res_dir_path: str, json_from_DocXchain: str, exclude_bboxes):
    """
    :param page_ID: int类型，当前page在当前pdf文档中是第page_D页。
    :param page :fitz读取的当前页的内容
    :param res_dir_path: str类型，是每一个pdf文档，在当前.py文件的目录下生成一个与pdf文档同名的文件夹，res_dir_path就是文件夹的dir
    :param json_from_DocXchain:str类型，把pdf文档送入DocXChain模型中后，提取bbox，结果保存到pdf文档同名文件夹下的 page_ID.json文件中了
    """
    page_artbox = page.artbox
    pageL, pageU, pageR, pageD = page_artbox[0], page_artbox[1], page_artbox[2], page_artbox[3]
    

    #--------- 通过json_from_DocXchain来获取 table ---------#
    equationEmbedding_from_DocXChain_bboxs = []
    equationIsolated_from_DocXChain_bboxs = []
    
    xf_json = json_from_DocXchain
    width_from_json = xf_json['page_info']['width']
    height_from_json = xf_json['page_info']['height']
    LR_scaleRatio = width_from_json / (pageR - pageL)
    UD_scaleRatio = height_from_json / (pageD - pageU)
    
    for xf in xf_json['layout_dets']:
    # {0: 'title', 1: 'figure', 2: 'plain text', 3: 'header', 4: 'page number', 5: 'footnote', 6: 'footer', 7: 'table', 8: 'table caption', 9: 'figure caption', 10: 'equation', 11: 'full column', 12: 'sub column'}
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
        # equation
        if xf['category_id'] == 13 and xf['score'] >= 0.3:
            equationEmbedding_from_DocXChain_bboxs.append((L, U, R, D))
        if xf['category_id'] == 14 and xf['score'] >= 0.3:
            equationIsolated_from_DocXChain_bboxs.append((L, U, R, D))
        
        
    
    #---------------------------------------- 排序，编号，保存 -----------------------------------------#
    equationIsolated_from_DocXChain_bboxs.sort(key = lambda LURD: (LURD[1], LURD[0]))
    equationIsolated_from_DocXChain_bboxs.sort(key = lambda LURD: (LURD[1], LURD[0]))
    
    equationEmbedding_from_DocXChain_names = []
    equationEmbedding_ID = 0
    
    equationIsolated_from_DocXChain_names = []
    equationIsolated_ID = 0
    
    for L, U, R, D in equationEmbedding_from_DocXChain_bboxs:
        if not(L < R and U < D):
            continue
        try:
            # cur_equation = page.get_pixmap(clip=(L,U,R,D))
            new_equation_name = "equationEmbedding_{}_{}.png".format(page_ID, equationEmbedding_ID)        # 公式name
            # cur_equation.save(res_dir_path + '/' + new_equation_name)                       # 把公式存出在新建的文件夹，并命名
            equationEmbedding_from_DocXChain_names.append(new_equation_name)                         # 把公式的名字存在list中，方便在md中插入引用
            equationEmbedding_ID += 1
        except:
            pass

    for L, U, R, D in equationIsolated_from_DocXChain_bboxs:
        if not(L < R and U < D):
            continue
        try:
            # cur_equation = page.get_pixmap(clip=(L,U,R,D))
            new_equation_name = "equationEmbedding_{}_{}.png".format(page_ID, equationIsolated_ID)        # 公式name
            # cur_equation.save(res_dir_path + '/' + new_equation_name)                       # 把公式存出在新建的文件夹，并命名
            equationIsolated_from_DocXChain_names.append(new_equation_name)                         # 把公式的名字存在list中，方便在md中插入引用
            equationIsolated_ID += 1
        except:
            pass
            
    equationEmbedding_from_DocXChain_bboxs.sort(key = lambda LURD: (LURD[1], LURD[0]))
    equationIsolated_from_DocXChain_bboxs.sort(key = lambda LURD: (LURD[1], LURD[0])) 
    return equationEmbedding_from_DocXChain_bboxs, equationIsolated_from_DocXChain_bboxs
