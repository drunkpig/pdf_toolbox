# 定义这里的bbox是一个list [x0, y0, x1, y1, block_id, idx_x, idx_y], 初始时候idx_x, idx_y都是None
# 其中x0, y0代表左上角坐标，x1, y1代表右下角坐标，坐标原点在左上角。

IDX_X = 5
IDX_Y = 6

X0_IDX = 0
Y0_IDX = 1
X1_IDX = 2
Y1_IDX = 3

def mymax(alist:list):
    """
    返回alist中的最大值，如果alist是空的，返回None
    """
    if len(alist) == 0:
        return [0]
    else:
        return max(alist)

def find_all_left_bbox(this_bbox, all_bboxes) -> list:
    """
    寻找this_bbox左边的所有bbox
    """
    left_boxes = [box for box in all_bboxes if box[X1_IDX] <= this_bbox[X0_IDX]]
    return left_boxes

def find_all_top_bbox(this_bbox, all_bboxes) -> list:
    """
    寻找this_bbox上面的所有bbox
    """
    top_boxes = [box for box in all_bboxes if box[Y1_IDX] <= this_bbox[Y0_IDX]]
    return top_boxes
    

def get_and_set_idx_x(this_bbox, all_bboxes) -> int:
    """
    寻找this_bbox在all_bboxes中的遮挡深度 idx_x
    """
    if this_bbox[IDX_X] is not None:
        return this_bbox[IDX_X]
    else:
        all_left_bboxes = find_all_left_bbox(this_bbox, all_bboxes)
        if len(all_left_bboxes) == 0:
            this_bbox[IDX_X] = 0
        else:
            all_left_bboxes_idx = [get_and_set_idx_x(bbox, all_bboxes) for bbox in all_left_bboxes]
            max_idx_x = mymax(all_left_bboxes_idx)
            this_bbox[IDX_X] = max_idx_x + 1
        return this_bbox[IDX_X]

def get_and_set_idx_y(this_bbox, all_bboxes) -> int:
    """
    寻找this_bbox在all_bboxes中y方向的遮挡深度 idx_y
    """
    if this_bbox[IDX_Y] is not None:
        return this_bbox[IDX_Y]
    else:
        all_top_bboxes = find_all_top_bbox(this_bbox, all_bboxes)
        if len(all_top_bboxes) == 0:
            this_bbox[IDX_Y] = 0
        else:
            all_top_bboxes_idx = [get_and_set_idx_y(bbox, all_bboxes) for bbox in all_top_bboxes]
            max_idx_y = mymax(all_top_bboxes_idx)
            this_bbox[IDX_Y] = max_idx_y + 1
        return this_bbox[IDX_Y]


def bbox_sort(all_bboxes:list):
    """
    排序
    """
    all_bboxes_idx_x = [get_and_set_idx_x(bbox, all_bboxes) for bbox in all_bboxes]
    all_bboxes_idx_y = [get_and_set_idx_y(bbox, all_bboxes) for bbox in all_bboxes]
    all_bboxes_idx = [(idx_x, idx_y) for idx_x, idx_y in zip(all_bboxes_idx_x, all_bboxes_idx_y)]
    
    all_bboxes_idx = [idx_x_y[0] * 100000 + idx_x_y[1] for idx_x_y in all_bboxes_idx] #变换成一个点，保证能够先X，X相同时按Y排序
    all_bboxes_idx = list(zip(all_bboxes_idx, all_bboxes))
    all_bboxes_idx.sort(key=lambda x: x[0])
    sorted_bboxes = [bbox for idx, bbox in all_bboxes_idx]
    return sorted_bboxes