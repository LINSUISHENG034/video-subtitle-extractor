# -*- coding: utf-8 -*-
"""
@Time    : 2024/2/4
@desc: 字幕提取器图形化界面（支持提取字幕图片）
"""
import os
import PySimpleGUI as sg
from threading import Thread
from gui import SubtitleExtractorGUI
import backend.main
from backend.tools.subtitle_image_extractor import SubtitleImageExtractor


class ImageExtractorGUI(SubtitleExtractorGUI):
    """
    字幕图片提取器图形化界面
    继承自SubtitleExtractorGUI，添加字幕图片提取功能
    """
    def __init__(self):
        super().__init__()
        # 提取模式：'srt' 或 'image'
        self.extract_mode = 'srt'

    def _create_layout(self):
        """
        创建布局，添加模式选择按钮
        """
        super()._create_layout()
        
        # 在运行按钮之前插入模式选择按钮
        mode_row = [
            sg.Text('提取模式:', font=self.font),
            sg.Radio('SRT字幕文件', 'EXTRACT_MODE', key='-MODE-SRT-', 
                    default=True, enable_events=True, font=self.font),
            sg.Radio('字幕图片', 'EXTRACT_MODE', key='-MODE-IMAGE-',
                    enable_events=True, font=self.font)
        ]
        
        # 将模式选择按钮插入到布局中
        self.layout.insert(-1, mode_row)

    def _run_event_handler(self, event, values):
        """
        处理运行事件，根据选择的模式使用不同的提取器
        """
        if event == '-RUN-':
            if self.video_cap is None:
                print(self.interface_config['SubtitleExtractorGUI']['OpenVideoFirst'])
            else:
                # 1) 禁止修改字幕滑块区域
                self.window['-Y-SLIDER-'].update(disabled=True)
                self.window['-X-SLIDER-'].update(disabled=True)
                self.window['-Y-SLIDER-H-'].update(disabled=True)
                self.window['-X-SLIDER-W-'].update(disabled=True)
                # 2) 禁止再次点击【运行】、【打开】和【识别语言】按钮
                self.window['-RUN-'].update(disabled=True)
                self.window['-FILE-'].update(disabled=True)
                self.window['-FILE_BTN-'].update(disabled=True)
                self.window['-LANGUAGE-MODE-'].update(disabled=True)
                # 3) 设定字幕区域位置
                self.xmin = int(values['-X-SLIDER-'])
                self.xmax = int(values['-X-SLIDER-'] + values['-X-SLIDER-W-'])
                self.ymin = int(values['-Y-SLIDER-'])
                self.ymax = int(values['-Y-SLIDER-'] + values['-Y-SLIDER-H-'])
                if self.ymax > self.frame_height:
                    self.ymax = self.frame_height
                if self.xmax > self.frame_width:
                    self.xmax = self.frame_width
                print(f"字幕区域：({self.ymin},{self.ymax},{self.xmin},{self.xmax})")
                subtitle_area = (self.ymin, self.ymax, self.xmin, self.xmax)
                y_p = self.ymin / self.frame_height
                h_p = (self.ymax - self.ymin) / self.frame_height
                x_p = self.xmin / self.frame_width
                w_p = (self.xmax - self.xmin) / self.frame_width
                self.set_subtitle_config(y_p, h_p, x_p, w_p)

                def task():
                    while self.video_paths:
                        video_path = self.video_paths.pop()
                        # 根据模式选择使用不同的提取器
                        if values['-MODE-IMAGE-']:
                            self.se = SubtitleImageExtractor(video_path, subtitle_area)
                        else:
                            self.se = backend.main.SubtitleExtractor(video_path, subtitle_area)
                        self.se.run()
                
                Thread(target=task, daemon=True).start()
                self.video_cap.release()
                self.video_cap = None

    def _mode_event_handler(self, event, values):
        """
        处理模式选择事件
        """
        if event in ['-MODE-SRT-', '-MODE-IMAGE-']:
            self.extract_mode = 'image' if values['-MODE-IMAGE-'] else 'srt'
            # 当选择图片模式时，禁用语言选择按钮（因为不需要OCR）
            self.window['-LANGUAGE-MODE-'].update(disabled=values['-MODE-IMAGE-'])

    def run(self):
        """
        运行GUI，添加模式选择事件处理
        """
        # 创建布局
        self._create_layout()
        # 创建窗口
        self.window = sg.Window(
            title=self.interface_config['SubtitleExtractorGUI']['Title'],
            layout=self.layout,
            icon=self.icon
        )
        
        while True:
            # 循环读取事件
            event, values = self.window.read(timeout=10)
            # 处理【打开】事件
            self._file_event_handler(event, values)
            # 处理【滑动】事件
            self._slide_event_handler(event, values)
            # 处理【识别语言】事件
            self._language_mode_event_handler(event)
            # 处理【运行】事件
            self._run_event_handler(event, values)
            # 处理【模式选择】事件
            self._mode_event_handler(event, values)
            
            # 如果关闭软件，退出
            if event == sg.WIN_CLOSED:
                break
                
            # 更新进度条
            if self.se is not None:
                self.window['-PROG-'].update(self.se.progress_total)
                if self.se.isFinished:
                    # 1) 打开修改字幕滑块区域按钮
                    self.window['-Y-SLIDER-'].update(disabled=False)
                    self.window['-X-SLIDER-'].update(disabled=False)
                    self.window['-Y-SLIDER-H-'].update(disabled=False)
                    self.window['-X-SLIDER-W-'].update(disabled=False)
                    # 2) 打开【运行】、【打开】和【识别语言】按钮
                    self.window['-RUN-'].update(disabled=False)
                    self.window['-FILE-'].update(disabled=False)
                    self.window['-FILE_BTN-'].update(disabled=False)
                    # 只在SRT模式下启用语言选择
                    self.window['-LANGUAGE-MODE-'].update(
                        disabled=values['-MODE-IMAGE-']
                    )
                    self.se = None


if __name__ == '__main__':
    try:
        import multiprocessing
        multiprocessing.set_start_method("spawn")
        # 运行图形化界面
        gui = ImageExtractorGUI()
        gui.run()
    except Exception as e:
        print(f'[{type(e)}] {e}')
        import traceback
        traceback.print_exc()
        msg = traceback.format_exc()
        err_log_path = os.path.join(os.path.expanduser('~'), 'VSE-Error-Message.log')
        with open(err_log_path, 'w', encoding='utf-8') as f:
            f.writelines(msg)
        import platform
        if platform.system() == 'Windows':
            os.system('pause')
        else:
            input()