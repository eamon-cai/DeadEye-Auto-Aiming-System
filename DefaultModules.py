# coding: utf-8
# cython: language_level=3
import time

import pydirectinput
from pynput import mouse
from ultralytics import YOLO

from BaseModules import *
from TensorRTEngine import *


class YoloDetector(DetectModule):
    def __init__(self, model: str):
        super(YoloDetector).__init__()
        self.model = None
        self.model_type = None
        self.load_model(model)

    def on_exit(self):
        if self.model_type == 'trt':
            self.model.on_exit()

    def load_model(self, model: str):
        if '.pt' in model:
            self.model = YOLO(model)
            self.model_type = 'pt'
        else:
            print('Loading TensorRT engine...')
            self.model = TensorRTEngine(model)
            self.model_type = 'trt'

    def target_detect(self, img) -> list:
        if self.model is None:
            raise RuntimeError("Model is not loaded. Please call load_model() first.")

        results = []
        if self.model_type == 'pt':
            # h, w = img.shape[:2]
            result = self.model(img, verbose=False, half=False, iou=0.8, conf=0.75)
            detections = result[0]

            # 提取检测结果中的边界框、类别标签和置信度
            boxes = detections.boxes.xyxy.cpu().numpy()  # 边界框坐标
            labels = detections.boxes.cls.cpu().numpy().astype(int)  # 类别标签
            # scores = detections.boxes.conf.cpu().numpy()  # 置信度

            # 在图像上绘制边界框
            for box, label in zip(boxes, labels):
                x1, y1, x2, y2 = box
                class_name = detections.names[label]  # 获取类别名称
                result = [class_name, (int(x1), int(y1)), (int(x2), int(y2))]
                results.append(result)
                # 绘制边界框
                # cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                # 绘制类别标签
                # cv2.putText(img, class_name, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        else:
            results = self.model.inference(img, conf=0.75, end2end=True)

        # 显示结果图像
        # cv2.imshow("Detection Results", img)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()
        return results


DEFAULT_P = 0.5
DEFEULT_I = 0.25
DEFAULT_D = 0.1
DEFAULT_R = 0.9


class DeadEyeAutoAimingModule(AutoAimModule):
    def __init__(self, view_range):
        super(DeadEyeAutoAimingModule).__init__()
        self.view_range_start = self.calculate_view_range_start_pos(view_range)

        # mouse controller
        self.mouse_controller = mouse.Controller()

        # Auto aim settings
        self.auto_aim_range_x = 1.5
        self.auto_aim_range_y = 1.5
        self.aim_sensitive = 1

        # Auto shoot settings
        self.last_auto_shoot_time = time.time()

        # PID
        self.max_movement = 320  # max output movement on single direction, to avoid large movement
        # PID核心参数
        k_adjust = 1
        self.k_p = DEFAULT_P * k_adjust  # 比例系数 主要移动
        self.k_i = DEFEULT_I * k_adjust  # 积分系数 补充移动
        self.k_d = DEFAULT_D * k_adjust  # 微分系数 抑制
        # 回弹强度
        self.rebound_strength = DEFAULT_R  # 作用于积分系数，用于消除瞄准回弹效果
        # PID计算变量
        # 前一次时间，用于计算dt
        self.previous_time = None
        self.x_integral_value = 0
        self.y_integral_value = 0
        self.previous_distance_x = 0
        self.previous_distance_y = 0

    def auto_shoot(self, target_list: list):
        # 自动扳机
        t = time.time()
        if t - self.last_auto_shoot_time < 0.25:
            return

        mouseX, mouseY = pyautogui.position()
        # print('鼠标位置：', mouseX, ',', mouseY)

        for target in target_list:
            tag, left_top, right_bottom = target.label, target.left_top, target.right_bottom
            width = right_bottom[0] - left_top[0]
            height = right_bottom[1] - left_top[1]
            if left_top[0] + self.view_range_start[0] + 0.25 * width <= mouseX <= right_bottom[0] + \
                    self.view_range_start[
                        0] - 0.25 * width:
                if left_top[1] + self.view_range_start[1] <= mouseY <= right_bottom[1] + self.view_range_start[
                    1] - 0.75 * height:
                    # windll.user32.BlockInput(1)
                    self.shoot()
                    break
            if left_top[0] + self.view_range_start[0] + 0.15 * width <= mouseX <= right_bottom[0] + \
                    self.view_range_start[
                        0] - 0.15 * width:
                if left_top[1] + self.view_range_start[1] <= mouseY <= right_bottom[1] + self.view_range_start[
                    1] - 0.5 * height:
                    # windll.user32.BlockInput(1)
                    self.shoot()
                    self.last_auto_shoot_time = t
                    break
        # print('瞄准计算用时：', time.time() - t)
        return

    def auto_aim(self, target_list: list):
        t = time.time()
        mouseX, mouseY = pyautogui.position()

        if not len(target_list):
            return False
        rel_mouse_x = mouseX - self.view_range_start[0]
        rel_mouse_y = mouseY - self.view_range_start[1]
        # 寻找最近目标的时候，最终距离减去目标长度宽度，这样可以避免小目标出现在大目标附近时，实际距离更远的小目标成为最近的目标
        nearest_target = min(target_list, key=lambda k: abs((k.left_top[0] + k.right_bottom[0]) / 2 - rel_mouse_x) +
                                                        abs((k.left_top[1] + k.right_bottom[1]) / 2 - rel_mouse_y) -
                                                        (k.right_bottom[0] - k.left_top[0] + k.right_bottom[1] -
                                                         k.left_top[1]))
        width = nearest_target.right_bottom[0] - nearest_target.left_top[0]
        height = nearest_target.right_bottom[1] - nearest_target.left_top[1]
        distance_x = (nearest_target.left_top[0] + nearest_target.right_bottom[0]) / 2 - rel_mouse_x
        distance_y = (nearest_target.left_top[1] + nearest_target.right_bottom[1]) / 2 - rel_mouse_y
        if distance_x > width * self.auto_aim_range_x or distance_y > height * self.auto_aim_range_y:
            return False
        # print('最近目标：', nearest_target)
        # 移动到最近的目标
        position_fixed = (round((nearest_target.left_top[0] + nearest_target.right_bottom[0]) * 0.5),
                          round((nearest_target.left_top[1] + nearest_target.right_bottom[1]) * 0.5))
        x_r, y_r = self.calculate_mouse_movement_by_pid(position_fixed, (rel_mouse_x, rel_mouse_y))  # 计算鼠标移动

        # 鼠标操控部分
        pydirectinput.moveRel(int(x_r * self.aim_sensitive),
                              int(y_r * self.aim_sensitive),
                              duration=0.000, relative=True)

    def shoot(self):
        self.mouse_controller.click(mouse.Button.left)

    def set_pid_parameters(self, p=None, i=None, d=None, rebond_strength=None):
        if p is not None:
            self.k_p = p
        if i is not None:
            self.k_i = i
        if d is not None:
            self.k_d = d
        if rebond_strength is not None:
            self.rebound_strength = rebond_strength

    def calculate_mouse_movement_by_pid(self, target_position, mouse_position):
        # PID控制算法
        if self.previous_time is not None and time.time() - self.previous_time > 0.5:
            # 消除残像
            self.previous_time = None
            self.x_integral_value = 0
            self.y_integral_value = 0
            self.previous_distance_x = 0
            self.previous_distance_y = 0

        # 绝对偏差
        current_time = time.time()
        distance_x = target_position[0] - mouse_position[0]
        if distance_x * self.previous_distance_x < 0:
            self.x_integral_value = self.x_integral_value * self.rebound_strength  # 降低积分量
        distance_y = target_position[1] - mouse_position[1]
        if distance_y * self.previous_distance_y < 0:
            self.y_integral_value = self.y_integral_value * self.rebound_strength  # 降低积分量

        # P/比例
        x_p = self.k_p * distance_x
        y_p = self.k_p * distance_y

        if self.previous_time is not None:
            # I/积分
            d_time = current_time - self.previous_time
            self.x_integral_value = self.x_integral_value + distance_x
            x_i = self.k_i * self.x_integral_value
            self.y_integral_value = self.y_integral_value + distance_y
            y_i = self.k_i * self.y_integral_value

            # D/微分
            if d_time != 0:
                derivative_x = (distance_x - self.previous_distance_x) / d_time
                x_d = self.k_d * derivative_x
                derivative_y = (distance_y - self.previous_distance_y) / d_time
                y_d = self.k_d * derivative_y
            else:
                x_d = 0
                y_d = 0
        else:
            x_i = 0
            y_i = 0
            x_d = 0
            y_d = 0

        # 结果
        x_r = x_p + x_i + x_d
        # print(x_p, x_i, x_d)
        y_r = y_p + y_i + y_d
        # print(y_p, y_i, y_d)

        # 极大值约束
        if abs(x_r) > self.max_movement:
            x_r = x_r / abs(x_r) * self.max_movement
        if abs(y_r) > self.max_movement:
            y_r = y_r / abs(y_r) * self.max_movement

        # 更新旧信息
        self.previous_time = current_time
        self.previous_distance_x = distance_x
        self.previous_distance_y = distance_y

        return x_r, y_r
