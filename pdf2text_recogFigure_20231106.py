import os                   
import collections      # 统计库
import re               # 正则
import fitz             # pyMuPDF库
import json             # json


#--------------------------------------- Tool Functions --------------------------------------#
# 正则化，输入文本，输出只保留a-z,A-Z,0-9
def remove_special_chars(s: str) -> str:
    pattern = r"[^a-zA-Z0-9]"
    res = re.sub(pattern, "", s)
    return res

def check_rect1_sameWith_rect2(L1: float, U1: float, R1: float, D1: float, L2: float, U2: float, R2: float, D2: float) -> bool:
    # 判断rect1和rect2是否一模一样
    return L1 == L2 and U1 == U2 and R1 == R2 and D1 == D2

def check_rect1_contains_rect2(L1: float, U1: float, R1: float, D1: float, L2: float, U2: float, R2: float, D2: float) -> bool:
    # 判断rect1包含了rect2
    return (L1 <= L2 <= R2 <= R1) and (U1 <= U2 <= D2 <= D1)

def check_rect1_overlaps_rect2(L1: float, U1: float, R1: float, D1: float, L2: float, U2: float, R2: float, D2: float) -> bool:
    # 判断rect1与rect2是否存在重叠（只有一条边重叠，也算重叠）
    return max(L1, L2) <= min(R1, R2) and max(U1, U2) <= min(D1, D2)

def calculate_overlapRatio_between_rect1_and_rect2(L1: float, U1: float, R1: float, D1: float, L2: float, U2: float, R2: float, D2: float) -> (float, float):
    # 计算两个rect，重叠面积各占2个rect面积的比例
    if min(R1, R2) < max(L1, L2) or min(D1, D2) < max(U1, U2):
        return 0, 0
    square_1 = (R1 - L1) * (D1 - U1)
    square_2 = (R2 - L2) * (D2 - U2)
    if square_1 == 0 or square_2 == 0:
        return 0, 0
    square_overlap = (min(R1, R2) - max(L1, L2)) * (min(D1, D2) - max(U1, U2))
    return square_overlap / square_1, square_overlap / square_2

def calculate_overlapRatio_between_line1_and_line2(L1: float, R1: float, L2: float, R2: float) -> (float, float):
    # 计算两个rect，重叠面积各占2个rect面积的比例
    if max(L1, L2) > min(R1, R2):
        return 0, 0
    if L1 == R1 or L2 == R2:
        return 0, 0
    overlap_line = min(R1, R2) - max(L1, L2)
    return overlap_line / (R1 - L1), overlap_line / (R2 - L2)


# 判断rect其实是一条line
def check_rect_isLine(L: float, U: float, R: float, D: float) -> bool:
    width = R - L
    height = D - U
    if width <= 3 or height <= 3:
        return True
    if width / height >= 30 or height / width >= 30:
        return True



def parse_images(page_ID: int, page: fitz.Page, res_dir_path: str, json_from_DocXchain_dir: str, exclude_bboxes):
    """
    :param page_ID: int类型，当前page在当前pdf文档中是第page_D页。
    :param res_dir_path: str类型，是每一个pdf文档，在当前.py文件的目录下生成一个与pdf文档同名的文件夹，res_dir_path就是文件夹的dir
    :param json_from_DocXchain_dir:str类型，把pdf文档送入DocXChain模型中后，提取bbox，结果保存到pdf文档同名文件夹下的 page_ID.json文件中了。json_from_DocXchain_dir就是该文件夹的dir
    :return figures的bboxs, []
    """
    #### 通过fitz获取page信息
    
    #----------------- 保存每一个文本块的LURD ------------------#
    textLine_blocks = []
    blocks = page.get_text(
            "dict",
            flags=fitz.TEXTFLAGS_TEXT,
            #clip=clip,
        )["blocks"]
    for i in range(len(blocks)):
        bbox = blocks[i]['bbox']
        # print(bbox)
        for tt in blocks[i]['lines']:
            # 当前line
            cur_line_bbox = None                            # 当前line，最右侧的section的bbox
            for xf in tt['spans']:
                L, U, R, D = xf['bbox']
                L, R = min(L, R), max(L, R)
                U, D = min(U, D), max(U, D)
                textLine_blocks.append((L, U, R, D))
    textLine_blocks.sort(key = lambda LURD: (LURD[1], LURD[0]))
    

    #---------------------------------------------- 保存img --------------------------------------------------#
    imgs = page.get_images()                    # 获取所有的图片
    img_names = []                              # 保存图片的名字，方便在md中插入引用
    img_bboxs = []                              # 保存图片的location信息。
    img_visited = [] # 记忆化，记录该图片是否在md中已经插入过了

    ## 获取、保存每张img的location信息(x1, y1, x2, y2， UL, DR坐标)
    tmp_list = []
    for i in range(len(imgs)):
        try:
            tt = page.get_image_rects(imgs[i][0])
            L, U, R, D = tt[0][0], tt[0][1], tt[0][2], tt[0][3]
            L, R = min(L, R), max(L, R)
            U, D = min(U, D), max(U, D)
            img_bboxs.append([L, U, R, D])
            img_visited.append(False)
            tmp_list.append(imgs[i])
        except:
            continue
    imgs = tmp_list

    ## 获取、存储每张img
    img_bad_idxs = []
    for i in range(len(imgs)):
        try:
            # img = page.extract_image(imgs[i][0])
            # pix1 = fitz.Pixmap(img['image'])
            new_img_name = "{}_{}.png".format(page_ID, i)      # 图片name
            # pix1.save(res_dir_path + '/' + new_img_name)        # 把图片存出在新建的文件夹，并命名
            img_names.append(new_img_name)                      # 把图片的名字存在list中，方便在md中插入引用
        except:
            img_bad_idxs.append(i)

    for bad_i in img_bad_idxs[::-1]:
        imgs = imgs[ :bad_i] + imgs[bad_i + 1: ]
        img_bboxs = img_bboxs[ :bad_i] + img_bboxs[bad_i + 1: ]
        img_visited = img_visited[ :bad_i] + img_visited[bad_i + 1: ]
        
    #---------------------------------------- 通过fitz提取svg的信息 -----------------------------------------#
    #
    svgs = page.get_drawings()
    #------------ preprocess, check一些大框，看是否是合理的 ----------#
    ## 去重。有时候会遇到rect1和rect2是完全一样的情形。
    svg_rect_visited = set()
    available_svgIdx = []
    for i in range(len(svgs)):
        L, U, R, D = svgs[i]['rect'].irect
        L, R = min(L, R), max(L, R)
        U, D = min(U, D), max(U, D)
        tt = (L, U, R, D)
        if tt not in svg_rect_visited:
            svg_rect_visited.add(tt)
            available_svgIdx.append(i)
        
    svgs = [svgs[i] for i in available_svgIdx]                  # 去重后，有效的svgs
    svg_childs = [[] for _ in range(len(svgs))]
    svg_parents = [[] for _ in range(len(svgs))]
    svg_overlaps = [[] for _ in range(len(svgs))]            #svg_overlaps[i]是一个list，存的是与svg_i有重叠的svg的index。e.g., svg_overlaps[0] = [1, 2, 7, 9]
    svg_visited = [False for _ in range(len(svgs))]
    svg_exceedPage = [0 for _ in range(len(svgs))]       # 是否超越边界（artbox），很大，但一般是一个svg的底。  
        
    ## 超越边界
    page_artbox = page.artbox
    pageL, pageU, pageR, pageD = page_artbox[0], page_artbox[1], page_artbox[2], page_artbox[3]
    for i in range(len(svgs)):
        L, U, R, D = svgs[i]['rect'].irect
        ratio_1, ratio_2 = calculate_overlapRatio_between_rect1_and_rect2(L, U, R, D, pageL, pageU, pageR, pageD)
        if pageL < L <= R < pageR and pageU < U <= D < pageD:
            if ratio_2 >= 0.7:
                svg_exceedPage[i] += 4
        else:
            if L <= pageL:
                svg_exceedPage[i] += 1
            if pageR <= R:
                svg_exceedPage[i] += 1
            if U <= pageU:
                svg_exceedPage[i] += 1
            if pageD <= D:
                svg_exceedPage[i] += 1
            
    #---------------------------- build graph ----------------------------#
    for i, p in enumerate(svgs):
        L1, U1, R1, D1 = svgs[i]["rect"].irect
        for j in range(len(svgs)):
            if i == j:
                continue
            L2, U2, R2, D2 = svgs[j]["rect"].irect
            ## 包含
            if check_rect1_contains_rect2(L1, U1, R1, D1, L2, U2, R2, D2) == True:
                svg_childs[i].append(j)
                svg_parents[j].append(i)
            else:
                ## 交叉
                if check_rect1_overlaps_rect2(L1, U1, R1, D1, L2, U2, R2, D2) == True:
                    svg_overlaps[i].append(j)

    #---------------- 确定最终的svg。连通块儿的外围 -------------------#
    eps_ERROR = 5                      # 给识别出的svg，四周留白（为了防止pyMuPDF的rect不准）
    svg_ID = 0        
    svg_final_names = []
    svg_final_bboxs = []
    svg_final_visited = []              # 为下面，text识别左准备。作用同img_visited
    
    svg_idxs = [i for i in range(len(svgs))]
    svg_idxs.sort(key = lambda i: -(svgs[i]['rect'].irect[2] - svgs[i]['rect'].irect[0]) * (svgs[i]['rect'].irect[3] - svgs[i]['rect'].irect[1]))   # 按照面积，从大到小排序
     
    for i in svg_idxs:
        if svg_visited[i] == True:
            continue
        svg_visited[i] = True
        L, U, R, D = svgs[i]['rect'].irect
        width = R - L
        height = D - U
        if check_rect_isLine(L, U, R, D) == True:
            svg_visited[i] = False
            continue
        # if i == 4:
        #     print(i, L, U, R, D)
        #     print(svg_parents[i])
        
        cur_block_element_cnt = 0               # 当前要判定为svg的区域中，有多少elements，最外围的最大svg框除外。
        if len(svg_parents[i]) == 0:
            ## 是个普通框的情形
            cur_block_element_cnt += len(svg_childs[i])
            if svg_exceedPage[i] == 0:
                ## 误差。可能已经包含在某个框里面了
                neglect_flag = False
                for pL, pU, pR, pD in svg_final_bboxs:
                    if pL <= L <= R <= pR and pU <= U <= D <= pD:
                        neglect_flag = True
                        break
                if neglect_flag == True:
                    continue
                
                ## 搜索连通域, bfs+记忆化
                q = collections.deque()
                for j in svg_overlaps[i]:
                    q.append(j)
                while q:
                    j = q.popleft()
                    svg_visited[j] = True
                    L2, U2, R2, D2 = svgs[j]['rect'].irect
                    # width2 = R2 - L2
                    # height2 = D2 - U2
                    # if width2 <= 2 or height2 <= 2 or (height2 / width2) >= 30 or (width2 / height2) >= 30:
                    #     continue
                    L = min(L, L2)
                    R = max(R, R2)
                    U = min(U, U2)
                    D = max(D, D2)
                    cur_block_element_cnt += 1
                    cur_block_element_cnt += len(svg_childs[j])
                    for k in svg_overlaps[j]:
                        if svg_visited[k] == False and svg_exceedPage[k] == 0:
                            svg_visited[k] = True
                            q.append(k)
            elif svg_exceedPage[i] <= 2:
                ## 误差。可能已经包含在某个svg_final_bbox框里面了
                neglect_flag = False
                for sL, sU, sR, sD in svg_final_bboxs:
                    if sL <= L <= R <= sR and sU <= U <= D <= sD:
                        neglect_flag = True
                        break
                if neglect_flag == True:
                    continue
                
                L, U, R, D = pageR, pageD, pageL, pageU
                ## 所有孩子元素的最大边界
                for j in svg_childs[i]:
                    if svg_visited[j] == True:
                        continue
                    svg_visited[j] = True
                    L2, U2, R2, D2 = svgs[j]['rect'].irect
                    L = min(L, L2)
                    R = max(R, R2)
                    U = min(U, U2)
                    D = max(D, D2)
                    cur_block_element_cnt += 1
                    
            # 如果是条line，就不用保存了
            if check_rect_isLine(L, U, R, D) == True:
                continue
            # 如果当前的svg，连2个elements都没有，就不用保存了
            if cur_block_element_cnt < 3:
                continue
            
            ## 当前svg，框住了多少文本框。如果框多了，可能就是错了
            contain_textLineBlock_cnt = 0
            for L2, U2, R2, D2 in textLine_blocks:
                if check_rect1_contains_rect2(L, U, R, D, L2, U2, R2, D2) == True:
                    contain_textLineBlock_cnt += 1
            if contain_textLineBlock_cnt >= 10:
                continue
            
            # L -= eps_ERROR * 2
            # U -= eps_ERROR
            # R += eps_ERROR * 2
            # D += eps_ERROR

            # cur_svg = page.get_pixmap(clip=(L,U,R,D))
            new_svg_name = "svg_{}_{}.png".format(page_ID, svg_ID)      # 图片name
            # cur_svg.save(res_dir_path + '/' + new_svg_name)        # 把图片存出在新建的文件夹，并命名
            svg_final_names.append(new_svg_name)                      # 把图片的名字存在list中，方便在md中插入引用
            svg_final_bboxs.append((L, U, R, D))
            svg_final_visited.append(False)
            svg_ID += 1
    
    ## 识别出的svg，可能有 包含，相邻的情形。需要进一步合并
    svg_idxs = [i for i in range(len(svg_final_bboxs))]
    svg_idxs.sort(key = lambda i: (svg_final_bboxs[i][1], svg_final_bboxs[i][0]))   # (U, L)
    svg_final_names_2 = []
    svg_final_bboxs_2 = []
    svg_final_visited_2 = []              # 为下面，text识别左准备。作用同img_visited
    svg_ID_2 = 0
    for i in range(len(svg_final_bboxs)):
        L1, U1, R1, D1 = svg_final_bboxs[i]
        for j in range(i + 1, len(svg_final_bboxs)):
            L2, U2, R2, D2 = svg_final_bboxs[j]
            # 如果 rect1包含了rect2
            if check_rect1_contains_rect2(L1, U1, R1, D1, L2, U2, R2, D2) == True:
                svg_final_visited[j] = True
                continue
            # 水平并列
            ratio_1, ratio_2 = calculate_overlapRatio_between_line1_and_line2(U1, D1, U2, D2)
            if ratio_1 >= 0.7 and ratio_2 >= 0.7:
                if abs(L2 - R1) >= 20:
                    continue
                LL = min(L1, L2)
                UU = min(U1, U2)
                RR = max(R1, R2)
                DD = max(D1, D2)
                svg_final_bboxs[i] = (LL, UU, RR, DD)
                svg_final_visited[j] = True
                continue
            # 竖直并列
            ratio_1, ratio_2 = calculate_overlapRatio_between_line1_and_line2(L1, R2, L2, R2)
            if ratio_1 >= 0.7 and ratio_2 >= 0.7:
                if abs(U2 - D1) >= 20:
                    continue
                LL = min(L1, L2)
                UU = min(U1, U2)
                RR = max(R1, R2)
                DD = max(D1, D2)
                svg_final_bboxs[i] = (LL, UU, RR, DD)
                svg_final_visited[j] = True
    
    for i in range(len(svg_final_bboxs)):
        if svg_final_visited[i] == False:
            L, U, R, D = svg_final_bboxs[i]
            svg_final_bboxs_2.append((L, U, R, D))
            
            L -= eps_ERROR * 2
            U -= eps_ERROR
            R += eps_ERROR * 2
            D += eps_ERROR
            # cur_svg = page.get_pixmap(clip=(L,U,R,D))
            new_svg_name = "svg_{}_{}.png".format(page_ID, svg_ID_2)      # 图片name
            # cur_svg.save(res_dir_path + '/' + new_svg_name)           # 把图片存出在新建的文件夹，并命名
            svg_final_names_2.append(new_svg_name)                      # 把图片的名字存在list中，方便在md中插入引用
            svg_final_bboxs_2.append((L, U, R, D))
            svg_final_visited_2.append(False)
            svg_ID_2 += 1
       
    ## svg收尾。识别为drawing，但是在上面没有拼成一张图的。
    # 有收尾才comprehensive
    # xxxx
    # xxxx
    # xxxx
    # xxxx
    
    
    #--------- 通过json_from_DocXchain来获取，figure, table, equation的bbox ---------#
    figure_bbox_from_DocXChain = []
    table_bbox_from_DocXChain = []
    equation_bbox_from_DocXChain = []
    
    figure_from_DocXChain_visited = []          # 记忆化
    figure_bbox_from_DocXChain_overlappedRatio = []
    
    figure_only_from_DocXChain_bboxs = []     # 存储
    figure_only_from_DocXChain_names = []
    figure_only_from_DocXChain_visited = []
    figure_only_ID = 0
    
    with open(json_from_DocXchain_dir + f'/{page_ID}.json', 'r') as f:
        xf_json = json.load(f)
    width_from_json = xf_json['page_info']['width']
    height_from_json = xf_json['page_info']['height']
    LR_scaleRatio = width_from_json / (pageR - pageL)
    UD_scaleRatio = height_from_json / (pageD - pageU)
    # LR_scaleRatio = 2.085
    # UD_scaleRatio = 2.085
    # LR_scaleRatio = 1
    # UD_scaleRatio = 1
    
    for xf in xf_json['layout_dets']:
    # {0: 'title', 1: 'figure', 2: 'plain text', 3: 'header', 4: 'page number', 5: 'footnote', 6: 'footer', 7: 'table', 8: 'table caption', 9: 'figure caption', 10: 'equation', 11: 'full column', 12: 'sub column'}
        L = xf['poly'][0] / LR_scaleRatio
        U = xf['poly'][1] / LR_scaleRatio
        R = xf['poly'][2] / UD_scaleRatio
        D = xf['poly'][5] / UD_scaleRatio
        L, R = min(L, R), max(L, R)
        U, D = min(U, D), max(U, D)
        if xf["category_id"] == 1 and xf['score'] >= 0.5:
            figure_bbox_from_DocXChain.append((L, U, R, D))
            figure_from_DocXChain_visited.append(False)
            figure_bbox_from_DocXChain_overlappedRatio.append(0.0)
        elif xf['category_id'] == 7 and xf['score'] >= 0.5:
            table_bbox_from_DocXChain.append((L, U, R, D))
        elif xf['category_id'] == 10 and xf['score'] >= 0.5:
            equation_bbox_from_DocXChain.append((L, U, R, D))
            
    #---------------------- 比对上面识别出来的img,svg 与DocXChain给的figure -----------------------#
    
    ## 比对imgs
    for i, b1 in enumerate(figure_bbox_from_DocXChain):
        L1, U1, R1, D1 = b1
        for b2 in img_bboxs:
            L2, U2, R2, D2 = b2
            # 相同
            if check_rect1_sameWith_rect2(L1, U1, R1, D1, L2, U2, R2, D2) == True:
                figure_from_DocXChain_visited[i] = True
            # 包含
            elif check_rect1_contains_rect2(L1, U1, R1, D1, L2, U2, R2, D2) == True or (L1, U1, R1, D1, L2, U2, R2, D2) == True:
                figure_from_DocXChain_visited[i] = True
            else:
                # 重叠了相当一部分
                ratio_1, ratio_2 = calculate_overlapRatio_between_rect1_and_rect2(L1, U1, R1, D1, L2, U2, R2, D2)
                if (ratio_1 >= 0.5 and ratio_2 >= 0.5) or ratio_1 >= 0.8 or ratio_2 >= 0.8:
                    figure_from_DocXChain_visited[i] = True
                else:
                    figure_bbox_from_DocXChain_overlappedRatio[i] += ratio_1

    ## 比对svgs
    for i, b1 in enumerate(figure_bbox_from_DocXChain):
        L1, U1, R1, D1 = b1
        for b2 in svg_final_bboxs:
            L2, U2, R2, D2 = b2
            # 相同
            if check_rect1_sameWith_rect2(L1, U1, R1, D1, L2, U2, R2, D2) == True:
                figure_from_DocXChain_visited[i] = True
            # 包含
            elif check_rect1_contains_rect2(L1, U1, R1, D1, L2, U2, R2, D2) == True or (L1, U1, R1, D1, L2, U2, R2, D2) == True:
                figure_from_DocXChain_visited[i] = True
            else:
                # 重叠了相当一部分
                ratio_1, ratio_2 = calculate_overlapRatio_between_rect1_and_rect2(L1, U1, R1, D1, L2, U2, R2, D2)
                if (ratio_1 >= 0.5 and ratio_2 >= 0.5) or (min(ratio_1, ratio_2) >= 0.4 and max(ratio_1, ratio_2) >= 0.6):
                    figure_from_DocXChain_visited[i] = True
                else:
                    figure_bbox_from_DocXChain_overlappedRatio[i] += ratio_1
    
    for i in range(len(figure_from_DocXChain_visited)):
        if figure_bbox_from_DocXChain_overlappedRatio[i] >= 0.7:
            figure_from_DocXChain_visited[i] = True
    
    # DocXChain识别出来的figure，但是没被保存的。
    for i in range(len(figure_from_DocXChain_visited)):
        if figure_from_DocXChain_visited[i] == False:
            figure_from_DocXChain_visited[i] = True
            cur_bbox = figure_bbox_from_DocXChain[i]
            # cur_figure = page.get_pixmap(clip=cur_bbox)
            new_figure_name = "figure_only_{}_{}.png".format(page_ID, figure_only_ID)      # 图片name
            # cur_figure.save(res_dir_path + '/' + new_figure_name)        # 把图片存出在新建的文件夹，并命名
            figure_only_from_DocXChain_names.append(new_figure_name)                      # 把图片的名字存在list中，方便在md中插入引用
            figure_only_from_DocXChain_bboxs.append(cur_bbox)
            figure_only_from_DocXChain_visited.append(False)
            figure_only_ID += 1
    
            
    #--------------------------------------------------- 关于table ------------------------------------------------#
    tabs = []
    try:
        tabs = page.find_tables()                       # 获取所有表格
    except:
        pass
    table_dict = collections.defaultdict(list)      # 存储table的信息
    
    table_final_names = []
    table_final_bboxs = []
    table_ID = 0
    for L, U, R, D in table_bbox_from_DocXChain:
        # cur_table = page.get_pixmap(clip=(L,U,R,D))
        new_table_name = "table_{}_{}.png".format(page_ID, table_ID)      # 表格name
        # cur_table.save(res_dir_path + '/' + new_table_name)        # 把表格存出在新建的文件夹，并命名
        table_final_names.append(new_table_name)                      # 把表格的名字存在list中，方便在md中插入引用
        table_final_bboxs.append((L, U, R, D))
        table_ID += 1
        
        
    #--------------------------------------------------- 关于equation ------------------------------------------------#

    # equation_from_DocXChain_names = []
    # equation_from_DocXChain_bboxs = []
    # equation_ID = 0
    # for L, U, R, D in equation_bbox_from_DocXChain:
    #     if not(L < R and U < D):
    #         continue
    #     try:
    #         # cur_equation = page.get_pixmap(clip=(L,U,R,D))
    #         new_equation_name = "equation_{}_{}.png".format(page_ID, table_ID)      # 公式name
    #         # cur_equation.save(res_dir_path + '/' + new_equation_name)        # 把公式存出在新建的文件夹，并命名
    #         equation_from_DocXChain_names.append(new_equation_name)                      # 把公式的名字存在list中，方便在md中插入引用
    #         equation_from_DocXChain_bboxs.append((L, U, R, D))
    #         equation_ID += 1
    #     except:
    #         pass


    curPage_all_fig_bboxs = img_bboxs + svg_final_bboxs + figure_only_from_DocXChain_bboxs
    curPage_all_table_bboxs = table_final_bboxs
    # curPage_all_equation_bboxs = equation_from_DocXChain_bboxs
    
    return curPage_all_fig_bboxs, curPage_all_table_bboxs

