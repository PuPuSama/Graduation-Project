#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
语音文件缓存生成器
预先生成常用的语音文件，避免运行时生成，提高系统响应速度
"""

import os
import time
from loguru import logger
from tts import ssml_save, ssml_wav
from fire_alarm import VOICE_ALARM_TEXT

# 配置日志 - 提高日志级别到WARNING，减少INFO日志
logger.add("Log/voice_cache.log", rotation="10 MB", compression="zip", level="WARNING")

# 语音文件目录
SOUND_DIR = "Sound"

# 需要预生成的语音文件配置
VOICE_FILES = {
    # 火灾报警相关语音
    "fire_alarm": {
        "text": VOICE_ALARM_TEXT,
        "file": os.path.join(SOUND_DIR, "fire_alarm.raw"),
        "format": "raw"
    },
    # 整点报时语音 (0-23小时)
    **{f"hour_{hour}": {
        "text": f'整点报时,已经{hour if hour<13 else hour-12}点啦',
        "file": os.path.join(SOUND_DIR, f"hour_{hour}.wav"),
        "format": "wav"
    } for hour in range(24)},
    # 常用提示语
    "welcome": {
        "text": "欢迎使用智能家居助手",
        "file": os.path.join(SOUND_DIR, "welcome.wav"),
        "format": "wav"
    },
    "goodbye": {
        "text": "再见，期待下次为您服务",
        "file": os.path.join(SOUND_DIR, "goodbye.wav"),
        "format": "wav"
    },
    "system_start": {
        "text": "系统已启动，所有服务运行正常",
        "file": os.path.join(SOUND_DIR, "system_start.wav"),
        "format": "wav"
    },
    "system_shutdown": {
        "text": "系统正在关闭，请稍等",
        "file": os.path.join(SOUND_DIR, "system_shutdown.wav"),
        "format": "wav"
    },
    "error": {
        "text": "抱歉，系统遇到错误，请稍后再试",
        "file": os.path.join(SOUND_DIR, "error.wav"),
        "format": "wav"
    }
}

def ensure_sound_dir():
    """确保语音文件目录存在"""
    if not os.path.exists(SOUND_DIR):
        os.makedirs(SOUND_DIR)
        logger.info(f"创建语音文件目录: {SOUND_DIR}")

def generate_voice_files(force_regenerate=False):
    """
    生成所有配置的语音文件
    
    参数:
        force_regenerate: 是否强制重新生成所有文件，即使文件已存在
    """
    ensure_sound_dir()
    
    start_time = time.time()
    success_count = 0
    fail_count = 0
    skip_count = 0
    
    # 仅在需要生成文件时记录开始日志
    need_generation = force_regenerate
    if not need_generation:
        # 检查是否有文件需要生成
        for config in VOICE_FILES.values():
            if not os.path.exists(config["file"]):
                need_generation = True
                break
    
    if need_generation:
        logger.info(f"开始生成语音文件，共 {len(VOICE_FILES)} 个文件")
    
    for key, config in VOICE_FILES.items():
        try:
            if os.path.exists(config["file"]) and not force_regenerate:
                # 不再为每个跳过的文件记录日志
                skip_count += 1
                continue
            
            # 根据格式选择生成方法
            if config["format"] == "raw":
                ssml_save(config["text"], config["file"])
            else:  # wav格式
                ssml_wav(config["text"], config["file"])
            
            # 只记录新生成的文件
            logger.info(f"生成语音文件: {config['file']}")
            success_count += 1
            
        except Exception as e:
            logger.error(f"生成语音文件 {config['file']} 失败: {e}")
            fail_count += 1
    
    # 只在有实际操作时记录完成日志
    if success_count > 0 or fail_count > 0:
        end_time = time.time()
        duration = end_time - start_time
        logger.info(f"语音文件生成完成，耗时 {duration:.2f} 秒，成功: {success_count}, 失败: {fail_count}, 跳过: {skip_count}")
    
    return success_count, fail_count, skip_count

if __name__ == "__main__":
    import sys
    
    # 检查是否有强制重新生成的参数
    force = False
    if len(sys.argv) > 1 and sys.argv[1].lower() in ['-f', '--force']:
        force = True
        print("将强制重新生成所有语音文件")
    
    print(f"开始生成语音文件，共 {len(VOICE_FILES)} 个文件...")
    success, fail, skip = generate_voice_files(force_regenerate=force)
    print(f"语音文件生成完成！成功: {success}, 失败: {fail}, 跳过: {skip}") 