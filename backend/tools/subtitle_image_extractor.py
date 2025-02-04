# -*- coding: utf-8 -*-
"""
@Time    : 2024/2/4
@desc: 提取视频字幕区域为图片
"""
import os
import cv2
import sys
import numpy as np
from Levenshtein import ratio
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from main import SubtitleExtractor
from tools.infer import utility
from tools.infer.predict_det import TextDetector
from tools.ocr import get_coordinates, OcrRecogniser
import importlib
import config


class SubtitleImageExtractor(SubtitleExtractor):
    """
    视频字幕区域提取为图片类
    继承自SubtitleExtractor，重写部分方法以实现保存字幕区域图片的功能
    """

    def __init__(self, vd_path, sub_area=None):
        super().__init__(vd_path, sub_area)
        # 字幕图片保存目录
        self.subtitle_images_dir = os.path.join(self.temp_output_dir, 'subtitle_images')
        if not os.path.exists(self.subtitle_images_dir):
            os.makedirs(self.subtitle_images_dir)
        
        # 确保text_detector被正确初始化
        importlib.reload(config)
        args = utility.parse_args()
        args.det_algorithm = 'DB'
        args.det_model_dir = config.DET_MODEL_PATH
        self.text_detector = TextDetector(args)
        
        # OCR识别器
        self.ocr = OcrRecogniser()
        # 上一帧的文本内容
        self.last_text = None

    def save_image(self, image, save_path):
        """
        安全地保存图片，处理可能的错误
        """
        try:
            # 首先尝试直接保存为BMP（不需要zlib）
            bmp_path = save_path.rsplit('.', 1)[0] + '.bmp'
            success = cv2.imwrite(bmp_path, image)
            if success:
                return True
            
            # 如果BMP保存失败，使用numpy保存
            np.save(save_path.rsplit('.', 1)[0] + '.npy', image)
            return True
        except Exception as e:
            print(f"保存图片失败：{str(e)}")
            return False

    def get_area_text(self, ocr_result):
        """
        获取字幕区域内的文本内容
        """
        box, text = ocr_result
        coordinates = get_coordinates(box)
        area_text = []
        for content, coordinate in zip(text, coordinates):
            if self.sub_area is not None:
                s_ymin = self.sub_area[0]
                s_ymax = self.sub_area[1]
                s_xmin = self.sub_area[2]
                s_xmax = self.sub_area[3]
                xmin = coordinate[0]
                xmax = coordinate[1]
                ymin = coordinate[2]
                ymax = coordinate[3]
                if s_xmin <= xmin and xmax <= s_xmax and s_ymin <= ymin and ymax <= s_ymax:
                    area_text.append(content[0])
            else:
                area_text.append(content[0])
        return area_text

    def get_subtitle_text(self, frame):
        """
        获取帧中的字幕文本
        """
        dt_boxes, _ = self.text_detector(frame)
        if len(dt_boxes) == 0:
            return None, []
            
        if self.sub_area is not None:
            s_ymin, s_ymax, s_xmin, s_xmax = self.sub_area
            coordinate_list = get_coordinates(dt_boxes.tolist())
            valid_regions = []
            for coordinate in coordinate_list:
                xmin, xmax, ymin, ymax = coordinate
                if (s_xmin <= xmin and xmax <= s_xmax and 
                    s_ymin <= ymin and ymax <= s_ymax):
                    valid_regions.append((xmin, xmax, ymin, ymax))
            if not valid_regions:
                return None, []
            dt_box, rec_res = self.ocr.predict(frame)
            text = "".join(self.get_area_text((dt_box, rec_res)))
            return text, valid_regions
        else:
            dt_box, rec_res = self.ocr.predict(frame)
            text = "".join(self.get_area_text((dt_box, rec_res)))
            return text, get_coordinates(dt_boxes.tolist())

    def run(self):
        """
        运行字幕图片提取流程
        """
        # 记录开始运行的时间
        self.lock.acquire()
        try:
            # 重置进度条
            self.update_progress(ocr=0, frame_extract=0)
            # 打印视频帧数与帧率
            print(f"视频总帧数：{self.frame_count}，帧率：{self.fps}")
            # 打印加载模型信息
            print(f'使用检测模型：{os.path.basename(os.path.dirname(config.DET_MODEL_PATH))}-{os.path.basename(config.DET_MODEL_PATH)}')
            print("开始处理视频帧...")

            if self.sub_area is not None:
                self.extract_frame_by_det()
            else:
                self.extract_frame_by_fps()

            print("字幕图片提取完成！")
            print(f"字幕图片保存在：{self.subtitle_images_dir}")
            self.update_progress(ocr=100, frame_extract=100)
            self.isFinished = True
        finally:
            self.lock.release()

    def extract_frame_by_det(self):
        """
        通过检测字幕区域位置提取字幕帧并保存为图片
        使用文本相似度比较来避免保存重复的字幕
        """
        # 删除缓存
        if not config.DEBUG_NO_DELETE_CACHE:
            if len(os.listdir(self.frame_output_dir)) > 0:
                for i in os.listdir(self.frame_output_dir):
                    os.remove(os.path.join(self.frame_output_dir, i))

        # 当前视频帧的帧号
        current_frame_no = 0
        total_frames = int(self.frame_count)
        print(f"总帧数: {total_frames}")

        try:
            while self.video_cap.isOpened():
                ret, frame = self.video_cap.read()
                if not ret:
                    break
                
                current_frame_no += 1
                if current_frame_no % 100 == 0:  # 每100帧显示一次进度
                    print(f"处理进度: {current_frame_no}/{total_frames} ({(current_frame_no/total_frames*100):.1f}%)")
                
                try:
                    # 获取当前帧的字幕文本和区域
                    current_text, regions = self.get_subtitle_text(frame)
                    
                    # 如果检测到文本且与上一帧不同，保存图片
                    if current_text and (self.last_text is None or 
                            ratio(current_text, self.last_text) < config.THRESHOLD_TEXT_SIMILARITY):
                        for idx, (xmin, xmax, ymin, ymax) in enumerate(regions):
                            # 裁剪字幕区域
                            subtitle_region = frame[ymin:ymax, xmin:xmax]
                            # 保存图片，使用帧号和区域编号命名
                            image_name = f'frame_{current_frame_no:06d}_region_{idx:02d}.png'
                            self.save_image(subtitle_region, os.path.join(self.subtitle_images_dir, image_name))
                        self.last_text = current_text

                except Exception as e:
                    print(f"处理帧 {current_frame_no} 时发生错误: {str(e)}")
                    continue

                # 更新进度
                self.update_progress(frame_extract=(current_frame_no / total_frames * 100))

        finally:
            if self.video_cap is not None:
                self.video_cap.release()

    def extract_frame_by_fps(self):
        """
        根据帧率提取视频帧并保存字幕区域图片
        使用文本相似度比较来避免保存重复的字幕
        """
        # 删除缓存
        if not config.DEBUG_NO_DELETE_CACHE:
            if len(os.listdir(self.frame_output_dir)) > 0:
                for i in os.listdir(self.frame_output_dir):
                    os.remove(os.path.join(self.frame_output_dir, i))
        
        # 当前视频帧的帧号
        current_frame_no = 0
        total_frames = int(self.frame_count)
        print(f"总帧数: {total_frames}")
        
        try:
            while self.video_cap.isOpened():
                ret, frame = self.video_cap.read()
                if not ret:
                    break
                    
                current_frame_no += 1
                if current_frame_no % 100 == 0:  # 每100帧显示一次进度
                    print(f"处理进度: {current_frame_no}/{total_frames} ({(current_frame_no/total_frames*100):.1f}%)")
                
                try:
                    # 获取当前帧的字幕文本和区域
                    current_text, regions = self.get_subtitle_text(frame)
                    
                    # 如果检测到文本且与上一帧不同，保存图片
                    if current_text and (self.last_text is None or 
                            ratio(current_text, self.last_text) < config.THRESHOLD_TEXT_SIMILARITY):
                        for idx, (xmin, xmax, ymin, ymax) in enumerate(regions):
                            # 裁剪字幕区域
                            subtitle_region = frame[ymin:ymax, xmin:xmax]
                            # 保存图片，使用帧号和区域编号命名
                            image_name = f'frame_{current_frame_no:06d}_region_{idx:02d}.png'
                            self.save_image(subtitle_region, os.path.join(self.subtitle_images_dir, image_name))
                        self.last_text = current_text

                except Exception as e:
                    print(f"处理帧 {current_frame_no} 时发生错误: {str(e)}")
                    continue
                
                # 跳过剩下的帧
                for i in range(int(self.fps // config.EXTRACT_FREQUENCY) - 1):
                    ret, _ = self.video_cap.read()
                    if ret:
                        current_frame_no += 1
                        
                # 更新进度条
                self.update_progress(frame_extract=(current_frame_no / total_frames * 100))
        finally:
            if self.video_cap is not None:
                self.video_cap.release()


if __name__ == '__main__':
    # 提示用户输入视频路径
    video_path = input("请输入视频文件路径：").strip()
    
    # 提示用户输入字幕区域
    try:
        y_min, y_max, x_min, x_max = map(int, input("请输入字幕区域坐标 (ymin ymax xmin xmax)：").split())
        subtitle_area = (y_min, y_max, x_min, x_max)
    except ValueError:
        subtitle_area = None
        
    # 创建字幕图片提取对象
    extractor = SubtitleImageExtractor(video_path, subtitle_area)
    # 开始提取字幕图片
    extractor.run()